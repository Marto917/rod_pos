"""Operaciones de stock atómicas + auditoría (local o vía LAN)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from db import get_connection
from pos_config import is_client_mode, load_config, server_base_url
import urllib.parse


class StockError(Exception):
    pass


def _http_json(method: str, path: str, payload: dict | None = None, timeout: float = 15.0) -> dict:
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
        raise StockError(msg) from e
    except Exception as e:
        raise StockError("No se pudo conectar al servidor LAN: %s" % e) from e


def get_product_by_barcode(codigo: str) -> dict | None:
    codigo = (codigo or "").strip()
    if not codigo:
        return None
    if is_client_mode():
        data = _http_json("GET", "/api/productos/barcode/%s" % urllib.parse.quote(codigo))
        return data.get("producto")
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, codigo_barras, nombre, categoria, cantidad, precio_lista, precio_publico
            FROM productos WHERE codigo_barras = ?
            """,
            (codigo,),
        )
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_products(q: str = "") -> list[dict]:
    if is_client_mode():
        data = _http_json("GET", "/api/productos?q=%s" % urllib.parse.quote(q or ""))
        return data.get("productos") or []
    conn = get_connection()
    try:
        c = conn.cursor()
        if q:
            like = "%%%s%%" % q
            c.execute(
                """
                SELECT id, codigo_barras, nombre, categoria, cantidad, precio_lista, precio_publico
                FROM productos
                WHERE codigo_barras LIKE ? OR nombre LIKE ?
                ORDER BY nombre
                LIMIT 500
                """,
                (like, like),
            )
        else:
            c.execute(
                """
                SELECT id, codigo_barras, nombre, categoria, cantidad, precio_lista, precio_publico
                FROM productos
                ORDER BY nombre
                LIMIT 500
                """
            )
        return [dict(r) for r in c.fetchall()]
    finally:
        conn.close()


def adjust_stock(
    producto_id: int,
    delta: int,
    *,
    motivo: str,
    usuario_id: int | None = None,
    referencia: str | None = None,
    allow_negative: bool = False,
) -> dict:
    cfg = load_config()
    payload = {
        "producto_id": producto_id,
        "delta": int(delta),
        "motivo": motivo,
        "usuario_id": usuario_id,
        "referencia": referencia,
        "terminal_id": cfg.get("terminal_id"),
        "allow_negative": allow_negative,
    }
    if is_client_mode():
        data = _http_json("POST", "/api/stock/adjust", payload)
        if not data.get("ok"):
            raise StockError(data.get("error") or "Error de stock")
        return data

    return adjust_stock_local(**payload)


