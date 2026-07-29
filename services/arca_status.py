"""Consulta estado de ARCA desde el monitor público de Gestión Comercio."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

STATUS_URL = "https://gestioncomercio.com.ar/api/arca/status.json"


def consultar_estado_arca(timeout: float = 8.0) -> dict[str, Any]:
    """
    Devuelve {ok: bool, overall: str, detalle: str, raw: dict|None}.
    ok=True cuando overall es operational y reachable.
    """
    try:
        req = urllib.request.Request(
            STATUS_URL,
            headers={
                "User-Agent": "ROD-POS/1.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {
            "ok": False,
            "overall": "unreachable",
            "detalle": "Sin respuesta del monitor: %s" % e,
            "raw": None,
        }

    overall = str(raw.get("overall") or "").strip().lower()
    reachable = bool(raw.get("reachable", True))
    comps = raw.get("components") or {}
    ok = reachable and overall in ("operational", "ok", "up")
    if ok:
        # Exigir componentes clave en OK si vienen informados
        for key in ("app", "db", "auth"):
            val = str(comps.get(key) or "").upper()
            if val and val not in ("OK", "OPERATIONAL"):
                ok = False
                break

    detalle = "overall=%s · app=%s db=%s auth=%s" % (
        overall or "?",
        comps.get("app", "?"),
        comps.get("db", "?"),
        comps.get("auth", "?"),
    )
    return {"ok": ok, "overall": overall or "unknown", "detalle": detalle, "raw": raw}
