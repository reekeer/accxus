from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyrogram import Client  # type: ignore[import-untyped]

import accxus.config as cfg
from accxus.platforms.telegram import sessions as tg_sessions
from accxus.types.core import ProxyConfig
from accxus.types.telegram import SessionInfo, SessionStatus
from accxus.utils.session_convert import detect_kind

log = logging.getLogger(__name__)


def make_client(
    session_name: str,
    *,
    api_id: int | None = None,
    api_hash: str | None = None,
    proxy: ProxyConfig | None = None,
    workdir: str | None = None,
) -> Client:
    from pyrogram import Client as _Client  # type: ignore[import-untyped]

    dc_id = tg_sessions.hydrate_session_dc_metadata(session_name)
    if dc_id is not None:
        log.debug("[tg] session %s uses dc_id=%s", session_name, dc_id)

    _proxy = proxy or cfg.config.telegram_proxy
    return _Client(  # type: ignore[reportCallIssue]
        name=session_name,
        api_id=api_id or cfg.TG_API_ID,
        api_hash=api_hash or cfg.TG_API_HASH,
        workdir=workdir or str(cfg.SESSIONS_DIR),
        no_updates=True,
        proxy=_proxy.to_pyrogram() if _proxy else None,  # type: ignore[arg-type]
        app_version=cfg.config.tg_app_version,
        device_model=cfg.config.tg_device_model,
        system_version=cfg.config.tg_system_version,
    )


@asynccontextmanager
async def connected(
    session_name: str,
    *,
    api_id: int | None = None,
    api_hash: str | None = None,
    proxy: ProxyConfig | None = None,
) -> AsyncGenerator[Client, None]:
    client = make_client(session_name, api_id=api_id, api_hash=api_hash, proxy=proxy)
    await client.connect()
    try:
        yield client
    finally:
        try:
            if client.is_connected:
                await client.disconnect()
        except Exception:
            pass


async def fetch_info(
    session_name: str,
    *,
    proxy: ProxyConfig | None = None,
) -> SessionInfo:
    async with connected(session_name, proxy=proxy) as client:
        me = await client.get_me()
        dc_id = await client.storage.dc_id()
        try:
            chat = await client.get_chat(me.id)
            bio: str = getattr(chat, "bio", "") or ""
        except Exception:
            bio = ""

        kind = detect_kind(cfg.SESSIONS_DIR / f"{session_name}.session")
        return SessionInfo(
            name=session_name,
            phone=f"+{me.phone_number}" if me.phone_number else "",
            first_name=me.first_name or "",
            last_name=me.last_name or "",
            username=me.username or "",
            bio=bio,
            dc_id=dc_id,
            kind=kind,
            status=SessionStatus.VALID,
        )


async def check_validity(
    session_name: str,
    *,
    proxy: ProxyConfig | None = None,
) -> SessionStatus:
    sess_file = cfg.SESSIONS_DIR / f"{session_name}.session"
    if not sess_file.exists():
        return SessionStatus.INVALID
    from pyrogram.errors import AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan

    try:
        async with connected(session_name, proxy=proxy) as client:
            me = await client.get_me()
            if me:
                tg_sessions.update_metadata_dc_id(session_name, await client.storage.dc_id())
                return SessionStatus.VALID
            return SessionStatus.INVALID
    except (AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan):
        return SessionStatus.INVALID
    except Exception:
        return SessionStatus.INVALID


async def check_all_validity(
    session_names: list[str],
    *,
    proxy: ProxyConfig | None = None,
    concurrency: int = 10,
) -> dict[str, SessionStatus]:
    sem = asyncio.Semaphore(concurrency)

    async def _one(name: str) -> tuple[str, SessionStatus]:
        async with sem:
            return name, await check_validity(name, proxy=proxy)

    results = await asyncio.gather(*(_one(n) for n in session_names))
    return dict(results)