def adjust_stock_local(
    producto_id: int,
    delta: int,
    *,
    motivo: str,
    usuario_id: int | None = None,
    referencia: str | None = None,
    terminal_id: str | None = None,
    allow_negative: bool = False,
) -> dict:
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        c.execute("SELECT id, nombre, cantidad FROM productos WHERE id = ?", (producto_id,))
        row = c.fetchone()
        if not row:
            conn.rollback()
            raise StockError("Producto no encontrado")
        stock_antes = int(row["cantidad"] or 0)
        stock_despues = stock_antes + int(delta)
        if stock_despues < 0 and not allow_negative:
            conn.rollback()
            raise StockError(
                "Stock insuficiente para %s (hay %d, se pidió %d)"
                % (row["nombre"], stock_antes, abs(int(delta)))
            )
        c.execute("UPDATE productos SET cantidad = ? WHERE id = ?", (stock_despues, producto_id))
        c.execute(
            """
            INSERT INTO stock_movimientos (
                producto_id, delta, stock_antes, stock_despues,
                motivo, referencia, usuario_id, terminal_id, fecha
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
            """,
            (
                producto_id,
                int(delta),
                stock_antes,
                stock_despues,
                motivo,
                referencia,
                usuario_id,
                terminal_id,
            ),
        )
        conn.commit()
        return {
            "ok": True,
            "producto_id": producto_id,
            "stock_antes": stock_antes,
            "stock_despues": stock_despues,
        }
    except StockError:
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_recepcion_local(data: dict) -> dict:
    """Alta o suma de stock por recepción (solo servidor/local)."""
    conn = get_connection()
    try:
        c = conn.cursor()
        codigo = data["codigo_barras"]
        cantidad = int(data["cantidad"])
        c.execute("BEGIN IMMEDIATE")
        c.execute("SELECT id, cantidad FROM productos WHERE codigo_barras = ?", (codigo,))
        row = c.fetchone()
        if row:
            pid = row["id"]
            stock_antes = int(row["cantidad"] or 0)
            stock_despues = stock_antes + cantidad
            c.execute(
                """
                UPDATE productos
                SET cantidad = ?, nombre = ?, precio_lista = ?, precio_publico = ?
                WHERE id = ?
                """,
                (
                    stock_despues,
                    data["nombre"],
                    float(data["precio_lista"]),
                    float(data["precio_publico"]),
                    pid,
                ),
            )
        else:
            c.execute(
                """
                INSERT INTO productos (codigo_barras, nombre, cantidad, precio_lista, precio_publico, categoria)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    codigo,
                    data["nombre"],
                    cantidad,
                    float(data["precio_lista"]),
                    float(data["precio_publico"]),
                    data.get("categoria") or "GENERAL",
                ),
            )
            pid = c.lastrowid
            stock_antes = 0
            stock_despues = cantidad
        c.execute(
            """
            INSERT INTO stock_movimientos (
                producto_id, delta, stock_antes, stock_despues,
                motivo, referencia, usuario_id, terminal_id, fecha
            ) VALUES (?, ?, ?, ?, 'RECEPCION', ?, ?, ?, datetime('now','localtime'))
            """,
            (
                pid,
                cantidad,
                stock_antes,
                stock_despues,
                data.get("referencia"),
                data.get("usuario_id"),
                data.get("terminal_id"),
            ),
        )
        conn.commit()
        return {"ok": True, "producto_id": pid, "stock_despues": stock_despues}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def recepcion_producto(data: dict) -> dict:
    cfg = load_config()
    payload = dict(data)
    payload["terminal_id"] = cfg.get("terminal_id")
    if is_client_mode():
        result = _http_json("POST", "/api/stock/recepcion", payload)
        if not result.get("ok"):
            raise StockError(result.get("error") or "Error en recepción")
        return result
    return upsert_recepcion_local(payload)


def crear_venta_local(payload: dict) -> dict:
    """Registra venta + descuenta stock de forma atómica."""
    from datetime import datetime

    items = payload.get("items") or []
    pagos = payload.get("pagos") or []
    # Se permite venta sin líneas de stock (ej. solo descuento / ítems manuales sin id)

    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        fecha = payload.get("fecha") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            """
            INSERT INTO ventas (usuario_id, total, fecha, metodo_pago, terminal_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                payload["usuario_id"],
                float(payload["total"]),
                fecha,
                payload.get("metodo_pago"),
                payload.get("terminal_id"),
            ),
        )
        venta_id = c.lastrowid

        # Desglose de pago mixto (o un solo método explícito)
        for p in pagos:
            metodo = str(p.get("metodo") or "").strip().upper()
            try:
                monto = float(p.get("monto") or 0)
            except Exception:
                monto = 0.0
            if not metodo or monto <= 0:
                continue
            c.execute(
                "INSERT INTO venta_pagos (venta_id, metodo, monto) VALUES (?, ?, ?)",
                (venta_id, metodo, round(monto, 2)),
            )

        for item in items:
            pid = item.get("producto_id") or item.get("id")
            if not pid:
                continue
            cant = int(item.get("cantidad") or 1)
            precio = float(item.get("precio") or 0)
            c.execute("SELECT cantidad, nombre FROM productos WHERE id = ?", (pid,))
            row = c.fetchone()
            if not row:
                conn.rollback()
                raise StockError("Producto id=%s no existe" % pid)
            stock_antes = int(row["cantidad"] or 0)
            if stock_antes < cant:
                conn.rollback()
                raise StockError(
                    "Stock insuficiente: %s (hay %d)" % (row["nombre"], stock_antes)
                )
            stock_despues = stock_antes - cant
            c.execute(
                "INSERT INTO detalle_ventas (venta_id, producto_id, cantidad, precio_unitario) VALUES (?, ?, ?, ?)",
                (venta_id, pid, cant, precio),
            )
            c.execute("UPDATE productos SET cantidad = ? WHERE id = ?", (stock_despues, pid))
            c.execute(
                """
                INSERT INTO stock_movimientos (
                    producto_id, delta, stock_antes, stock_despues,
                    motivo, referencia, usuario_id, terminal_id, fecha
                ) VALUES (?, ?, ?, ?, 'VENTA', ?, ?, ?, ?)
                """,
                (
                    pid,
                    -cant,
                    stock_antes,
                    stock_despues,
                    str(venta_id),
                    payload.get("usuario_id"),
                    payload.get("terminal_id"),
                    fecha,
                ),
            )
        conn.commit()
        return {"ok": True, "venta_id": venta_id}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_sale(
    *,
    usuario_id: int,
    total: float,
    metodo_pago: str,
    items: list[dict],
    fecha: str | None = None,
    pagos: list[dict] | None = None,
) -> dict:
    """Crea venta y descuenta stock (local o servidor LAN)."""
    from datetime import datetime

    cfg = load_config()
    payload = {
        "usuario_id": usuario_id,
        "total": float(total),
        "metodo_pago": metodo_pago,
        "items": items,
        "fecha": fecha or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "terminal_id": cfg.get("terminal_id"),
        "pagos": pagos or [],
    }
    if is_client_mode():
        data = _http_json("POST", "/api/ventas", payload)
        if not data.get("ok"):
            raise StockError(data.get("error") or "No se pudo registrar la venta")
        return data

    return crear_venta_local(payload)


