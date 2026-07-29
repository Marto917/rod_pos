"""Ajuste de caja: corregir forma de pago (sacar de X, poner en Y)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

from db import get_connection
from db_init import get_base_dir
from pos_config import is_client_mode, load_config, server_base_url
from services.cierre_caja import _money, _norm_metodo_pago

METODOS_AJUSTE = ("EFECTIVO", "TARJETA", "MERCADOPAGO")

CODIGOS_AJUSTE = {
    "AJUSTE DE CAJA",
    "AJUSTEDECAJA",
    "AJUSTE",
    "AJUSTE_CAJA",
}


def es_codigo_ajuste(codigo: str) -> bool:
    raw = (codigo or "").strip().upper()
    compact = "".join(ch for ch in raw if ch.isalnum())
    return raw in CODIGOS_AJUSTE or compact in {"AJUSTEDECAJA", "AJUSTE", "AJUSTECAJA"}


def _http_json(method: str, path: str, payload: dict | None = None, timeout: float = 20.0) -> dict:
    url = server_base_url() + path
    data = None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
            msg = parsed.get("error") or detail
        except Exception:
            msg = detail or str(e)
        raise ValueError(msg) from e
    except Exception as e:
        raise ValueError("No se pudo conectar al servidor LAN: %s" % e) from e


def _pdf_safe(texto) -> str:
    """Core fonts de FPDF solo latin-1: evita PDFs rotos por unicode."""
    t = str(texto if texto is not None else "")
    repl = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U",
        "ñ": "n", "Ñ": "N", "ü": "u", "Ü": "U",
        "¿": "?", "¡": "!", "°": "o", "–": "-", "—": "-",
        "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...",
        "→": "->", "←": "<-", "€": "EUR",
    }
    for a, b in repl.items():
        t = t.replace(a, b)
    return t.encode("latin-1", "replace").decode("latin-1")


def titulo_ajuste(nro_dia: int, fecha: str | None = None) -> str:
    """Ej: Ajuste de caja 1 - 26/07/2026"""
    if fecha:
        try:
            if len(fecha) >= 10 and fecha[4] == "-":
                d = datetime.strptime(fecha[:10], "%Y-%m-%d")
            else:
                d = datetime.strptime(fecha[:10], "%d/%m/%Y")
            fecha_txt = d.strftime("%d/%m/%Y")
        except Exception:
            fecha_txt = (fecha or "")[:10]
    else:
        fecha_txt = datetime.now().strftime("%d/%m/%Y")
    return "Ajuste de caja %s - %s" % (int(nro_dia or 1), fecha_txt)


def proximo_nro_dia(fecha_dia: str | None = None) -> int:
    fecha_dia = fecha_dia or datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT COALESCE(MAX(nro_dia), 0)
            FROM ajustes_caja
            WHERE date(fecha)=?
            """,
            (fecha_dia,),
        )
        row = c.fetchone()
        return int((row[0] if row else 0) or 0) + 1
    finally:
        conn.close()


def lineas_comprobante_ajuste(
    *,
    nro_dia: int,
    user_name: str,
    monto: float,
    metodo_desde: str,
    metodo_hacia: str,
    observaciones: str,
    fecha: str,
    terminal_id: str | None = None,
    sucursal: str | None = None,
) -> list[str]:
    titulo = titulo_ajuste(nro_dia, fecha)
    return [
        titulo,
        "-" * 32,
        "Sucursal: %s" % (sucursal or "-"),
        "Terminal: %s" % (terminal_id or "-"),
        "Cajero: %s" % user_name,
        "Fecha: %s" % fecha,
        "Nro del dia: %s" % nro_dia,
        "-" * 32,
        "Sacar de: %s" % metodo_desde,
        "Poner en: %s" % metodo_hacia,
        "Monto: $%.2f" % monto,
        "Obs: %s" % (observaciones or "Ajuste de forma de pago"),
        "-" * 32,
        "Comprobante interno (no fiscal)",
        titulo,
    ]


