"""Lógica de cierre de caja profesional."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

from db import get_connection
from pos_config import is_client_mode, load_config, server_base_url
from services.xlsx_writer import write_xlsx


def _money(value) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _http_json(method: str, path: str, payload: dict | None = None, timeout: float = 30.0) -> dict:
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


def resumen_pendiente(usuario_id: int, fecha: str | None = None) -> dict[str, Any]:
    """Ventas del día aún no incluidas en un cierre."""
    fecha = fecha or datetime.now().strftime("%Y-%m-%d")
    if is_client_mode():
        q = urllib.parse.urlencode({"usuario_id": usuario_id, "fecha": fecha})
        data = _http_json("GET", "/api/cierre/resumen?%s" % q)
        if not data.get("ok"):
            raise ValueError(data.get("error") or "Error al leer cierre")
        return data["resumen"]

    return resumen_pendiente_local(usuario_id, fecha)


def _norm_metodo_pago(metodo: str | None) -> str:
    """Unifica variantes viejas a EFECTIVO / TARJETA / MERCADOPAGO."""
    m = (metodo or "").upper().strip()
    m = (
        m.replace("Á", "A")
        .replace("É", "E")
        .replace("Í", "I")
        .replace("Ó", "O")
        .replace("Ú", "U")
    )
    if m == "EFECTIVO":
        return "EFECTIVO"
    if m == "MIXTO":
        return "MIXTO"
    if "MERCADO" in m or m in ("MP", "MERCADOPAGO"):
        return "MERCADOPAGO"
    if "TARJETA" in m or "DEBITO" in m or "CREDITO" in m:
        return "TARJETA"
    return m or "OTROS"


def _fmt_pagos_label(metodo: str, pagos: list[dict] | None) -> str:
    """Etiqueta para listados: MIXTO (E 500.00 + T 300.00)."""
    m = _norm_metodo_pago(metodo)
    if m != "MIXTO" or not pagos:
        return m
    short = {"EFECTIVO": "E", "TARJETA": "T", "MERCADOPAGO": "MP"}
    parts = []
    for p in pagos:
        met = _norm_metodo_pago(p.get("metodo"))
        mon = _money(p.get("monto"))
        if mon <= 0:
            continue
        parts.append("%s %.2f" % (short.get(met, met[:2]), mon))
    if not parts:
        return "MIXTO"
    return "MIXTO (%s)" % " + ".join(parts)


def resumen_pendiente_local(usuario_id: int, fecha: str) -> dict[str, Any]:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, fecha, total, metodo_pago, terminal_id
            FROM ventas
            WHERE date(fecha)=?
              AND usuario_id=?
              AND COALESCE(es_ajuste, 0)=0
              AND arqueo_id IS NULL
            ORDER BY fecha ASC
            """,
            (fecha, usuario_id),
        )
        ventas_raw = [dict(row) for row in c.fetchall()]
        ids = [int(v["id"]) for v in ventas_raw]
        pagos_por_venta: dict[int, list[dict]] = {i: [] for i in ids}
        if ids:
            placeholders = ",".join("?" for _ in ids)
            try:
                c.execute(
                    "SELECT venta_id, metodo, monto FROM venta_pagos WHERE venta_id IN (%s)"
                    % placeholders,
                    ids,
                )
                for row in c.fetchall():
                    vid = int(row["venta_id"])
                    pagos_por_venta.setdefault(vid, []).append(
                        {
                            "metodo": _norm_metodo_pago(row["metodo"]),
                            "monto": _money(row["monto"]),
                        }
                    )
            except Exception:
                # Base vieja sin tabla venta_pagos
                pagos_por_venta = {i: [] for i in ids}

        ventas = []
        for v in ventas_raw:
            v = dict(v)
            vid = int(v["id"])
            metodo = _norm_metodo_pago(v.get("metodo_pago"))
            pagos = pagos_por_venta.get(vid) or []
            # Si no hay filas en venta_pagos, tratar como pago único
            if not pagos and metodo and metodo != "MIXTO":
                pagos = [{"metodo": metodo, "monto": _money(v.get("total"))}]
            v["metodo_pago"] = metodo
            v["pagos"] = pagos
            v["metodo_label"] = _fmt_pagos_label(metodo, pagos)
            ventas.append(v)

        por_metodo: dict[str, dict[str, float]] = {}
        for v in ventas:
            pagos = v.get("pagos") or []
            if v["metodo_pago"] == "MIXTO" and pagos:
                for p in pagos:
                    met = _norm_metodo_pago(p.get("metodo"))
                    mon = _money(p.get("monto"))
                    if mon <= 0:
                        continue
                    bucket = por_metodo.setdefault(met, {"tickets": 0, "total": 0.0})
                    bucket["tickets"] += 1
                    bucket["total"] += mon
            else:
                metodo = v["metodo_pago"]
                if metodo == "MIXTO":
                    # MIXTO sin desglose: va a OTROS para no distorsionar
                    metodo = "OTROS"
                bucket = por_metodo.setdefault(metodo, {"tickets": 0, "total": 0.0})
                bucket["tickets"] += 1
                bucket["total"] += _money(v.get("total"))

        from services.ajuste_caja import aplicar_ajustes_a_por_metodo, listar_ajustes_pendientes

        ajustes = listar_ajustes_pendientes(usuario_id, fecha)
        por_metodo = aplicar_ajustes_a_por_metodo(por_metodo, ajustes)

        total_sistema = sum(b["total"] for b in por_metodo.values())
        efectivo_sistema = _money(por_metodo.get("EFECTIVO", {}).get("total", 0))
        tarjeta_sistema = _money(por_metodo.get("TARJETA", {}).get("total", 0))
        mercadopago_sistema = _money(por_metodo.get("MERCADOPAGO", {}).get("total", 0))
        otros_sistema = _money(
            total_sistema - efectivo_sistema - tarjeta_sistema - mercadopago_sistema
        )

        return {
            "fecha": fecha,
            "ventas": ventas,
            "ajustes": ajustes,
            "por_metodo": por_metodo,
            "cantidad_tickets": len(ventas),
            "cantidad_ajustes": len(ajustes),
            "total_sistema": _money(total_sistema),
            "efectivo_sistema": efectivo_sistema,
            "tarjeta_sistema": tarjeta_sistema,
            "mercadopago_sistema": mercadopago_sistema,
            "otros_sistema": otros_sistema,
        }
    finally:
        conn.close()


