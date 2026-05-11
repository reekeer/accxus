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


def _enum_value(value: Any) -> str:
    if value is None:
        return ""
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    enum_name = getattr(value, "name", None)
    if isinstance(enum_name, str):
        return enum_name.lower()
    return str(value)


def _stringify_list(values: Any) -> list[str]:
    if not values:
        return []
    if not isinstance(values, list | tuple):
        values = [values]
    return [_format_optional(v) for v in values if v is not None]


def _serializable_value(value: Any, depth: int = 0) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if depth > 2:
        return _format_optional(value)
    if isinstance(value, list | tuple | set):
        return [_serializable_value(item, depth + 1) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _serializable_value(item, depth + 1)
            for key, item in value.items()
            if not str(key).startswith("_")
        }
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value"):
        return _enum_value(value)
    data = getattr(value, "__dict__", None)
    if isinstance(data, dict):
        return {
            key: _serializable_value(item, depth + 1)
            for key, item in data.items()
            if not key.startswith("_") and key != "_client"
        }
    return _format_optional(value)


def _normalize_gift(gift: Any) -> dict[str, Any]:
    data = _serializable_value(gift)
    if not isinstance(data, dict):
        data = {"value": data}
    from_id = (
        data.get("from")
        or data.get("from_id")
        or data.get("sender_id")
        or data.get("user_id")
        or data.get("peer_id")
        or ""
    )
    gift_type = data.get("type") or data.get("_") or data.get("title") or type(gift).__name__
    date = data.get("date") or data.get("timestamp") or ""
    normalized = {"from": from_id, "type": gift_type, "date": date}
    for key, value in data.items():
        if key not in normalized and key not in {"from_id", "sender_id", "user_id", "peer_id"}:
            normalized[key] = value
    return normalized


def _normalize_gifts(values: Any) -> list[dict[str, Any]]:
    if not values:
        return []
    if not isinstance(values, list | tuple):
        values = [values]
    return [_normalize_gift(value) for value in values if value is not None]


def _message_sender(msg: Any) -> str:
    if getattr(msg, "from_user", None):
        user = msg.from_user
        return user.username or str(user.id)
    if getattr(msg, "sender_chat", None):
        chat = msg.sender_chat
        return chat.username or chat.title or str(chat.id)
    return ""


def _message_type(msg: Any) -> str:
    if getattr(msg, "service", None):
        return "service"
    if getattr(msg, "media", None):
        return _enum_value(msg.media)
    if getattr(msg, "text", None):
        return "text"
    return "empty"


def _user_label(user: Any) -> str:
    if user is None:
        return ""
    username = getattr(user, "username", "") or ""
    if username:
        return f"@{username}"
    name = " ".join(
        part for part in [getattr(user, "first_name", ""), getattr(user, "last_name", "")] if part
    )
    return name or str(getattr(user, "id", ""))


def _service_text(msg: Any) -> str:
    service = _enum_value(getattr(msg, "service", None))
    actor = _message_sender(msg) or "system"
    if service == "new_chat_members":
        members = ", ".join(
            _user_label(user) for user in getattr(msg, "new_chat_members", []) or []
        )
        return f"{actor} added {members}".strip()
    if service == "left_chat_members":
        return f"{_user_label(getattr(msg, 'left_chat_member', None))} left the chat".strip()
    if service == "new_chat_title":
        return f"{actor} changed chat title to {getattr(msg, 'new_chat_title', '')}"
    if service == "new_chat_photo":
        return f"{actor} changed chat photo"
    if service == "delete_chat_photo":
        return f"{actor} deleted chat photo"
    if service == "pinned_message":
        pinned = getattr(getattr(msg, "pinned_message", None), "id", "")
        return f"{actor} pinned message {pinned}".strip()
    if service == "video_chat_started":
        return f"{actor} started video chat"
    if service == "video_chat_ended":
        ended = getattr(msg, "video_chat_ended", None)
        duration = getattr(ended, "duration", "")
        return f"{actor} ended video chat {duration}".strip()
    if service == "video_chat_scheduled":
        scheduled = getattr(msg, "video_chat_scheduled", None)
        start_date = _format_optional(getattr(scheduled, "start_date", ""))
        return f"{actor} scheduled video chat {start_date}".strip()
    if service == "video_chat_members_invited":
        invited = getattr(msg, "video_chat_members_invited", None)
        users = ", ".join(_user_label(user) for user in getattr(invited, "users", []) or [])
        return f"{actor} invited {users} to video chat".strip()
    ttl_period = getattr(msg, "ttl_period", None) or getattr(msg, "message_auto_delete_timer", None)
    if ttl_period:
        return f"{actor} changed auto-delete timer to {ttl_period}"
    return service


