from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from accxus.platforms.telegram.client import connected
from accxus.types.telegram import ParsedUser

log = logging.getLogger(__name__)


def _clean_filename(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value)
    return cleaned.strip("._") or "chat"


def _chat_ref(chat: dict[str, Any]) -> str:
    username = str(chat.get("username") or "").strip()
    if username:
        return f"@{username}"
    return str(chat["id"])


def _format_optional(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _stringify_list(values: Any) -> list[str]:
    if not values:
        return []
    if not isinstance(values, list | tuple):
        values = [values]
    return [_format_optional(v) for v in values if v is not None]


async def export_chat_history(
    session_name: str,
    chat: str,
    limit: int = 0,
    on_progress: Callable[[int], None] | None = None,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    async with connected(session_name) as client:
        async for msg in client.get_chat_history(chat, limit=limit or 0):  # type: ignore[reportGeneralTypeIssues]
            messages.append(
                {
                    "id": msg.id,
                    "date": str(msg.date),
                    "from": (
                        (msg.from_user.username or str(msg.from_user.id)) if msg.from_user else ""
                    ),
                    "text": msg.text or msg.caption or "",
                }
            )
            if on_progress and len(messages) % 100 == 0:
                on_progress(len(messages))
    return messages


async def save_chat_history(
    session_name: str,
    chat: str,
    dest: Path,
    fmt: str = "json",
    limit: int = 0,
    on_progress: Callable[[int], None] | None = None,
) -> int:
    messages = await export_chat_history(session_name, chat, limit, on_progress)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "txt":
        lines = [f"[{m['date']}] {m['from'] or 'unknown'}: {m['text']}" for m in messages]
        dest.write_text("\n".join(lines), encoding="utf-8")
    else:
        dest.write_text(json.dumps(messages, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"[parse] exported {len(messages)} messages from {chat!r} → {dest}")
    return len(messages)


async def save_chats_history(
    session_name: str,
    chats: list[str],
    dest_dir: Path,
    fmt: str = "json",
    limit: int = 0,
    on_progress: Callable[[str, int], None] | None = None,
) -> dict[str, int]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    exported: dict[str, int] = {}

    for chat in chats:
        chat_key = _clean_filename(chat.lstrip("@"))

        def _progress(count: int, chat_ref: str = chat) -> None:
            if on_progress:
                on_progress(chat_ref, count)

        dest = dest_dir / f"{chat_key}.{fmt}"
        exported[chat] = await save_chat_history(
            session_name,
            chat,
            dest,
            fmt=fmt,
            limit=limit,
            on_progress=_progress,
        )

    log.info("[parse] exported %d chat histories to %s", len(exported), dest_dir)
    return exported


async def save_all_dialog_histories(
    session_name: str,
    dest_dir: Path,
    *,
    kind: str = "all",
    selected_chats: list[str] | None = None,
    fmt: str = "json",
    limit: int = 0,
    on_progress: Callable[[str, int], None] | None = None,
) -> dict[str, int]:
    chats = selected_chats or [
        _chat_ref(chat) for chat in await list_dialogs(session_name, kind=kind, limit=0)
    ]
    return await save_chats_history(
        session_name,
        chats,
        dest_dir,
        fmt=fmt,
        limit=limit,
        on_progress=on_progress,
    )


async def _download_user_avatar(client: Any, user: Any, avatar_dir: Path | None) -> str:
    if avatar_dir is None:
        return ""
    photo = getattr(user, "photo", None)
    file_id = getattr(photo, "big_file_id", "") or getattr(photo, "small_file_id", "")
    if not file_id:
        return ""

    avatar_dir.mkdir(parents=True, exist_ok=True)
    dest = avatar_dir / f"{user.id}.jpg"
    try:
        downloaded = await client.download_media(file_id, file_name=str(dest))
        return str(downloaded or dest)
    except Exception as exc:
        log.debug("[parse] avatar download failed for %s: %s", user.id, exc)
        return ""


async def _load_user_extras(client: Any, user_id: int) -> dict[str, Any]:
    extras: dict[str, Any] = {
        "bio": "",
        "song": "",
        "birthday": "",
        "gifts": [],
    }
    with contextlib.suppress(Exception):
        chat = await client.get_chat(user_id)
        extras["bio"] = getattr(chat, "bio", "") or getattr(chat, "description", "") or ""
        extras["song"] = _format_optional(getattr(chat, "profile_song", ""))
        extras["birthday"] = _format_optional(getattr(chat, "birthday", ""))
        extras["gifts"] = _stringify_list(getattr(chat, "gifts", []))

    with contextlib.suppress(Exception):
        from pyrogram.raw.functions.users import GetFullUser  # type: ignore[import-untyped]

        peer = await client.resolve_peer(user_id)
        full = await client.invoke(GetFullUser(id=peer))
        full_user = getattr(full, "full_user", full)
        extras["bio"] = extras["bio"] or getattr(full_user, "about", "") or ""
        extras["song"] = extras["song"] or _format_optional(getattr(full_user, "profile_song", ""))
        extras["birthday"] = extras["birthday"] or _format_optional(
            getattr(full_user, "birthday", "")
        )
        extras["gifts"] = extras["gifts"] or _stringify_list(
            getattr(full_user, "gifts", None) or getattr(full_user, "premium_gifts", None)
        )

    return extras


async def _parsed_user_from_member(
    client: Any,
    member: Any,
    *,
    chat_info: dict[str, Any],
    avatar_dir: Path | None,
) -> ParsedUser:
    u = member.user
    extras = await _load_user_extras(client, u.id)
    return ParsedUser(
        id=u.id,
        username=u.username or "",
        first_name=u.first_name or "",
        last_name=u.last_name or "",
        phone=u.phone_number or "",
        avatar_path=await _download_user_avatar(client, u, avatar_dir),
        bio=extras["bio"],
        song=extras["song"],
        birthday=extras["birthday"],
        gifts=extras["gifts"],
        source_chat_id=chat_info.get("id"),
        source_chat_title=chat_info.get("title", ""),
        source_chat_username=chat_info.get("username", ""),
    )


async def parse_chat_members(
    session_name: str,
    chat: str,
    on_progress: Callable[[int], None] | None = None,
    avatar_dir: Path | None = None,
) -> list[ParsedUser]:
    users: list[ParsedUser] = []
    async with connected(session_name) as client:
        chat_obj = await client.get_chat(chat)
        chat_info = {
            "id": chat_obj.id,
            "title": (
                getattr(chat_obj, "title", None)
                or " ".join(
                    p
                    for p in [
                        getattr(chat_obj, "first_name", ""),
                        getattr(chat_obj, "last_name", ""),
                    ]
                    if p
                )
                or str(chat_obj.id)
            ),
            "username": getattr(chat_obj, "username", "") or "",
        }
        async for member in client.get_chat_members(chat):  # type: ignore[reportGeneralTypeIssues]
            users.append(
                await _parsed_user_from_member(
                    client,
                    member,
                    chat_info=chat_info,
                    avatar_dir=avatar_dir,
                )
            )
            if on_progress and len(users) % 50 == 0:
                on_progress(len(users))
    log.info(f"[parse] parsed {len(users)} members from {chat!r}")
    return users


async def parse_chats_members(
    session_name: str,
    chats: list[str],
    *,
    avatar_dir: Path | None = None,
    on_progress: Callable[[str, int], None] | None = None,
) -> list[ParsedUser]:
    users_by_id: dict[int, ParsedUser] = {}
    async with connected(session_name) as client:
        for chat in chats:
            chat_obj = await client.get_chat(chat)
            chat_info = {
                "id": chat_obj.id,
                "title": (
                    getattr(chat_obj, "title", None)
                    or " ".join(
                        p
                        for p in [
                            getattr(chat_obj, "first_name", ""),
                            getattr(chat_obj, "last_name", ""),
                        ]
                        if p
                    )
                    or str(chat_obj.id)
                ),
                "username": getattr(chat_obj, "username", "") or "",
            }
            count = 0
            async for member in client.get_chat_members(chat):  # type: ignore[reportGeneralTypeIssues]
                parsed = await _parsed_user_from_member(
                    client,
                    member,
                    chat_info=chat_info,
                    avatar_dir=avatar_dir,
                )
                if parsed.id not in users_by_id:
                    users_by_id[parsed.id] = parsed
                count += 1
                if on_progress and count % 50 == 0:
                    on_progress(chat, count)
            if on_progress:
                on_progress(chat, count)

    users = list(users_by_id.values())
    log.info("[parse] parsed %d unique members from %d chats", len(users), len(chats))
    return users


async def save_chats_members(
    session_name: str,
    chats: list[str],
    dest: Path,
    *,
    avatar_dir: Path | None = None,
    on_progress: Callable[[str, int], None] | None = None,
) -> int:
    users = await parse_chats_members(
        session_name,
        chats,
        avatar_dir=avatar_dir,
        on_progress=on_progress,
    )
    payload = [u.model_dump() for u in users]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("[parse] saved %d parsed members to %s", len(users), dest)
    return len(users)


async def list_dialogs(
    session_name: str,
    kind: str = "all",
    limit: int = 200,
) -> list[dict[str, Any]]:
    from pyrogram.enums import ChatType  # type: ignore[import-untyped]

    kind_map = {
        ChatType.PRIVATE: "private",
        ChatType.BOT: "private",
        ChatType.GROUP: "group",
        ChatType.SUPERGROUP: "group",
        ChatType.CHANNEL: "channel",
    }
    result: list[dict[str, Any]] = []
    async with connected(session_name) as client:
        async for dialog in client.get_dialogs(limit=limit):  # type: ignore[reportGeneralTypeIssues]
            chat = dialog.chat
            chat_kind = kind_map.get(chat.type, "other")
            if kind != "all" and chat_kind != kind:
                continue
            if chat_kind == "private":
                title = (
                    " ".join(p for p in [chat.first_name or "", chat.last_name or ""] if p)
                    or chat.username
                    or str(chat.id)
                )
            else:
                title = chat.title or chat.username or str(chat.id)
            result.append(
                {
                    "kind": chat_kind,
                    "id": chat.id,
                    "title": title,
                    "username": chat.username or "",
                    "unread": getattr(dialog, "unread_messages_count", 0),
                }
            )
    log.info("[parse] listed %d dialogs (filter=%s) from %s", len(result), kind, session_name)
    return result


async def get_user_info(session_name: str, user_id: str) -> dict[str, Any]:
    async with connected(session_name) as client:
        u = await client.get_users(user_id)
        return {
            "id": u.id,
            "username": u.username or "",
            "first_name": u.first_name or "",
            "last_name": u.last_name or "",
            "phone": u.phone_number or "",
            "bio": getattr(u, "bio", "") or "",
        }