def anular_venta_local(venta_id: int, *, usuario_id: int | None = None, motivo: str = "ANULACION") -> dict:
    """Revierte stock, borra detalle/pendientes fiscales y elimina la venta."""
    from datetime import datetime

    cfg = load_config()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        c.execute("SELECT id FROM ventas WHERE id=?", (venta_id,))
        if not c.fetchone():
            conn.rollback()
            raise StockError("La venta #%s no existe" % venta_id)

        c.execute(
            "SELECT producto_id, cantidad FROM detalle_ventas WHERE venta_id=? AND producto_id IS NOT NULL",
            (venta_id,),
        )
        detalles = c.fetchall()
        for row in detalles:
            pid = int(row["producto_id"])
            cant = int(row["cantidad"] or 0)
            if cant <= 0:
                continue
            c.execute("SELECT cantidad, nombre FROM productos WHERE id=?", (pid,))
            prod = c.fetchone()
            if not prod:
                continue
            stock_antes = int(prod["cantidad"] or 0)
            stock_despues = stock_antes + cant
            c.execute("UPDATE productos SET cantidad=? WHERE id=?", (stock_despues, pid))
            c.execute(
                """
                INSERT INTO stock_movimientos (
                    producto_id, delta, stock_antes, stock_despues,
                    motivo, referencia, usuario_id, terminal_id, fecha
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid,
                    cant,
                    stock_antes,
                    stock_despues,
                    motivo or "ANULACION",
                    str(venta_id),
                    usuario_id,
                    cfg.get("terminal_id"),
                    ahora,
                ),
            )

        c.execute("DELETE FROM detalle_ventas WHERE venta_id=?", (venta_id,))
        try:
            c.execute("DELETE FROM venta_pagos WHERE venta_id=?", (venta_id,))
        except Exception:
            pass
        c.execute("DELETE FROM fiscal_pendientes WHERE venta_id=?", (venta_id,))
        c.execute("DELETE FROM ventas WHERE id=?", (venta_id,))
        conn.commit()
        return {"ok": True, "venta_id": venta_id}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def anular_venta(venta_id: int, *, usuario_id: int | None = None, motivo: str = "ANULACION") -> dict:
    if is_client_mode():
        data = _http_json(
            "POST",
            "/api/ventas/anular",
            {
                "venta_id": int(venta_id),
                "usuario_id": usuario_id,
                "motivo": motivo or "ANULACION",
            },
        )
        if not data.get("ok"):
            raise StockError(data.get("error") or "No se pudo anular la venta")
        return data
    return anular_venta_local(venta_id, usuario_id=usuario_id, motivo=motivo)


def enqueue_fiscal(venta_id: int, payload: dict) -> dict:
    if is_client_mode():
        data = _http_json(
            "POST",
            "/api/fiscal/enqueue",
            {"venta_id": venta_id, "payload": payload},
        )
        if not data.get("ok"):
            raise StockError(data.get("error") or "No se pudo encolar fiscal")
        return data
    from fiscal_service import emitir_o_encolar

    ok, res = emitir_o_encolar(venta_id, payload)
    return {"ok": ok, "result": res}


def healthcheck() -> dict[str, Any]:
    if is_client_mode():
        return _http_json("GET", "/api/health")
    return {"ok": True, "modo": "local"}