def cerrar_caja(
    usuario_id: int,
    user_name: str,
    efectivo_contado: float,
    fondo_inicial: float = 0.0,
    observaciones: str = "",
    fecha: str | None = None,
    reportes_dir: str | None = None,
) -> dict[str, Any]:
    if is_client_mode():
        data = _http_json(
            "POST",
            "/api/cierre",
            {
                "usuario_id": usuario_id,
                "user_name": user_name,
                "efectivo_contado": efectivo_contado,
                "fondo_inicial": fondo_inicial,
                "observaciones": observaciones,
                "fecha": fecha,
            },
        )
        if not data.get("ok"):
            raise ValueError(data.get("error") or "No se pudo cerrar la caja")
        resumen = data.get("resumen_snapshot") or data.get("resumen")
        if not resumen:
            raise ValueError("El servidor no devolvió el detalle del cierre.")
        cfg = load_config()
        ahora = datetime.now()
        stamp = ahora.strftime("%Y%m%d_%H%M%S")
        base_dir = reportes_dir or os_path_reportes()
        os_makedirs(base_dir)
        excel_path = os_path_join(base_dir, "cierre_%s_%s.xlsx" % (stamp, sanitize(user_name)))
        pdf_path = os_path_join(base_dir, "cierre_%s_%s.pdf" % (stamp, sanitize(user_name)))
        generar_excel_cierre(
            excel_path,
            user_name=user_name,
            cfg=cfg,
            resumen=resumen,
            efectivo_contado=_money(efectivo_contado),
            fondo_inicial=_money(fondo_inicial),
            diferencia=_money(data.get("diferencia")),
            observaciones=observaciones,
            cerrado_en=ahora.strftime("%Y-%m-%d %H:%M:%S"),
        )
        generar_pdf_cierre(
            pdf_path,
            user_name=user_name,
            cfg=cfg,
            resumen=resumen,
            efectivo_contado=_money(efectivo_contado),
            fondo_inicial=_money(fondo_inicial),
            diferencia=_money(data.get("diferencia")),
            observaciones=observaciones,
            cerrado_en=ahora.strftime("%Y-%m-%d %H:%M:%S"),
        )
        data["excel_path"] = excel_path
        data["pdf_path"] = pdf_path
        return data

    return cerrar_caja_local(
        usuario_id=usuario_id,
        user_name=user_name,
        efectivo_contado=efectivo_contado,
        fondo_inicial=fondo_inicial,
        observaciones=observaciones,
        fecha=fecha,
        reportes_dir=reportes_dir,
    )


