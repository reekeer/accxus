from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any

from rigi import RigiApp, TabDef, Setting
from rigi.layout.pane import RigiCard, RigiPane
from rigi.widgets import Label, RigiBottomPanel

import accxus.config as cfg
from accxus.ui.proxy.add import AddProxyTab
from accxus.ui.proxy.checker import ProxyCheckerTab
from accxus.ui.proxy.view import ViewProxiesTab
from accxus.ui.sms.providers import SmsProvidersTab
from accxus.ui.sms.services import SmsServicesTab
from accxus.ui.tg.add_session import AddSessionTab
from accxus.ui.tg.messages import MessagesTab
from accxus.ui.tg.parsing import ParsingTab
from accxus.ui.tg.sessions import SessionsTab

log = logging.getLogger(__name__)

_sms_balance: str = "—"


def _proxy_status() -> str:
    proxy = cfg.config.telegram_proxy
    if proxy is None:
        return "—"
    return proxy.display_name


def _make_tg_welcome() -> RigiPane:
    return RigiPane(
        RigiCard(
            Label("[dim]Choose a subtab from the left panel[/dim]"),
            Label("  Sessions  ·  Messages  ·  Parsing"),
            title="  Telegram",
        )
    )


def _write(app_: RigiApp, text: str) -> None:
    try:
        app_.query_one(RigiBottomPanel).write_output(text)
    except Exception:
        app_.notify(text)


