from __future__ import annotations

import sqlite3
from pathlib import Path

from accxus.types import SessionKind

_TELETHON_MARKER = "server_address"


def detect_kind(session_path: Path) -> SessionKind:
    if not session_path.exists():
        return SessionKind.UNKNOWN
    try:
        conn = sqlite3.connect(f"file:{session_path}?mode=ro", uri=True)
        cur = conn.execute("PRAGMA table_info(sessions)")
        cols = {row[1] for row in cur.fetchall()}
        conn.close()
        if _TELETHON_MARKER in cols:
            return SessionKind.TELETHON
        if "dc_id" in cols and "auth_key" in cols:
            return SessionKind.PYROGRAM
    except Exception:
        pass
    return SessionKind.UNKNOWN


def convert_telethon_to_pyrogram(src: Path, dest: Path) -> bool:
    if not src.exists():
        return False
    try:
        conn_src = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        row = conn_src.execute("SELECT dc_id, auth_key FROM sessions LIMIT 1").fetchone()
        conn_src.close()
        if row is None:
            return False
        dc_id, auth_key = row

        dest.unlink(missing_ok=True)
        conn_dst = sqlite3.connect(str(dest))
        conn_dst.execute(
            "CREATE TABLE sessions ("
            "  dc_id    INTEGER PRIMARY KEY,"
            "  test_mode INTEGER,"
            "  auth_key BLOB,"
            "  date     INTEGER,"
            "  user_id  INTEGER,"
            "  is_bot   INTEGER"
            ")"
        )
        conn_dst.execute(
            "CREATE TABLE peers ("
            "  id       INTEGER PRIMARY KEY,"
            "  access_hash INTEGER,"
            "  type     TEXT,"
            "  phone_number TEXT,"
            "  last_update_on INTEGER"
            ")"
        )
        conn_dst.execute(
            "CREATE TABLE version (number INTEGER)",
        )
        conn_dst.execute("INSERT INTO version VALUES (3)")
        conn_dst.execute(
            "INSERT INTO sessions VALUES (?, 0, ?, 0, 0, 0)",
            (dc_id, auth_key),
        )
        conn_dst.commit()
        conn_dst.close()
        return True
    except Exception:
        dest.unlink(missing_ok=True)
        return False
