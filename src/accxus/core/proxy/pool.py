from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from accxus.types.core import ProxyConfig


@dataclass
class _Entry:
    config: ProxyConfig
    failures: int = 0
    last_fail: float = field(default_factory=float)


class ProxyPool:
    def __init__(
        self,
        proxies: list[ProxyConfig],
        *,
        max_concurrent: int = 10,
        cooldown: float = 30.0,
        max_failures: int = 3,
    ) -> None:
        if not proxies:
            raise ValueError("ProxyPool requires at least one proxy")
        self._entries: list[_Entry] = [_Entry(config=p) for p in proxies]
        self._max_failures = max_failures
        self._cooldown = cooldown
        self._sem = asyncio.Semaphore(max_concurrent)
        self._rr_idx = 0
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[ProxyConfig, None]:
        async with self._sem:
            entry = await self._pick()
            try:
                yield entry.config
            except Exception:
                self._mark_failure(entry)
                raise

    def report_failure(self, proxy: ProxyConfig) -> None:
        for e in self._entries:
            if e.config == proxy:
                self._mark_failure(e)
                return

    def report_success(self, proxy: ProxyConfig) -> None:
        for e in self._entries:
            if e.config == proxy:
                e.failures = 0
                return

    def stats(self) -> list[dict[str, object]]:
        now = time.monotonic()
        out: list[dict[str, object]] = []
        for e in self._entries:
            available = self._is_available(e, now)
            remaining = max(0.0, self._cooldown - (now - e.last_fail)) if not available else 0.0
            out.append(
                {
                    "proxy": e.config.to_url(),
                    "failures": e.failures,
                    "available": available,
                    "cooldown_remaining_s": remaining,
                }
            )
        return out

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def available_count(self) -> int:
        now = time.monotonic()
        return sum(1 for e in self._entries if self._is_available(e, now))

    def _is_available(self, entry: _Entry, now: float) -> bool:
        if entry.failures < self._max_failures:
            return True
        return (now - entry.last_fail) > self._cooldown

    def _mark_failure(self, entry: _Entry) -> None:
        entry.failures += 1
        entry.last_fail = time.monotonic()

    async def _pick(self) -> _Entry:
        while True:
            now = time.monotonic()
            async with self._lock:
                n = len(self._entries)
                for _ in range(n):
                    e = self._entries[self._rr_idx % n]
                    self._rr_idx += 1
                    if self._is_available(e, now):
                        return e
            await asyncio.sleep(1.0)