def _build_app() -> RigiApp:
    app = RigiApp(
        name="accxus",
        version="0.2.0",
        description="Telegram session manager",
        home_tab="Telegram",
    )

    app.add_status(
        "time",
        "Time",
        lambda: datetime.datetime.now().strftime("%H:%M:%S"),
        refresh_interval=1.0,
    )
    app.add_status(
        "sms_bal",
        "SMS",
        lambda: _sms_balance,
        refresh_interval=30.0,
        style="bold cyan",
    )
    app.add_status(
        "proxy",
        "Proxy",
        _proxy_status,
        refresh_interval=2.0,
        style="bold green",
    )

    tg_tab = TabDef(name="Telegram", key="1", icon="", widget_factory=_make_tg_welcome)

    sess_sub = tg_tab.add_subtab("Sessions", SessionsTab, icon="")
    sess_sub.add_subtab("View", SessionsTab, icon="")
    sess_sub.add_subtab("Add", AddSessionTab, icon="")

    msg_sub = tg_tab.add_subtab("Messages", MessagesTab, icon="")
    msg_sub.add_subtab("Bulk", MessagesTab, icon="")

    tg_tab.add_subtab("Parsing", ParsingTab, icon="")
    app.add_tab(tg_tab)

    proxy_tab = TabDef(name="Proxies", key="2", icon="🌐")
    proxy_tab.add_subtab("Check", ProxyCheckerTab, icon="")
    proxy_tab.add_subtab("Add", AddProxyTab, icon="")
    proxy_tab.add_subtab("View", ViewProxiesTab, icon="")
    app.add_tab(proxy_tab)

    sms_tab = TabDef(name="SMS", key="3", icon="📱")
    sms_tab.add_subtab("Providers", SmsProvidersTab, icon="")
    sms_tab.add_subtab("Services", SmsServicesTab, icon="")
    app.add_tab(sms_tab)

    tg_settings = app.settings.add_page("Telegram")
    tg_settings.settings = [
        Setting(
            "API ID",
            description="Telegram API ID",
            value_fn=lambda: str(cfg.config.tg_api_id),
            write_fn=lambda v: (
                setattr(cfg.config, "tg_api_id", int(v) if v.isdigit() else cfg.config.tg_api_id),
                cfg.save_config(cfg.config)
            ),
        ),
        Setting(
            "API Hash",
            description="Telegram API Hash",
            value_fn=lambda: cfg.config.tg_api_hash,
            write_fn=lambda v: (setattr(cfg.config, "tg_api_hash", v), cfg.save_config(cfg.config)),
        ),
        Setting(
            "Device Model",
            value_fn=lambda: cfg.config.tg_device_model,
            write_fn=lambda v: (setattr(cfg.config, "tg_device_model", v), cfg.save_config(cfg.config)),
        ),
        Setting(
            "App Version",
            value_fn=lambda: cfg.config.tg_app_version,
            write_fn=lambda v: (setattr(cfg.config, "tg_app_version", v), cfg.save_config(cfg.config)),
        ),
        Setting(
            "System Version",
            value_fn=lambda: cfg.config.tg_system_version,
            write_fn=lambda v: (setattr(cfg.config, "tg_system_version", v), cfg.save_config(cfg.config)),
        ),
    ]

    credits_page = app.settings.add_page("Credits")
    credits_page.settings = [
        Setting("Author", value_fn=lambda: "@IMDelewer"),
        Setting("Maintainer", value_fn=lambda: "@xeltorV"),
    ]

    @app.on_startup
    async def _balance_loop(  # pyright: ignore[reportUnusedFunction,reportUnusedParameter]
        app_: RigiApp,
    ) -> None:
        global _sms_balance
        while True:
            await asyncio.sleep(60)
            try:
                from accxus.core.sms.manager import SmsManager

                manager = SmsManager.from_config(cfg.config.sms_providers)
                if manager.active_providers:
                    balances = await manager.get_balance_all()
                    if balances:
                        parts = [f"{b.provider}: {b.balance:.2f}" for b in balances[:3]]
                        _sms_balance = "  ".join(parts)
            except Exception:
                pass

    @app.command("session", help="Manage sessions: list / check / delete <name>")
    async def _cmd_session(  # pyright: ignore[reportUnusedFunction]
        app: RigiApp, _arg0: str = "list", _arg1: str = "", **_: Any
    ) -> None:
        action = _arg0 or "list"
        target = _arg1 or ""

        if action == "list":
            from accxus.platforms.telegram.sessions import list_sessions

            sessions = list_sessions()
            if not sessions:
                _write(app, "[dim]No sessions found.[/dim]")
                return
            _write(app, f"[bold]Sessions ({len(sessions)}):[/bold]")
            for s in sessions:
                color = "green" if s.status.value == "valid" else "red"
                name_part = f"[cyan]{s.name}[/cyan]"
                phone_part = f"[dim]{s.phone or '?'} · @{s.username or '—'}[/dim]"
                _write(app, f"  [{color}]●[/{color}] {name_part}  {phone_part}")

        elif action == "check":
            from accxus.platforms.telegram.client import check_all_validity
            from accxus.platforms.telegram.sessions import list_sessions

            sessions = list_sessions()
            _write(app, f"[dim]Checking {len(sessions)} session(s)…[/dim]")
            results = await check_all_validity([s.name for s in sessions])
            for name, status in results.items():
                color = "green" if status.value == "valid" else "red"
                _write(app, f"  [{color}]{status.value:7}[/{color}]  {name}")
            ok = sum(1 for v in results.values() if v.value == "valid")
            _write(app, f"[dim]{ok}/{len(results)} valid[/dim]")

        elif action == "delete":
            if not target:
                _write(app, "[red]Usage:[/red] session delete [bold]<name>[/bold]")
                return
            sess_file = cfg.SESSIONS_DIR / f"{target}.session"
            if not sess_file.exists():
                _write(app, f"[red]Session {target!r} not found.[/red]")
                return
            sess_file.unlink()
            _write(app, f"[green]✓ Deleted:[/green] {target}")

        elif action == "add":
            phone_hint = f" [dim]{target}[/dim]" if target else ""
            _write(app, f"[dim]Use Sessions → Add to add a new session.{phone_hint}[/dim]")

        else:
            _write(app, "[bold]session[/bold] — manage Telegram sessions")
            _write(app, "  [cyan]session list[/cyan]         list all sessions")
            _write(app, "  [cyan]session check[/cyan]        check validity")
            _write(app, "  [cyan]session add   <phone>[/cyan] add new session")
            _write(app, "  [cyan]session delete <name>[/cyan] delete a session")

    @app.command("balance", help="Fetch SMS provider balance(s)", aliases=["bal"])
    async def _cmd_balance(app: RigiApp, **_: Any) -> None:  # pyright: ignore[reportUnusedFunction]
        global _sms_balance
        from accxus.core.sms.manager import SmsManager

        manager = SmsManager.from_config(cfg.config.sms_providers)
        if not manager.active_providers:
            _write(app, "[dim]No SMS providers configured (add api_key to config).[/dim]")
            return
        _write(app, "[bold]Fetching SMS balances…[/bold]")
        balances = await manager.get_balance_all()
        if not balances:
            _write(app, "[red]All providers failed to respond.[/red]")
            return
        for b in balances:
            _write(
                app,
                f"  [cyan]{b.provider:14}[/cyan]  [green]{b.balance:.2f} {b.currency}[/green]",
            )
        parts = [f"{b.provider}: {b.balance:.2f}" for b in balances[:3]]
        _sms_balance = "  ".join(parts)

    @app.command("message", help="Send message: message <session> <target> <text>", aliases=["msg"])
    async def _cmd_message(  # pyright: ignore[reportUnusedFunction]
        app: RigiApp, args: dict[str, Any]
    ) -> None:
        session = str(args.get("_arg0", "") or "").strip()
        target = str(args.get("_arg1", "") or "").strip()
        text_parts: list[str] = []
        idx = 2
        while f"_arg{idx}" in args:
            text_parts.append(str(args[f"_arg{idx}"]))
            idx += 1
        text = " ".join(text_parts).strip()

        if not session or not target or not text:
            _write(app, "[red]Usage:[/red] message [bold]<session> <target> <text>[/bold]")
            _write(app, "[dim]Example: msg main @username Hello from accxus[/dim]")
            return

        from accxus.platforms.telegram.messaging import send_one

        _write(app, f"[dim]Sending message: {session} -> {target}[/dim]")
        result = await send_one(session, target, text)
        if result.success:
            _write(app, f"[green]✓ Sent:[/green] {session} -> {target}")
        else:
            _write(app, f"[red]✗ Failed:[/red] {session} -> {target}  {result.error}")

    @app.command("proxy", help="Proxy management: list / check / set <url>")
    async def _cmd_proxy(  # pyright: ignore[reportUnusedFunction]
        app: RigiApp, _arg0: str = "list", _arg1: str = "", _arg2: str = "", **_: Any
    ) -> None:
        action = _arg0 or "list"
        url = _arg1 or ""
        name = _arg2 or ""
        current = cfg.config.telegram_proxy

        if action == "list":
            if current:
                _write(app, f"[bold]Telegram proxy:[/bold] [cyan]{current.display_name}[/cyan]")
            if cfg.config.proxies:
                _write(app, f"[bold]Saved proxies ({len(cfg.config.proxies)}):[/bold]")
                for proxy in cfg.config.proxies:
                    marker = "●" if proxy == current else "○"
                    latency = f"{proxy.latency_ms:.0f} ms" if proxy.latency_ms > 0 else "—"
                    _write(
                        app,
                        f"  [cyan]{marker}[/cyan] {proxy.display_name} "
                        f"[dim]{proxy.country_label} · {latency} · {proxy.to_url()}[/dim]",
                    )
            elif not current:
                _write(app, "[dim]No proxy configured.  Use: proxy set <url> <name>[/dim]")
            else:
                _write(app, "[dim]No saved proxies.[/dim]")

        elif action == "check":
            if not current:
                _write(app, "[red]No proxy configured.  Use: proxy set <url>[/red]")
                return
            from accxus.core.proxy.checker import check_proxy, lookup_proxy_country

            _write(app, f"[dim]Checking {current.display_name} …[/dim]")
            if not current.country or not current.country_code:
                country, country_code = await lookup_proxy_country(current)
                current.country = current.country or country
                current.country_code = current.country_code or country_code
            result = await check_proxy(current)
            if result.ok:
                current.exit_ip = result.ip or ""
                current.latency_ms = result.latency_ms
                cfg.config.telegram_proxy = current
                cfg.config.proxies = [
                    current if p.to_url() == current.to_url() else p for p in cfg.config.proxies
                ]
                cfg.save_config(cfg.config)
                _write(
                    app,
                    f"[green]✓ OK[/green]  exit IP: [cyan]{result.ip}[/cyan]"
                    f"  [dim]{current.country_label} · {result.latency_ms:.0f} ms[/dim]",
                )
            else:
                _write(app, f"[red]✗ Failed:[/red] {result.error}")

        elif action == "set":
            if not url:
                _write(app, "[red]Usage:[/red] proxy set [bold]<url>[/bold]")
                _write(app, "[dim]Example: proxy set socks5://127.0.0.1:1080[/dim]")
                return
            import urllib.parse

            from accxus.types.core import ProxyConfig

            try:
                parsed = urllib.parse.urlparse(url)
                proxy = ProxyConfig(
                    name=name,
                    scheme=parsed.scheme,  # type: ignore[arg-type]
                    host=parsed.hostname or "",
                    port=parsed.port or 1080,
                    username=parsed.username or "",
                    password=parsed.password or "",
                )
                if not proxy.country or not proxy.country_code:
                    from accxus.core.proxy.checker import check_proxy, lookup_proxy_country

                    country, country_code = await lookup_proxy_country(proxy)
                    proxy.country = country
                    proxy.country_code = country_code
                    result = await check_proxy(proxy)
                    if result.ok:
                        proxy.exit_ip = result.ip or ""
                        proxy.latency_ms = result.latency_ms
                if not proxy.name:
                    prefix = f"{proxy.country_label} - #"
                    nums = [
                        int(p.name.removeprefix(prefix))
                        for p in cfg.config.proxies
                        if p.name.startswith(prefix) and p.name.removeprefix(prefix).isdigit()
                    ]
                    proxy.name = f"{prefix}{max(nums, default=0) + 1}"
                cfg.config.telegram_proxy = proxy
                cfg.config.proxies = [p for p in cfg.config.proxies if p.name != proxy.name]
                cfg.config.proxies.append(proxy)
                cfg.save_config(cfg.config)
                _write(app, f"[green]✓ Proxy set:[/green] {proxy.display_name}")
            except Exception as exc:
                _write(app, f"[red]Invalid proxy URL:[/red] {exc}")

        elif action == "unset":
            cfg.config.telegram_proxy = None
            cfg.save_config(cfg.config)
            _write(app, "[green]✓ Proxy removed.[/green]")

        else:
            _write(app, "[bold]proxy[/bold] — manage the Telegram proxy")
            _write(app, "  [cyan]proxy list[/cyan]            show current proxy")
            _write(app, "  [cyan]proxy check[/cyan]           test connectivity")
            _write(app, "  [cyan]proxy set   <url> <name>[/cyan] set proxy URL")
            _write(app, "  [cyan]proxy unset[/cyan]           remove proxy")

    @app.command("sessions", help="Go to Sessions tab", aliases=["sess"])
    async def _cmd_sessions(  # pyright: ignore[reportUnusedFunction]
        app: RigiApp, **_: Any
    ) -> None:
        app.navigate_to_tab("Telegram")

    @app.command("logs", help="Open the live log viewer")
    async def _cmd_logs(app: RigiApp, **_: Any) -> None:  # pyright: ignore[reportUnusedFunction]
        app.navigate_to_tab("Logs")

    @app.command("crash", help="Emergency kill: crash yes — stop all tasks and exit immediately")
    async def _cmd_crash(  # pyright: ignore[reportUnusedFunction]
        app: RigiApp, _arg0: str = "", **_: Any
    ) -> None:
        confirm = _arg0 or ""
        if confirm.lower() != "yes":
            _write(app, "[yellow]Usage:[/yellow] crash yes  — kills all tasks and exits NOW")
            return
        _write(app, "[bold red]EMERGENCY CRASH — killing all tasks and exiting…[/bold red]")
        log.critical("crash yes — emergency exit triggered by user")
        import os as _os
        import signal as _signal

        _os.kill(_os.getpid(), _signal.SIGKILL)

    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    app = _build_app()
    RigiApp.run_cli(app)


if __name__ == "__main__":
    main()
