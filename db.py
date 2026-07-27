"""Acceso unificado a SQLite con WAL (mejor para servidor LAN)."""
from __future__ import annotations

import sqlite3

from db_init import get_db_path


def get_connection(timeout: float = 30.0) -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(), timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = %d" % int(timeout * 1000))
        conn.execute("PRAGMA synchronous = NORMAL")
    except sqlite3.Error:
        pass
    return conn
