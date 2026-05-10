from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from accxus.platforms.telegram.client import connected
from accxus.platforms.telegram.sessions import load_metadata
from accxus.types.telegram import SendResult
from accxus.utils.variables import expand

log = logging.getLogger(__name__)


async def send_one(
    session_name: str,
    target: str,
    text: str,
    retries: int = 1,
) -> SendResult:
    from pyrogram.errors import FloodWait, PeerIdInvalid, UsernameNotOccupied

    last_error = ""
    attempts = max(1, retries)

    for attempt in range(attempts):
        log.info("[msg] attempt %d/%d — %s → %s", attempt + 1, attempts, session_name, target)
        try:
            async with connected(session_name) as client:
                await client.send_message(target, text)
            log.info("[msg] ✓ sent — %s → %s", session_name, target)
            return SendResult(session=session_name, target=target, success=True)

        except FloodWait as e:
            wait = float(e.value) if isinstance(e.value, (int, float)) else 30.0
            log.warning("[msg] FloodWait %.0fs — %s, sleeping…", wait, session_name)
            last_error = f"FloodWait {wait:.0f}s"
            await asyncio.sleep(wait)

        except (PeerIdInvalid, UsernameNotOccupied):
            log.warning("[msg] peer not found: %s (session: %s)", target, session_name)
            return SendResult(
                session=session_name, target=target, success=False, error="Peer not found"
            )

        except Exception as e:
            last_error = str(e)
            log.error(
                "[msg] error attempt %d/%d — %s → %s: %s",
                attempt + 1,
                attempts,
                session_name,
                target,
                e,
            )
            if attempt + 1 < attempts:
                log.info("[msg] retrying in 2s…")
                await asyncio.sleep(2.0)

    log.error("[msg] ✗ all attempts failed — %s → %s: %s", session_name, target, last_error)
    return SendResult(
        session=session_name, target=target, success=False, error=last_error or "Failed"
    )


async def send_bulk(
    sessions: list[str],
    targets: list[str],
    template: str,
    delay: float = 1.0,
    retries: int = 1,
    on_result: Callable[[SendResult], None] | None = None,
    stop_flag: Callable[[], bool] | None = None,
) -> list[SendResult]:
    meta_all = load_metadata()
    results: list[SendResult] = []
    total = len(sessions) * len(targets)

    log.info(
        "[msg] starting bulk send: %d session(s) × %d target(s) = %d messages, delay=%.1fs, retries=%d",
        len(sessions),
        len(targets),
        total,
        delay,
        retries,
    )

    done = 0
    for sname in sessions:
        if stop_flag and stop_flag():
            log.info("[msg] stopped by user after %d/%d", done, total)
            break
        meta = meta_all.get(sname, {})
        full_name = f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip()
        log.info("[msg] session %s — name=%r phone=%s", sname, full_name, meta.get("phone", "?"))

        for target in targets:
            if stop_flag and stop_flag():
                log.info("[msg] stopped by user after %d/%d", done, total)
                break
            text = expand(
                template,
                name=full_name,
                phone=meta.get("phone", ""),
                username=meta.get("username", ""),
            )
            result = await send_one(sname, target, text, retries=retries)
            results.append(result)
            done += 1
            if on_result:
                on_result(result)
            if done < total and not (stop_flag and stop_flag()):
                log.info("[msg] sleeping %.1fs before next send…", delay)
                await asyncio.sleep(delay)

    ok = sum(1 for r in results if r.success)
    log.info("[msg] bulk send finished: %d/%d succeeded", ok, len(results))
    return results
