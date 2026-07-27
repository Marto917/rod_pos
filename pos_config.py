"""Configuración local del POS (modo LAN, sucursal, terminal)."""
from __future__ import annotations

import json
import os
from copy import deepcopy

from db_init import get_base_dir

CONFIG_FILENAME = "pos_config.json"

DEFAULTS = {
    "sucursal_nombre": "Sucursal principal",
    "terminal_id": "CAJA-1",
    # local = BD en esta PC | servidor = esta PC comparte BD por LAN | cliente = usa BD del servidor
    "modo_red": "local",
    "servidor_host": "127.0.0.1",
    "servidor_puerto": 8765,
    "auto_iniciar_servidor": True,
}


def config_path() -> str:
    return os.path.join(get_base_dir(), CONFIG_FILENAME)


def load_config() -> dict:
    path = config_path()
    data = deepcopy(DEFAULTS)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                data.update({k: raw[k] for k in DEFAULTS if k in raw})
        except Exception:
            pass
    return data


def save_config(updates: dict) -> dict:
    data = load_config()
    for key, value in updates.items():
        if key in DEFAULTS:
            data[key] = value
    path = config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def is_server_mode(cfg: dict | None = None) -> bool:
    cfg = cfg or load_config()
    return str(cfg.get("modo_red", "local")).lower() == "servidor"


def is_client_mode(cfg: dict | None = None) -> bool:
    cfg = cfg or load_config()
    return str(cfg.get("modo_red", "local")).lower() == "cliente"


def server_base_url(cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    host = str(cfg.get("servidor_host") or "127.0.0.1").strip()
    port = int(cfg.get("servidor_puerto") or 8765)
    return "http://%s:%s" % (host, port)
