from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar

import aiohttp

from accxus.types.core import ProxyConfig, SmsProviderConfig
from accxus.types.sms import Activation, ActivationStatus, ProviderBalance, ServiceInfo

log = logging.getLogger(__name__)


def _build_session(proxy: ProxyConfig | None) -> aiohttp.ClientSession:
    if proxy is None:
        return aiohttp.ClientSession()

    if proxy.scheme in ("http", "https"):
        return aiohttp.ClientSession()

    try:
        from aiohttp_socks import ProxyConnector  # type: ignore[import-untyped]

        connector = ProxyConnector.from_url(proxy.to_url())
        return aiohttp.ClientSession(connector=connector)
    except ImportError:
        log.warning(
            "aiohttp-socks not installed — SOCKS proxy ignored for SMS requests. "
            "Install it with: pip install aiohttp-socks"
        )
        return aiohttp.ClientSession()


def _request_kwargs(proxy: ProxyConfig | None) -> dict[str, Any]:
    if proxy and proxy.scheme in ("http", "https"):
        return proxy.to_aiohttp_kwargs()
    return {}


class AbstractSmsProvider(ABC):
    name: ClassVar[str] = "abstract"

    def __init__(self, config: SmsProviderConfig) -> None:
        self.config = config
        self._proxy = config.proxy
        self._api_key = config.api_key

    @abstractmethod
    async def get_balance(self) -> ProviderBalance: ...

    @abstractmethod
    async def get_number(self, service: str, country: int = 0) -> Activation: ...

    @abstractmethod
    async def get_status(self, activation_id: str) -> tuple[ActivationStatus, str | None]: ...

    @abstractmethod
    async def cancel(self, activation_id: str) -> bool: ...

    @abstractmethod
    async def confirm(self, activation_id: str) -> bool: ...

    async def list_services(self, country: int = 0) -> list[ServiceInfo]:
        return []

    async def wait_for_code(
        self,
        activation_id: str,
        timeout: int | None = None,
        poll: int | None = None,
    ) -> str | None:
        _timeout = timeout if timeout is not None else self.config.timeout
        _poll = poll if poll is not None else self.config.poll
        elapsed = 0
        while elapsed < _timeout:
            try:
                status, code = await self.get_status(activation_id)
            except Exception as e:
                log.warning(f"[{self.name}] get_status error: {e}")
                await asyncio.sleep(_poll)
                elapsed += _poll
                continue

            if status == ActivationStatus.RECEIVED and code:
                return code
            if status in (ActivationStatus.CANCELLED, ActivationStatus.EXPIRED):
                return None

            await asyncio.sleep(_poll)
            elapsed += _poll

        log.warning(f"[{self.name}] activation {activation_id!r} timed out after {_timeout}s")
        return None

    def _session(self) -> aiohttp.ClientSession:
        return _build_session(self._proxy)

    def _req_kw(self) -> dict[str, Any]:
        return _request_kwargs(self._proxy)
