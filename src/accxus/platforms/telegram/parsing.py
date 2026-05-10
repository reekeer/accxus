from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from accxus.platforms.telegram.client import connected
from accxus.types.telegram import ParsedUser

log = logging.getLogger(__name__)


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
    if fmt == "txt":
        lines = [f"[{m['date']}] {m['from'] or 'unknown'}: {m['text']}" for m in messages]
        dest.write_text("\n".join(lines), encoding="utf-8")
    else:
        dest.write_text(json.dumps(messages, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"[parse] exported {len(messages)} messages from {chat!r} → {dest}")
    return len(messages)


async def parse_chat_members(
    session_name: str,
    chat: str,
    on_progress: Callable[[int], None] | None = None,
) -> list[ParsedUser]:
    users: list[ParsedUser] = []
    async with connected(session_name) as client:
        async for member in client.get_chat_members(chat):  # type: ignore[reportGeneralTypeIssues]
            u = member.user
            users.append(
                ParsedUser(
                    id=u.id,
                    username=u.username or "",
                    first_name=u.first_name or "",
                    last_name=u.last_name or "",
                    phone=u.phone_number or "",
                )
            )
            if on_progress and len(users) % 50 == 0:
                on_progress(len(users))
    log.info(f"[parse] parsed {len(users)} members from {chat!r}")
    return users


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
