from __future__ import annotations

import logging
from pathlib import Path

from accxus.platforms.telegram.client import connected, fetch_info
from accxus.platforms.telegram.sessions import update_metadata
from accxus.types.telegram import SessionInfo

log = logging.getLogger(__name__)


async def get_profile(session_name: str) -> SessionInfo:
    info = await fetch_info(session_name)
    update_metadata(session_name, info)
    return info


async def update_profile(
    session_name: str,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    bio: str | None = None,
) -> None:
    async with connected(session_name) as client:
        kwargs: dict[str, str] = {}
        if first_name is not None:
            kwargs["first_name"] = first_name
        if last_name is not None:
            kwargs["last_name"] = last_name
        if bio is not None:
            kwargs["bio"] = bio
        if kwargs:
            await client.update_profile(**kwargs)
    log.info(f"[profile] {session_name!r} updated: {list(kwargs)}")


async def set_avatar(session_name: str, photo_path: str | Path) -> None:
    path = Path(photo_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    async with connected(session_name) as client:
        await client.set_profile_photo(photo=str(path))
    log.info(f"[profile] {session_name!r} avatar updated from {path.name!r}")


async def delete_avatar(session_name: str) -> None:
    async with connected(session_name) as client:
        photos = []
        async for photo in client.get_chat_photos("me"):  # type: ignore[reportGeneralTypeIssues]
            photos.append(photo.file_id)
            break
        if photos:
            await client.delete_profile_photos(photos)
    log.info(f"[profile] {session_name!r} avatar deleted")