def _service_details(msg: Any) -> dict[str, Any]:
    fields = [
        "new_chat_members",
        "left_chat_member",
        "new_chat_title",
        "delete_chat_photo",
        "group_chat_created",
        "supergroup_chat_created",
        "channel_chat_created",
        "migrate_to_chat_id",
        "migrate_from_chat_id",
        "pinned_message",
        "game_high_score",
        "video_chat_scheduled",
        "video_chat_started",
        "video_chat_ended",
        "video_chat_members_invited",
        "web_app_data",
        "ttl_period",
        "message_auto_delete_timer",
        "message_auto_delete_timer_changed",
    ]
    details: dict[str, Any] = {}
    for field in fields:
        value = getattr(msg, field, None)
        if value:
            details[field] = _serializable_value(value)
    return details


def _media_suffix(msg: Any) -> str:
    media_type = _enum_value(getattr(msg, "media", None))
    media = getattr(msg, media_type, None) if media_type else None
    file_name = getattr(media, "file_name", "") or ""
    if file_name and Path(file_name).suffix:
        return Path(file_name).suffix
    mime_type = getattr(media, "mime_type", "") or ""
    if mime_type == "application/x-tgsticker":
        return ".tgs"
    if mime_type == "video/webm":
        return ".webm"
    if mime_type == "image/webp":
        return ".webp"
    if media_type == "photo":
        return ".jpg"
    if media_type == "sticker":
        if getattr(media, "is_animated", False):
            return ".tgs"
        if getattr(media, "is_video", False):
            return ".webm"
        return ".webp"
    if media_type == "animation":
        return ".mp4"
    return ""


async def _download_message_media(client: Any, msg: Any, media_dir: Path | None) -> str:
    if media_dir is None or not getattr(msg, "media", None):
        return ""
    media_dir.mkdir(parents=True, exist_ok=True)
    media_type = _enum_value(msg.media)
    dest = media_dir / f"{media_type}{msg.id}{_media_suffix(msg)}"
    try:
        downloaded = await client.download_media(msg, file_name=str(dest))
        return Path(str(downloaded or dest)).name
    except Exception as exc:
        log.debug("[parse] media download failed for message %s: %s", msg.id, exc)
        return ""


def _custom_emoji_ids(msg: Any) -> list[int]:
    ids: list[int] = []
    for entity in list(getattr(msg, "entities", []) or []) + list(
        getattr(msg, "caption_entities", []) or []
    ):
        custom_emoji_id = getattr(entity, "custom_emoji_id", None)
        if custom_emoji_id:
            ids.append(int(custom_emoji_id))
    return ids


async def _download_custom_emojis(client: Any, msg: Any, media_dir: Path | None) -> list[str]:
    ids = _custom_emoji_ids(msg)
    if media_dir is None or not ids:
        return []
    media_dir.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    with contextlib.suppress(Exception):
        stickers = await client.get_custom_emoji_stickers(ids)
        for sticker in stickers:
            suffix = ".tgs" if sticker.is_animated else ".webm" if sticker.is_video else ".webp"
            dest = media_dir / f"emoji{sticker.file_unique_id}{suffix}"
            try:
                downloaded = await client.download_media(sticker.file_id, file_name=str(dest))
                files.append(Path(str(downloaded or dest)).name)
            except Exception as exc:
                log.debug("[parse] custom emoji download failed: %s", exc)
    return files


async def _message_to_dict(client: Any, msg: Any, media_dir: Path | None) -> dict[str, Any]:
    msg_type = _message_type(msg)
    service = _enum_value(getattr(msg, "service", None))
    media = _enum_value(getattr(msg, "media", None))
    text = msg.text or msg.caption or ""
    if service and not text:
        text = _service_text(msg)
    return {
        "id": msg.id,
        "date": str(msg.date),
        "from": _message_sender(msg),
        "type": msg_type,
        "service": service,
        "media_type": media,
        "text": text,
        "media_file": await _download_message_media(client, msg, media_dir),
        "custom_emoji_files": await _download_custom_emojis(client, msg, media_dir),
        "service_details": _service_details(msg) if service else {},
    }


