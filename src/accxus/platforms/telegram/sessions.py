from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

import accxus.config as cfg
from accxus.types.telegram import SessionInfo, SessionKind, SessionStatus
from accxus.utils.session_convert import convert_telethon_to_pyrogram, detect_kind

log = logging.getLogger(__name__)

_META_FILE: Path = cfg.SESSIONS_DIR / "metadata.json"


def load_metadata() -> dict[str, dict[str, Any]]:
    if _META_FILE.exists():
        try:
            return json.loads(_META_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_metadata(meta: dict[str, dict[str, Any]]) -> None:
    _META_FILE.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def read_session_dc_id(session_name: str) -> int | None:
    path = session_path(session_name)
    if not path.exists():
        return None
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute("SELECT dc_id FROM sessions LIMIT 1").fetchone()
    except sqlite3.Error:
        return None
    if not row or row[0] is None:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def update_metadata_dc_id(session_name: str, dc_id: int | None) -> None:
    if dc_id is None:
        return
    meta = load_metadata()
    item = meta.setdefault(session_name, {})
    if item.get("dc_id") == dc_id:
        return
    item["dc_id"] = dc_id
    save_metadata(meta)


def update_metadata(session_name: str, info: SessionInfo) -> None:
    meta = load_metadata()
    data = {
        "phone": info.phone,
        "first_name": info.first_name,
        "last_name": info.last_name,
        "username": info.username,
        "kind": info.kind.name,
        "status": info.status.value,
    }
    if info.user_id is not None:
        data["user_id"] = str(info.user_id)
    if info.dc_id is not None:
        data["dc_id"] = str(info.dc_id)
    meta.setdefault(session_name, {}).update(data)
    save_metadata(meta)


def hydrate_session_dc_metadata(session_name: str) -> int | None:
    dc_id = read_session_dc_id(session_name)
    update_metadata_dc_id(session_name, dc_id)
    return dc_id


def hydrate_all_dc_metadata() -> None:
    meta = load_metadata()
    changed = False
    for f in sorted(cfg.SESSIONS_DIR.glob("*.session")):
        dc_id = read_session_dc_id(f.stem)
        if dc_id is not None and meta.setdefault(f.stem, {}).get("dc_id") != dc_id:
            meta[f.stem]["dc_id"] = dc_id
            changed = True
    if changed:
        save_metadata(meta)


def update_metadata_statuses(statuses: dict[str, SessionStatus]) -> None:
    meta = load_metadata()
    for name, status in statuses.items():
        item = meta.setdefault(name, {})
        item["status"] = status.value
        dc_id = read_session_dc_id(name)
        if dc_id is not None:
            item["dc_id"] = dc_id
    save_metadata(meta)


def _coerce_dc_id(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def list_sessions() -> list[SessionInfo]:
    hydrate_all_dc_metadata()
    meta = load_metadata()
    result: list[SessionInfo] = []
    for f in sorted(cfg.SESSIONS_DIR.glob("*.session")):
        name = f.stem
        m = meta.get(name, {})
        kind_str = m.get("kind", "")
        try:
            kind = SessionKind[kind_str] if kind_str else detect_kind(f)
        except KeyError:
            kind = SessionKind.UNKNOWN
        status_str = m.get("status", SessionStatus.UNKNOWN.value)
        try:
            status = SessionStatus(status_str)
        except ValueError:
            status = SessionStatus.UNKNOWN

        result.append(
            SessionInfo(
                name=name,
                phone=m.get("phone", ""),
                first_name=m.get("first_name", ""),
                last_name=m.get("last_name", ""),
                username=m.get("username", ""),
                bio=m.get("bio", ""),
                user_id=m.get("user_id"),
                dc_id=_coerce_dc_id(m.get("dc_id")) or read_session_dc_id(name),
                kind=kind,
                status=status,
            )
        )
    return result


def session_path(name: str) -> Path:
    return cfg.SESSIONS_DIR / f"{name}.session"


def session_exists(name: str) -> bool:
    return session_path(name).exists()


def delete_session(name: str) -> None:
    path = session_path(name)
    if path.exists():
        path.unlink()
    meta = load_metadata()
    meta.pop(name, None)
    save_metadata(meta)
    log.info(f"[sessions] deleted {name!r}")


def import_session(src: Path, new_name: str) -> tuple[bool, str]:
    if not src.exists():
        return False, f"File not found: {src}"

    dest = session_path(new_name)
    if dest.exists():
        return False, f"Session '{new_name}' already exists"

    kind = detect_kind(src)

    if kind == SessionKind.PYROGRAM:
        import shutil

        shutil.copy2(src, dest)
        meta = load_metadata()
        meta[new_name] = {"kind": SessionKind.PYROGRAM.name, "status": SessionStatus.UNKNOWN.value}
        save_metadata(meta)
        log.info(f"[sessions] imported pyrogram session {src.name!r} as {new_name!r}")
        return True, "Pyrogram session imported"

    if kind == SessionKind.TELETHON:
        ok = convert_telethon_to_pyrogram(src, dest)
        if ok:
            meta = load_metadata()
            meta[new_name] = {
                "kind": SessionKind.TELETHON.name,
                "status": SessionStatus.UNKNOWN.value,
            }
            save_metadata(meta)
            log.info(f"[sessions] converted telethon session {src.name!r} → {new_name!r}")
            return True, "Telethon session converted and imported"
        return False, "Telethon conversion failed"

    return False, f"Unknown session format: {src.name}"
