from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio

from accxus.core.proxy.checker import ProxyCheckResult, check_proxy
from accxus.core.proxy.pool import ProxyPool
from accxus.types.core import ProxyConfig

FAKE_IP = "1.2.3.4"


async def _ip_server_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    await reader.read(4096)
    body = json.dumps({"origin": FAKE_IP}).encode()
    response = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        + f"Content-Length: {len(body)}\r\n".encode()
        + b"Connection: close\r\n"
        + b"\r\n"
        + body
    )
    writer.write(response)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def _proxy_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    import urllib.parse

    try:
        raw = (await reader.readline()).decode(errors="replace").strip()
        if not raw:
            return
        parts = raw.split(" ", 2)
        if len(parts) < 2:
            return
        method, url = parts[0], parts[1]
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")

        while True:
            line = (await reader.readline()).strip()
            if not line:
                break

        t_reader, t_writer = await asyncio.open_connection(host, port)
        req = f"{method} {path} HTTP/1.0\r\nHost: {host}\r\nConnection: close\r\n\r\n"
        t_writer.write(req.encode())
        await t_writer.drain()
        response = await t_reader.read(65536)
        t_writer.close()
        await t_writer.wait_closed()

        writer.write(response)
        await writer.drain()
    except Exception:
        try:
            writer.write(b"HTTP/1.0 502 Bad Gateway\r\n\r\n")
            await writer.drain()
        except Exception:
            pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


@pytest_asyncio.fixture  # type: ignore[misc]
async def local_proxy_setup() -> AsyncGenerator[tuple[ProxyConfig, str], Any]:
    http_server = await asyncio.start_server(_ip_server_handler, "127.0.0.1", 0)
    http_port: int = http_server.sockets[0].getsockname()[1]  # type: ignore[index]

    proxy_server = await asyncio.start_server(_proxy_handler, "127.0.0.1", 0)
    proxy_port: int = proxy_server.sockets[0].getsockname()[1]  # type: ignore[index]

    proxy_cfg = ProxyConfig(scheme="http", host="127.0.0.1", port=proxy_port)
    check_url = f"http://127.0.0.1:{http_port}/"

    yield proxy_cfg, check_url

    http_server.close()
    proxy_server.close()
    await http_server.wait_closed()
    await proxy_server.wait_closed()


@pytest.mark.asyncio
async def test_proxy_check_returns_fake_ip(
    local_proxy_setup: tuple[ProxyConfig, str],
) -> None:
    proxy_cfg, check_url = local_proxy_setup
    result = await check_proxy(proxy_cfg, url=check_url, timeout=5.0)

    assert isinstance(result, ProxyCheckResult)
    assert result.ok is True, f"check_proxy failed: {result.error}"
    assert result.ip == FAKE_IP
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_proxy_check_bad_proxy_returns_error() -> None:
    dead = ProxyConfig(scheme="http", host="127.0.0.1", port=19999)
    result = await check_proxy(dead, url="http://127.0.0.1:19998/", timeout=2.0)

    assert result.ok is False
    assert result.error is not None
    assert result.ip is None


@pytest.mark.asyncio
async def test_pool_round_robin() -> None:
    p1 = ProxyConfig(scheme="http", host="127.0.0.1", port=8001)
    p2 = ProxyConfig(scheme="http", host="127.0.0.1", port=8002)
    pool = ProxyPool([p1, p2], max_concurrent=2)

    seen: list[int] = []
    for _ in range(4):
        async with pool.acquire() as proxy:
            seen.append(proxy.port)

    assert seen == [8001, 8002, 8001, 8002]


@pytest.mark.asyncio
async def test_pool_failure_marks_cooldown() -> None:
    p = ProxyConfig(scheme="http", host="127.0.0.1", port=9001)
    pool = ProxyPool([p], max_concurrent=1, cooldown=3600.0, max_failures=2)

    pool.report_failure(p)
    pool.report_failure(p)

    assert pool.available_count == 0


@pytest.mark.asyncio
async def test_pool_success_resets_failures() -> None:
    p = ProxyConfig(scheme="http", host="127.0.0.1", port=9002)
    pool = ProxyPool([p], max_concurrent=1, cooldown=3600.0, max_failures=2)

    pool.report_failure(p)
    pool.report_failure(p)
    assert pool.available_count == 0

    pool.report_success(p)
    assert pool.available_count == 1


@pytest.mark.asyncio
async def test_pool_stats_structure() -> None:
    p = ProxyConfig(scheme="socks5", host="10.0.0.1", port=1080)
    pool = ProxyPool([p], max_concurrent=5)

    stats = pool.stats()
    assert len(stats) == 1
    entry = stats[0]
    assert "proxy" in entry
    assert "failures" in entry
    assert "available" in entry
    assert entry["available"] is True


@pytest.mark.asyncio
async def test_pool_size_property() -> None:
    proxies = [ProxyConfig(scheme="http", host="127.0.0.1", port=p) for p in range(8010, 8015)]
    pool = ProxyPool(proxies, max_concurrent=10)
    assert pool.size == 5
    assert pool.available_count == 5


@pytest.mark.asyncio
async def test_pool_requires_at_least_one_proxy() -> None:
    with pytest.raises(ValueError, match="at least one"):
        ProxyPool([])