async def export_chat_history(
    session_name: str,
    chat: str,
    limit: int = 0,
    on_progress: Callable[[int], None] | None = None,
    media_dir: Path | None = None,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    async with connected(session_name) as client:
        async for msg in client.get_chat_history(chat, limit=limit or 0):  # type: ignore[reportGeneralTypeIssues]
            messages.append(await _message_to_dict(client, msg, media_dir))
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
    media_dir: Path | None = None,
) -> int:
    messages = await export_chat_history(session_name, chat, limit, on_progress, media_dir)
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
    media_dir: Path | None = None,
) -> dict[str, int]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    exported: dict[str, int] = {}

    for chat in chats:
        chat_key = _clean_filename(chat.lstrip("@"))

        def _progress(count: int, chat_ref: str = chat) -> None:
            if on_progress:
                on_progress(chat_ref, count)

        dest = dest_dir / f"{chat_key}.{fmt}"
        chat_media_dir = media_dir / chat_key if media_dir else None
        exported[chat] = await save_chat_history(
            session_name,
            chat,
            dest,
            fmt=fmt,
            limit=limit,
            on_progress=_progress,
            media_dir=chat_media_dir,
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
    media_dir: Path | None = None,
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
        media_dir=media_dir,
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
        extras["birthday"] = extras["birthday"] or _format_optional(getattr(chat, "birthdate", ""))
        extras["song"] = extras["song"] or _format_optional(getattr(chat, "profile_music", ""))
        extras["gifts"] = _normalize_gifts(
            getattr(chat, "gifts", None)
            or getattr(chat, "received_gifts", None)
            or getattr(chat, "premium_gifts", None)
        )

    with contextlib.suppress(Exception):
        from pyrogram.raw.functions.users import GetFullUser  # type: ignore[import-untyped]

        peer = await client.resolve_peer(user_id)
        full = await client.invoke(GetFullUser(id=peer))
        full_user = getattr(full, "full_user", full)
        extras["bio"] = extras["bio"] or getattr(full_user, "about", "") or ""
        extras["song"] = extras["song"] or _format_optional(getattr(full_user, "profile_song", ""))
        extras["birthday"] = extras["birthday"] or _format_optional(
            getattr(full_user, "birthday", "") or getattr(full_user, "birthdate", "")
        )
        extras["song"] = extras["song"] or _format_optional(getattr(full_user, "profile_music", ""))
        extras["gifts"] = extras["gifts"] or _normalize_gifts(
            getattr(full_user, "gifts", None)
            or getattr(full_user, "received_gifts", None)
            or getattr(full_user, "premium_gifts", None)
        )
        extras["raw_profile"] = _serializable_value(full_user)

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
        extras = await _load_user_extras(client, u.id)
        return {
            "id": u.id,
            "username": u.username or "",
            "first_name": u.first_name or "",
            "last_name": u.last_name or "",
            "phone": u.phone_number or "",
            "bio": extras.get("bio", "") or getattr(u, "bio", "") or "",
            "birthday": extras.get("birthday", ""),
            "song": extras.get("song", ""),
            "gifts": extras.get("gifts", []),
            "is_bot": bool(getattr(u, "is_bot", False)),
            "is_contact": bool(getattr(u, "is_contact", False)),
            "is_mutual_contact": bool(getattr(u, "is_mutual_contact", False)),
            "is_premium": bool(getattr(u, "is_premium", False)),
            "is_verified": bool(getattr(u, "is_verified", False)),
            "is_scam": bool(getattr(u, "is_scam", False)),
            "is_fake": bool(getattr(u, "is_fake", False)),
            "language_code": getattr(u, "language_code", "") or "",
            "dc_id": getattr(u, "dc_id", None),
            "status": _enum_value(getattr(u, "status", None)),
            "last_online_date": _format_optional(getattr(u, "last_online_date", "")),
            "next_offline_date": _format_optional(getattr(u, "next_offline_date", "")),
            "emoji_status": _serializable_value(getattr(u, "emoji_status", None)),
            "raw_profile": extras.get("raw_profile", {}),
        }
