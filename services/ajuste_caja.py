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
        # Generar PDF también en la PC cliente
        pdf_path = generar_pdf_ajuste(
            ajuste_id=data.get("ajuste_id") or 0,
            user_name=user_name,
            monto=monto,
            metodo_desde=desde,
            metodo_hacia=hacia,
            observaciones=payload["observaciones"],
            terminal_id=payload["terminal_id"],
            sucursal=payload["sucursal"],
            fecha=data.get("fecha") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        data["pdf_path"] = pdf_path
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
    cfg = load_config()
    terminal_id = terminal_id or cfg.get("terminal_id")
    sucursal = sucursal or cfg.get("sucursal_nombre")
    obs = observaciones or "Ajuste de forma de pago"

    pdf_path = generar_pdf_ajuste(
        ajuste_id=0,
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
        c.execute(
            """
            INSERT INTO ajustes_caja (
                usuario_id, fecha, monto, metodo_desde, metodo_hacia,
                observaciones, pdf_path, terminal_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (usuario_id, ahora, monto, desde, hacia, obs, pdf_path, terminal_id),
        )
        ajuste_id = c.lastrowid
        # Renombrar PDF con id real si hace falta
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "ok": True,
        "ajuste_id": ajuste_id,
        "fecha": ahora,
        "monto": monto,
        "metodo_desde": desde,
        "metodo_hacia": hacia,
        "pdf_path": pdf_path,
    }


def listar_ajustes_pendientes(usuario_id: int, fecha: str) -> list[dict]:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, fecha, monto, metodo_desde, metodo_hacia, observaciones, terminal_id
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

    reportes = os.path.join(get_base_dir(), "reportes")
    os.makedirs(reportes, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(reportes, "ajuste_caja_%s_%s.pdf" % (stamp, ajuste_id or "tmp"))

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "AJUSTE DE CAJA", ln=1, align="C")
    pdf.set_font("Arial", size=11)
    pdf.cell(0, 8, "ROD POS - Correccion de forma de pago", ln=1, align="C")
    pdf.ln(6)
    for label, value in [
        ("Sucursal", sucursal or ""),
        ("Terminal", terminal_id or ""),
        ("Cajero", user_name),
        ("Fecha", fecha),
        ("Nro ajuste", str(ajuste_id or "-")),
    ]:
        pdf.cell(55, 7, "%s:" % label, border=0)
        pdf.cell(0, 7, str(value), ln=1)

    pdf.ln(6)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Movimiento", ln=1)
    pdf.set_font("Arial", size=11)
    pdf.cell(90, 8, "Sacar de", border=1)
    pdf.cell(90, 8, metodo_desde, border=1, ln=1)
    pdf.cell(90, 8, "Poner en", border=1)
    pdf.cell(90, 8, metodo_hacia, border=1, ln=1)
    pdf.cell(90, 8, "Monto", border=1)
    pdf.cell(90, 8, "$%.2f" % monto, border=1, ln=1)
    pdf.ln(6)
    pdf.multi_cell(0, 7, "Observaciones: %s" % (observaciones or "Ninguna"))
    pdf.ln(8)
    pdf.set_font("Arial", "I", 9)
    pdf.multi_cell(
        0,
        5,
        "Este comprobante no es fiscal. Solo corrige el medio de pago "
        "para el cierre de caja del dia.",
    )
    pdf.output(path)
    return path
