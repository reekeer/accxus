from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass

from accxus.types.core import ProxyConfig

_DEFAULT_URL = "http://httpbin.org/ip"
_GEO_URL = "http://ip-api.com/json/?fields=status,country,countryCode,query,message"
_DEFAULT_TIMEOUT = 10.0


@dataclass
class ProxyCheckResult:
    proxy: ProxyConfig
    ok: bool
    ip: str | None
    latency_ms: float
    error: str | None = None


async def check_proxy(
    proxy: ProxyConfig,
    *,
    url: str = _DEFAULT_URL,
    timeout: float = _DEFAULT_TIMEOUT,
) -> ProxyCheckResult:
    import aiohttp

    start = time.monotonic()
    try:
        if proxy.scheme in ("http", "https"):
            proxy_url = f"http://{proxy.host}:{proxy.port}"
            proxy_auth = (
                aiohttp.BasicAuth(proxy.username, proxy.password) if proxy.username else None
            )
            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    url,
                    proxy=proxy_url,
                    proxy_auth=proxy_auth,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp,
            ):
                body = await resp.text()
        else:
            try:
                from aiohttp_socks import ProxyConnector  # type: ignore[import-untyped]
            except ImportError:
                return ProxyCheckResult(
                    proxy=proxy,
                    ok=False,
                    ip=None,
                    latency_ms=(time.monotonic() - start) * 1000,
                    error="aiohttp-socks not installed — pip install aiohttp-socks",
                )
            connector = ProxyConnector.from_url(proxy.to_url())
            async with (
                aiohttp.ClientSession(connector=connector) as session,
                session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp,
            ):
                body = await resp.text()

        data: dict[str, object] = json.loads(body)
        ip_raw = data.get("origin") or data.get("ip")
        ip = str(ip_raw) if ip_raw is not None else None
        return ProxyCheckResult(
            proxy=proxy,
            ok=True,
            ip=ip,
            latency_ms=(time.monotonic() - start) * 1000,
        )

    except Exception as exc:
        return ProxyCheckResult(
            proxy=proxy,
            ok=False,
            ip=None,
            latency_ms=(time.monotonic() - start) * 1000,
            error=str(exc),
        )


async def lookup_proxy_country(
    proxy: ProxyConfig,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
) -> tuple[str, str]:
    import aiohttp

    try:
        if proxy.scheme in ("http", "https"):
            proxy_url = f"http://{proxy.host}:{proxy.port}"
            proxy_auth = (
                aiohttp.BasicAuth(proxy.username, proxy.password) if proxy.username else None
            )
            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    _GEO_URL,
                    proxy=proxy_url,
                    proxy_auth=proxy_auth,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp,
            ):
                body = await resp.text()
        else:
            try:
                from aiohttp_socks import ProxyConnector  # type: ignore[import-untyped]
            except ImportError:
                return "", ""
            connector = ProxyConnector.from_url(proxy.to_url())
            async with (
                aiohttp.ClientSession(connector=connector) as session,
                session.get(_GEO_URL, timeout=aiohttp.ClientTimeout(total=timeout)) as resp,
            ):
                body = await resp.text()

        data: dict[str, object] = json.loads(body)
        if data.get("status") != "success":
            return "", ""
        country = str(data.get("country") or "")
        country_code = str(data.get("countryCode") or "")
        return country, country_code
    except Exception:
        return "", ""


async def check_all(
    proxies: list[ProxyConfig],
    *,
    url: str = _DEFAULT_URL,
    timeout: float = _DEFAULT_TIMEOUT,
    concurrency: int = 10,
) -> list[ProxyCheckResult]:
    sem = asyncio.Semaphore(concurrency)

    async def _one(p: ProxyConfig) -> ProxyCheckResult:
        async with sem:
            return await check_proxy(p, url=url, timeout=timeout)

    return list(await asyncio.gather(*(_one(p) for p in proxies)))