def registrar_ajuste(
    *,
    usuario_id: int,
    user_name: str,
    monto: float,
    metodo_desde: str,
    metodo_hacia: str,
    observaciones: str = "",
) -> dict[str, Any]:
    monto = _money(monto)
    if monto <= 0:
        raise ValueError("El monto debe ser mayor a 0.")
    desde = _norm_metodo_pago(metodo_desde)
    hacia = _norm_metodo_pago(metodo_hacia)
    if desde not in METODOS_AJUSTE or hacia not in METODOS_AJUSTE:
        raise ValueError("Métodos válidos: EFECTIVO, TARJETA, MERCADOPAGO.")
    if desde == hacia:
        raise ValueError("Origen y destino tienen que ser distintos.")

    cfg = load_config()
    payload = {
        "usuario_id": usuario_id,
        "user_name": user_name,
        "monto": monto,
        "metodo_desde": desde,
        "metodo_hacia": hacia,
        "observaciones": (observaciones or "").strip() or "Ajuste de forma de pago",
        "terminal_id": cfg.get("terminal_id"),
        "sucursal": cfg.get("sucursal_nombre"),
    }
    if is_client_mode():
        data = _http_json("POST", "/api/ajustes", payload)
        if not data.get("ok"):
            raise ValueError(data.get("error") or "No se pudo registrar el ajuste")
        nro_dia = int(data.get("nro_dia") or 1)
        fecha = data.get("fecha") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pdf_path = generar_pdf_ajuste(
            ajuste_id=data.get("ajuste_id") or 0,
            nro_dia=nro_dia,
            user_name=user_name,
            monto=monto,
            metodo_desde=desde,
            metodo_hacia=hacia,
            observaciones=payload["observaciones"],
            terminal_id=payload["terminal_id"],
            sucursal=payload["sucursal"],
            fecha=fecha,
        )
        data["pdf_path"] = pdf_path
        data["nro_dia"] = nro_dia
        data["titulo"] = titulo_ajuste(nro_dia, fecha)
        data["lineas"] = lineas_comprobante_ajuste(
            nro_dia=nro_dia,
            user_name=user_name,
            monto=monto,
            metodo_desde=desde,
            metodo_hacia=hacia,
            observaciones=payload["observaciones"],
            fecha=fecha,
            terminal_id=payload["terminal_id"],
            sucursal=payload["sucursal"],
        )
        return data

    return registrar_ajuste_local(**payload)


