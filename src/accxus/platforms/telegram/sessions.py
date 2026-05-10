from __future__ import annotations

import json
import logging
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


def update_metadata(session_name: str, info: SessionInfo) -> None:
    meta = load_metadata()
    meta.setdefault(session_name, {}).update(
        {
            "phone": info.phone,
            "first_name": info.first_name,
            "last_name": info.last_name,
            "username": info.username,
            "kind": info.kind.name,
            "status": info.status.value,
        }
    )
    save_metadata(meta)


def list_sessions() -> list[SessionInfo]:
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
