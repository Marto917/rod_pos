"""
Servidor LAN de ROD POS.

La PC en modo 'servidor' expone la base SQLite para que otras cajas
(en modo 'cliente') compartan stock y ventas.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from db import get_connection
from pos_config import load_config
from services.stock_ops import (
    StockError,
    adjust_stock_local,
    crear_venta_local,
    upsert_recepcion_local,
)

_server_thread: threading.Thread | None = None
_httpd: ThreadingHTTPServer | None = None


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


class PosLanHandler(BaseHTTPRequestHandler):
    server_version = "RodPOS-LAN/1.0"

    def log_message(self, fmt, *args):  # silencio en consola de caja
        return

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/health":
                cfg = load_config()
                return _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "modo": "servidor",
                        "sucursal": cfg.get("sucursal_nombre"),
                        "terminal": cfg.get("terminal_id"),
                    },
                )

            if path == "/api/cierre/resumen":
                qs = parse_qs(parsed.query)
                usuario_id = int((qs.get("usuario_id") or ["0"])[0])
                fecha = (qs.get("fecha") or [None])[0]
                from services.cierre_caja import resumen_pendiente_local
                from datetime import datetime as _dt

                fecha = fecha or _dt.now().strftime("%Y-%m-%d")
                resumen = resumen_pendiente_local(usuario_id, fecha)
                return _json_response(self, 200, {"ok": True, "resumen": resumen})

            if path.startswith("/api/productos/barcode/"):
                codigo = unquote(path.split("/api/productos/barcode/", 1)[1])
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
                    return _json_response(
                        self, 200, {"producto": dict(row) if row else None}
                    )
                finally:
                    conn.close()

            if path == "/api/productos":
                q = (parse_qs(parsed.query).get("q") or [""])[0]
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
                            ORDER BY nombre LIMIT 500
                            """,
                            (like, like),
                        )
                    else:
                        c.execute(
                            """
                            SELECT id, codigo_barras, nombre, categoria, cantidad, precio_lista, precio_publico
                            FROM productos ORDER BY nombre LIMIT 500
                            """
                        )
                    return _json_response(
                        self, 200, {"productos": [dict(r) for r in c.fetchall()]}
                    )
                finally:
                    conn.close()

            return _json_response(self, 404, {"error": "Ruta no encontrada"})
        except Exception as e:
            return _json_response(self, 500, {"error": str(e)})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = _read_json(self)
            if path == "/api/stock/adjust":
                result = adjust_stock_local(
                    int(payload["producto_id"]),
                    int(payload["delta"]),
                    motivo=str(payload.get("motivo") or "AJUSTE"),
                    usuario_id=payload.get("usuario_id"),
                    referencia=payload.get("referencia"),
                    terminal_id=payload.get("terminal_id"),
                    allow_negative=bool(payload.get("allow_negative")),
                )
                return _json_response(self, 200, result)

            if path == "/api/stock/recepcion":
                result = upsert_recepcion_local(payload)
                return _json_response(self, 200, result)

            if path == "/api/ventas":
                result = crear_venta_local(payload)
                return _json_response(self, 200, result)

            if path == "/api/fiscal/enqueue":
                from fiscal_service import emitir_o_encolar

                venta_id = int(payload["venta_id"])
                fiscal_payload = payload.get("payload") or {}
                ok, res = emitir_o_encolar(venta_id, fiscal_payload)
                return _json_response(self, 200, {"ok": ok, "result": res})

            if path == "/api/cierre":
                from services.cierre_caja import cerrar_caja_local

                result = cerrar_caja_local(
                    usuario_id=int(payload["usuario_id"]),
                    user_name=str(payload.get("user_name") or "Cajero"),
                    efectivo_contado=float(payload.get("efectivo_contado") or 0),
                    fondo_inicial=float(payload.get("fondo_inicial") or 0),
                    observaciones=str(payload.get("observaciones") or ""),
                    fecha=payload.get("fecha"),
                )
                return _json_response(self, 200, result)

            if path == "/api/ajustes":
                from services.ajuste_caja import registrar_ajuste_local

                result = registrar_ajuste_local(
                    usuario_id=int(payload["usuario_id"]),
                    user_name=str(payload.get("user_name") or "Cajero"),
                    monto=float(payload["monto"]),
                    metodo_desde=str(payload["metodo_desde"]),
                    metodo_hacia=str(payload["metodo_hacia"]),
                    observaciones=str(payload.get("observaciones") or ""),
                    terminal_id=payload.get("terminal_id"),
                    sucursal=payload.get("sucursal"),
                )
                return _json_response(self, 200, result)

            return _json_response(self, 404, {"error": "Ruta no encontrada"})
        except StockError as e:
            return _json_response(self, 409, {"ok": False, "error": str(e)})
        except Exception as e:
            return _json_response(self, 500, {"ok": False, "error": str(e)})


def start_lan_server(host: str | None = None, port: int | None = None) -> tuple[str, int]:
    global _server_thread, _httpd
    if _httpd is not None:
        cfg = load_config()
        return host or "0.0.0.0", int(port or cfg.get("servidor_puerto") or 8765)

    cfg = load_config()
    bind_host = host if host is not None else "0.0.0.0"
    bind_port = int(port if port is not None else cfg.get("servidor_puerto") or 8765)
    _httpd = ThreadingHTTPServer((bind_host, bind_port), PosLanHandler)

    def _run():
        _httpd.serve_forever(poll_interval=0.5)

    _server_thread = threading.Thread(target=_run, name="RodPOS-LAN", daemon=True)
    _server_thread.start()
    return bind_host, bind_port


def stop_lan_server() -> None:
    global _httpd, _server_thread
    if _httpd is not None:
        _httpd.shutdown()
        _httpd.server_close()
        _httpd = None
        _server_thread = None


def is_lan_server_running() -> bool:
    return _httpd is not None