def registrar_ajuste_local(
    *,
    usuario_id: int,
    user_name: str,
    monto: float,
    metodo_desde: str,
    metodo_hacia: str,
    observaciones: str = "",
    terminal_id: str | None = None,
    sucursal: str | None = None,
) -> dict[str, Any]:
    monto = _money(monto)
    desde = _norm_metodo_pago(metodo_desde)
    hacia = _norm_metodo_pago(metodo_hacia)
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fecha_dia = ahora[:10]
    cfg = load_config()
    terminal_id = terminal_id or cfg.get("terminal_id")
    sucursal = sucursal or cfg.get("sucursal_nombre")
    obs = observaciones or "Ajuste de forma de pago"
    nro_dia = proximo_nro_dia(fecha_dia)

    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO ajustes_caja (
                usuario_id, fecha, monto, metodo_desde, metodo_hacia,
                observaciones, pdf_path, terminal_id, nro_dia
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (usuario_id, ahora, monto, desde, hacia, obs, None, terminal_id, nro_dia),
        )
        ajuste_id = c.lastrowid
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    pdf_path = generar_pdf_ajuste(
        ajuste_id=ajuste_id,
        nro_dia=nro_dia,
        user_name=user_name,
        monto=monto,
        metodo_desde=desde,
        metodo_hacia=hacia,
        observaciones=obs,
        terminal_id=terminal_id,
        sucursal=sucursal,
        fecha=ahora,
    )

    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("UPDATE ajustes_caja SET pdf_path=? WHERE id=?", (pdf_path, ajuste_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "ok": True,
        "ajuste_id": ajuste_id,
        "nro_dia": nro_dia,
        "titulo": titulo_ajuste(nro_dia, ahora),
        "fecha": ahora,
        "monto": monto,
        "metodo_desde": desde,
        "metodo_hacia": hacia,
        "pdf_path": pdf_path,
        "lineas": lineas_comprobante_ajuste(
            nro_dia=nro_dia,
            user_name=user_name,
            monto=monto,
            metodo_desde=desde,
            metodo_hacia=hacia,
            observaciones=obs,
            fecha=ahora,
            terminal_id=terminal_id,
            sucursal=sucursal,
        ),
    }


def listar_ajustes_pendientes(usuario_id: int, fecha: str) -> list[dict]:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, fecha, monto, metodo_desde, metodo_hacia, observaciones,
                   terminal_id, nro_dia
            FROM ajustes_caja
            WHERE date(fecha)=?
              AND usuario_id=?
              AND arqueo_id IS NULL
            ORDER BY fecha ASC
            """,
            (fecha, usuario_id),
        )
        return [dict(r) for r in c.fetchall()]
    finally:
        conn.close()


def aplicar_ajustes_a_por_metodo(por_metodo: dict, ajustes: list[dict]) -> dict:
    """Resta del origen y suma al destino (misma estructura de buckets)."""
    buckets = {k: {"tickets": v["tickets"], "total": float(v["total"])} for k, v in por_metodo.items()}
    for aj in ajustes:
        desde = _norm_metodo_pago(aj.get("metodo_desde"))
        hacia = _norm_metodo_pago(aj.get("metodo_hacia"))
        monto = _money(aj.get("monto"))
        b_desde = buckets.setdefault(desde, {"tickets": 0, "total": 0.0})
        b_hacia = buckets.setdefault(hacia, {"tickets": 0, "total": 0.0})
        b_desde["total"] = _money(b_desde["total"] - monto)
        b_hacia["total"] = _money(b_hacia["total"] + monto)
    return buckets


def marcar_ajustes_en_arqueo(usuario_id: int, fecha: str, arqueo_id: int) -> None:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            UPDATE ajustes_caja
            SET arqueo_id=?
            WHERE date(fecha)=? AND usuario_id=? AND arqueo_id IS NULL
            """,
            (arqueo_id, fecha, usuario_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def generar_pdf_ajuste(
    *,
    ajuste_id: int,
    nro_dia: int,
    user_name: str,
    monto: float,
    metodo_desde: str,
    metodo_hacia: str,
    observaciones: str,
    terminal_id: str | None,
    sucursal: str | None,
    fecha: str,
) -> str:
    from fpdf import FPDF

    # Misma carpeta que el resto de comprobantes
    out_dir = os.path.join(get_base_dir(), "comprobantes")
    os.makedirs(out_dir, exist_ok=True)
    try:
        d = datetime.strptime(fecha[:10], "%Y-%m-%d")
        fecha_arch = d.strftime("%d%m%Y")
        fecha_txt = d.strftime("%d/%m/%Y")
    except Exception:
        fecha_arch = datetime.now().strftime("%d%m%Y")
        fecha_txt = datetime.now().strftime("%d/%m/%Y")

    titulo = titulo_ajuste(nro_dia, fecha)
    path = os.path.join(
        out_dir,
        "ajuste_caja_%02d_%s.pdf" % (int(nro_dia or 1), fecha_arch),
    )
    # Si ya existe (reintento), agregar id
    if os.path.exists(path):
        path = os.path.join(
            out_dir,
            "ajuste_caja_%02d_%s_id%s.pdf" % (int(nro_dia or 1), fecha_arch, ajuste_id or 0),
        )

    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _pdf_safe("AJUSTE DE CAJA"), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _pdf_safe(titulo), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 8, _pdf_safe("Correccion de forma de pago"), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    for label, value in [
        ("Sucursal", sucursal or ""),
        ("Terminal", terminal_id or ""),
        ("Cajero", user_name),
        ("Fecha", fecha),
        ("Nro del dia", "%s (%s)" % (nro_dia, fecha_txt)),
        ("ID interno", str(ajuste_id or "-")),
    ]:
        pdf.cell(55, 7, _pdf_safe("%s:" % label), border=0)
        pdf.cell(0, 7, _pdf_safe(value), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _pdf_safe("Movimiento"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    pdf.cell(90, 8, _pdf_safe("Sacar de"), border=1)
    pdf.cell(90, 8, _pdf_safe(metodo_desde), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(90, 8, _pdf_safe("Poner en"), border=1)
    pdf.cell(90, 8, _pdf_safe(metodo_hacia), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(90, 8, _pdf_safe("Monto"), border=1)
    pdf.cell(90, 8, _pdf_safe("$%.2f" % monto), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.multi_cell(0, 7, _pdf_safe("Observaciones: %s" % (observaciones or "Ninguna")))
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 9)
    pdf.multi_cell(
        0,
        5,
        _pdf_safe(
            "Este comprobante no es fiscal. Solo corrige el medio de pago "
            "para el cierre de caja del dia."
        ),
    )
    pdf.output(path)

    # Validación mínima: debe empezar con %PDF
    with open(path, "rb") as fh:
        head = fh.read(5)
    if head != b"%PDF-":
        raise ValueError("El PDF de ajuste no se genero correctamente: %s" % path)
    return path