def cerrar_caja_local(
    usuario_id: int,
    user_name: str,
    efectivo_contado: float,
    fondo_inicial: float = 0.0,
    observaciones: str = "",
    fecha: str | None = None,
    reportes_dir: str | None = None,
) -> dict[str, Any]:
    cfg = load_config()
    fecha = fecha or datetime.now().strftime("%Y-%m-%d")
    resumen = resumen_pendiente_local(usuario_id, fecha)
    if resumen["cantidad_tickets"] == 0 and resumen.get("cantidad_ajustes", 0) == 0:
        raise ValueError("No hay ventas ni ajustes pendientes de cierre para esta fecha.")

    ahora = datetime.now()
    stamp = ahora.strftime("%Y%m%d_%H%M%S")
    base_dir = reportes_dir or os_path_reportes()
    os_makedirs(base_dir)

    efectivo_contado = _money(efectivo_contado)
    fondo_inicial = _money(fondo_inicial)
    esperado_efectivo = _money(resumen["efectivo_sistema"] + fondo_inicial)
    diferencia = _money(efectivo_contado - esperado_efectivo)

    excel_path = os_path_join(base_dir, "cierre_%s_%s.xlsx" % (stamp, sanitize(user_name)))
    pdf_path = os_path_join(base_dir, "cierre_%s_%s.pdf" % (stamp, sanitize(user_name)))

    generar_excel_cierre(
        excel_path,
        user_name=user_name,
        cfg=cfg,
        resumen=resumen,
        efectivo_contado=efectivo_contado,
        fondo_inicial=fondo_inicial,
        diferencia=diferencia,
        observaciones=observaciones,
        cerrado_en=ahora.strftime("%Y-%m-%d %H:%M:%S"),
    )
    generar_pdf_cierre(
        pdf_path,
        user_name=user_name,
        cfg=cfg,
        resumen=resumen,
        efectivo_contado=efectivo_contado,
        fondo_inicial=fondo_inicial,
        diferencia=diferencia,
        observaciones=observaciones,
        cerrado_en=ahora.strftime("%Y-%m-%d %H:%M:%S"),
    )

    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO arqueos_caja (
                usuario_id, fecha, efectivo, tarjeta, otros,
                total_sistema, diferencia, observaciones,
                efectivo_contado, fondo_inicial, terminal_id, sucursal,
                cantidad_tickets, fecha_desde, fecha_hasta, archivo_excel, archivo_pdf
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usuario_id,
                ahora.strftime("%Y-%m-%d %H:%M:%S"),
                resumen["efectivo_sistema"],
                resumen["tarjeta_sistema"],
                _money(resumen.get("mercadopago_sistema", 0) + resumen.get("otros_sistema", 0)),
                resumen["total_sistema"],
                diferencia,
                observaciones or "Ninguna",
                efectivo_contado,
                fondo_inicial,
                cfg.get("terminal_id"),
                cfg.get("sucursal_nombre"),
                resumen["cantidad_tickets"],
                fecha + " 00:00:00",
                fecha + " 23:59:59",
                excel_path,
                pdf_path,
            ),
        )
        arqueo_id = c.lastrowid
        venta_ids = [v["id"] for v in resumen["ventas"]]
        if venta_ids:
            placeholders = ",".join("?" for _ in venta_ids)
            c.execute(
                "UPDATE ventas SET es_ajuste=1, arqueo_id=? WHERE id IN (%s)" % placeholders,
                [arqueo_id, *venta_ids],
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    from services.ajuste_caja import marcar_ajustes_en_arqueo

    marcar_ajustes_en_arqueo(usuario_id, fecha, arqueo_id)

    return {
        "ok": True,
        "arqueo_id": arqueo_id,
        "excel_path": excel_path,
        "pdf_path": pdf_path,
        "diferencia": diferencia,
        "resumen": resumen,
        "resumen_snapshot": resumen,
    }


def generar_excel_cierre(
    path: str,
    *,
    user_name: str,
    cfg: dict,
    resumen: dict,
    efectivo_contado: float,
    fondo_inicial: float,
    diferencia: float,
    observaciones: str,
    cerrado_en: str,
) -> str:
    resumen_rows = [
        ["CIERRE DE CAJA - ROD POS"],
        [],
        ["Sucursal", cfg.get("sucursal_nombre", "")],
        ["Terminal", cfg.get("terminal_id", "")],
        ["Cajero", user_name],
        ["Fecha operativa", resumen["fecha"]],
        ["Cerrado en", cerrado_en],
        [],
        ["RESUMEN POR MÉTODO"],
        ["Método de pago", "Tickets", "Total sistema"],
    ]
    for metodo, data in sorted(resumen["por_metodo"].items()):
        resumen_rows.append([metodo, data["tickets"], _money(data["total"])])

    resumen_rows.extend(
        [
            [],
            ["TOTAL SISTEMA", "", resumen["total_sistema"]],
            ["Tickets", "", resumen["cantidad_tickets"]],
            ["Ajustes de caja", "", resumen.get("cantidad_ajustes", 0)],
            [],
            ["POR MEDIO DE PAGO"],
            ["Efectivo", "", resumen.get("efectivo_sistema", 0)],
            ["Tarjeta", "", resumen.get("tarjeta_sistema", 0)],
            ["Mercado Pago", "", resumen.get("mercadopago_sistema", 0)],
            ["Otros", "", resumen.get("otros_sistema", 0)],
            [],
            ["ARQUEO DE EFECTIVO"],
            ["Fondo inicial", fondo_inicial],
            ["Efectivo ventas (sistema)", resumen["efectivo_sistema"]],
            ["Efectivo esperado", _money(fondo_inicial + resumen["efectivo_sistema"])],
            ["Efectivo contado", efectivo_contado],
            ["Diferencia", diferencia],
            [],
            ["Observaciones", observaciones or "Ninguna"],
        ]
    )

    detalle_rows = [
        ["ID venta", "Fecha/hora", "Método", "Total", "Terminal"],
    ]
    for v in resumen["ventas"]:
        detalle_rows.append(
            [
                v["id"],
                v["fecha"],
                v.get("metodo_label") or v.get("metodo_pago") or "",
                _money(v.get("total")),
                v.get("terminal_id") or "",
            ]
        )

    ajustes_rows = [
        ["ID", "Fecha/hora", "Monto", "Desde", "Hacia", "Observaciones"],
    ]
    for aj in resumen.get("ajustes") or []:
        ajustes_rows.append(
            [
                aj.get("id"),
                aj.get("fecha"),
                _money(aj.get("monto")),
                aj.get("metodo_desde"),
                aj.get("metodo_hacia"),
                aj.get("observaciones") or "",
            ]
        )

    write_xlsx(
        path,
        {
            "Resumen": resumen_rows,
            "Detalle ventas": detalle_rows,
            "Ajustes caja": ajustes_rows,
        },
    )
    return path


def generar_pdf_cierre(
    path: str,
    *,
    user_name: str,
    cfg: dict,
    resumen: dict,
    efectivo_contado: float,
    fondo_inicial: float,
    diferencia: float,
    observaciones: str,
    cerrado_en: str,
) -> str:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "CIERRE DE CAJA", ln=1, align="C")
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 6, "ROD POS", ln=1, align="C")
    pdf.ln(4)
    for label, value in [
        ("Sucursal", cfg.get("sucursal_nombre", "")),
        ("Terminal", cfg.get("terminal_id", "")),
        ("Cajero", user_name),
        ("Fecha", resumen["fecha"]),
        ("Cerrado", cerrado_en),
    ]:
        pdf.cell(50, 6, "%s:" % label, border=0)
        pdf.cell(0, 6, str(value), ln=1)

    pdf.ln(4)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, "Ventas por metodo", ln=1)
    pdf.set_font("Arial", size=10)
    pdf.cell(80, 7, "Metodo", border=1)
    pdf.cell(30, 7, "Tickets", border=1)
    pdf.cell(40, 7, "Total", border=1, ln=1)
    for metodo, data in sorted(resumen["por_metodo"].items()):
        pdf.cell(80, 7, metodo, border=1)
        pdf.cell(30, 7, str(data["tickets"]), border=1)
        pdf.cell(40, 7, "$%.2f" % data["total"], border=1, ln=1)

    pdf.ln(6)
    pdf.cell(80, 7, "Total sistema", border=1)
    pdf.cell(70, 7, "$%.2f" % resumen["total_sistema"], border=1, ln=1)
    pdf.cell(80, 7, "Efectivo", border=1)
    pdf.cell(70, 7, "$%.2f" % resumen.get("efectivo_sistema", 0), border=1, ln=1)
    pdf.cell(80, 7, "Tarjeta", border=1)
    pdf.cell(70, 7, "$%.2f" % resumen.get("tarjeta_sistema", 0), border=1, ln=1)
    pdf.cell(80, 7, "Mercado Pago", border=1)
    pdf.cell(70, 7, "$%.2f" % resumen.get("mercadopago_sistema", 0), border=1, ln=1)
    pdf.cell(80, 7, "Fondo inicial", border=1)
    pdf.cell(70, 7, "$%.2f" % fondo_inicial, border=1, ln=1)
    pdf.cell(80, 7, "Efectivo contado", border=1)
    pdf.cell(70, 7, "$%.2f" % efectivo_contado, border=1, ln=1)
    pdf.cell(80, 7, "Diferencia", border=1)
    pdf.cell(70, 7, "$%.2f" % diferencia, border=1, ln=1)

    ajustes = resumen.get("ajustes") or []
    if ajustes:
        pdf.ln(6)
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 8, "Ajustes de caja (%d)" % len(ajustes), ln=1)
        pdf.set_font("Arial", size=9)
        pdf.cell(25, 6, "Monto", border=1)
        pdf.cell(40, 6, "Desde", border=1)
        pdf.cell(40, 6, "Hacia", border=1)
        pdf.cell(75, 6, "Obs", border=1, ln=1)
        for aj in ajustes:
            pdf.cell(25, 6, "$%.2f" % _money(aj.get("monto")), border=1)
            pdf.cell(40, 6, str(aj.get("metodo_desde") or "")[:14], border=1)
            pdf.cell(40, 6, str(aj.get("metodo_hacia") or "")[:14], border=1)
            pdf.cell(75, 6, str(aj.get("observaciones") or "")[:32], border=1, ln=1)

    pdf.ln(4)
    pdf.multi_cell(0, 6, "Observaciones: %s" % (observaciones or "Ninguna"))
    pdf.output(path)
    return path


def sanitize(name: str) -> str:
    keep = []
    for ch in (name or "caja"):
        if ch.isalnum() or ch in ("-", "_"):
            keep.append(ch)
        elif ch.isspace():
            keep.append("_")
    return "".join(keep)[:40] or "caja"


def os_path_reportes() -> str:
    from db_init import get_base_dir
    import os

    return os.path.join(get_base_dir(), "reportes")


def os_makedirs(path: str) -> None:
    import os

    os.makedirs(path, exist_ok=True)


def os_path_join(*parts: str) -> str:
    import os

    return os.path.join(*parts)
