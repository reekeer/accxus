from __future__ import annotations

import contextlib

from rigi import ComposeResult, Widget
from rigi.widgets import (
    ActionMenuItemData,
    Button,
    DataTable,
)
from textual.events import Click, MouseDown

import accxus.config as cfg
from accxus.core.proxy.checker import check_proxy, lookup_proxy_country
from accxus.types.core import ProxyConfig


class ViewProxiesTab(Widget):
    DEFAULT_CSS = """
    ViewProxiesTab {
        height: 100%;
        width: 100%;
    }
    #proxy_top_row {
        layout: horizontal;
        height: auto;
        margin-bottom: 1;
    }
    #proxy_top_row Button { margin-right: 1; }
    #proxies_table { height: 1fr; }
    """

    def compose(self) -> ComposeResult:
        with Widget(id="proxy_top_row"):
            yield Button("Refresh", id="refresh_proxies_btn", variant="primary")
            yield Button("Update Ping", id="update_proxy_ping_btn", variant="success")
        yield DataTable(
            id="proxies_table",
            cursor_type="row",
            zebra_stripes=True,
        )

    def on_mount(self) -> None:
        self.run_worker(self._load_proxies())

    def on_click(self, event: Click) -> None:
        with contextlib.suppress(Exception):
            panel = self.app.query_one("#rigi-action-panel")
            panel.remove()

    def on_mouse_down(self, event: MouseDown) -> None:
        if event.button == 3:
            event.stop()
            tbl = self.query_one("#proxies_table", DataTable)
            table_region = tbl.region
            row_in_view = event.screen_y - table_region.y - 1
            scroll_y = int(tbl.scroll_offset.y)
            row_idx = max(0, min(row_in_view + scroll_y, len(tbl.rows) - 1))
            if row_in_view >= 0:
                self._show_action_menu(row_idx, event.screen_x, event.screen_y)

    def _close_action_menu(self) -> None:
        with contextlib.suppress(Exception):
            panel = self.app.query_one("#rigi-action-panel")
            panel.remove()

    def _show_action_menu(self, row_idx: int, x: int, y: int) -> None:
        self._close_action_menu()
        proxies = list(cfg.config.proxies)
        if cfg.config.telegram_proxy and cfg.config.telegram_proxy not in proxies:
            proxies.insert(0, cfg.config.telegram_proxy)
        if row_idx < 0 or row_idx >= len(proxies):
            return
        proxy = proxies[row_idx]
        items: list[ActionMenuItemData] = [
            ActionMenuItemData(
                "Set as Telegram Proxy",
                callback=lambda p=proxy: self._set_telegram_proxy(p),
                color="green",
            ),
            ActionMenuItemData(
                "Update Ping",
                callback=lambda p=proxy: self.run_worker(self._update_one(p)),
            ),
            ActionMenuItemData(
                "Delete",
                callback=lambda p=proxy: self._do_delete(p),
                color="red",
            ),
        ]
        self.app.show_action_menu(items, title=proxy.display_name, x=x, y=y)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh_proxies_btn":
            await self._load_proxies()
        elif event.button.id == "update_proxy_ping_btn":
            await self._update_all()

    async def _load_proxies(self) -> None:
        table = self.query_one("#proxies_table", DataTable)
        table.clear(columns=True)
        table.add_column("Name", key="name")
        table.add_column("Country", key="country")
        table.add_column("Ping", key="ping")
        table.add_column("Type", key="type")
        table.add_column("Host", key="host")
        table.add_column("Port", key="port")
        table.add_column("Auth", key="auth")
        table.add_column("URL", key="url")

        proxies = list(cfg.config.proxies)
        if cfg.config.telegram_proxy and cfg.config.telegram_proxy not in proxies:
            proxies.insert(0, cfg.config.telegram_proxy)

        for proxy in proxies:
            auth = "✓" if proxy.username else "—"
            is_current = proxy == cfg.config.telegram_proxy
            name = proxy.display_name
            if is_current:
                name = f"[green]{name}[/green]"
            table.add_row(
                name,
                proxy.country_label,
                self._latency_label(proxy),
                f"[cyan]{proxy.scheme}[/cyan]",
                proxy.host,
                str(proxy.port),
                auth,
                f"[dim]{proxy.to_url()}[/dim]",
                key=self._proxy_key(proxy),
            )

        if table.row_count == 0:
            table.add_row(
                "[dim]—[/dim]",
                "[dim]—[/dim]",
                "[dim]No proxies configured[/dim]",
                "[dim]—[/dim]",
                "[dim]—[/dim]",
                "[dim]—[/dim]",
                "[dim]—[/dim]",
                "[dim]—[/dim]",
            )

    def _set_telegram_proxy(self, proxy: ProxyConfig) -> None:
        cfg.config.telegram_proxy = proxy
        cfg.save_config(cfg.config)
        self.app.notify(f"Telegram proxy set: {proxy.display_name}", severity="information")
        self.run_worker(self._load_proxies())

    async def _update_one(self, proxy: ProxyConfig) -> None:
        try:
            if not proxy.country or not proxy.country_code:
                country, country_code = await lookup_proxy_country(proxy, timeout=6.0)
                proxy.country = proxy.country or country
                proxy.country_code = proxy.country_code or country_code
            result = await check_proxy(proxy, timeout=6.0)
            if result.ok:
                proxy.exit_ip = result.ip or ""
                proxy.latency_ms = result.latency_ms
            self._save_proxy(proxy)
            self.run_worker(self._load_proxies())
            if result.ok:
                self.app.notify(
                    f"{proxy.display_name}: {result.latency_ms:.0f} ms",
                    severity="information",
                )
            else:
                self.app.notify(f"{proxy.display_name}: failed", severity="error")
        except Exception as e:
            self.app.notify(f"Update error: {e}", severity="error")

    def _do_delete(self, proxy: ProxyConfig) -> None:
        cfg.config.proxies = [
            p for p in cfg.config.proxies if self._proxy_key(p) != self._proxy_key(proxy)
        ]
        if cfg.config.telegram_proxy == proxy:
            cfg.config.telegram_proxy = None
        cfg.save_config(cfg.config)
        self.run_worker(self._load_proxies())
        self.app.notify(
            f"Proxy '{proxy.display_name}' deleted",
            severity="warning",
        )

    async def _update_all(self) -> None:
        if not cfg.config.proxies:
            self.app.notify("No saved proxies to update", severity="warning")
            return
        self.app.notify("Updating proxy ping and country...", timeout=2)
        updated: list[ProxyConfig] = []
        for proxy in cfg.config.proxies:
            if not proxy.country or not proxy.country_code:
                country, country_code = await lookup_proxy_country(proxy, timeout=6.0)
                proxy.country = proxy.country or country
                proxy.country_code = proxy.country_code or country_code
            result = await check_proxy(proxy, timeout=6.0)
            if result.ok:
                proxy.exit_ip = result.ip or ""
                proxy.latency_ms = result.latency_ms
            updated.append(proxy)
        cfg.config.proxies = updated
        if cfg.config.telegram_proxy:
            active = next(
                (
                    p
                    for p in updated
                    if self._proxy_key(p) == self._proxy_key(cfg.config.telegram_proxy)
                ),
                cfg.config.telegram_proxy,
            )
            cfg.config.telegram_proxy = active
        cfg.save_config(cfg.config)
        await self._load_proxies()
        self.app.notify("Proxy details updated", severity="information")

    def _save_proxy(self, proxy: ProxyConfig) -> None:
        for i, p in enumerate(cfg.config.proxies):
            if self._proxy_key(p) == self._proxy_key(proxy):
                cfg.config.proxies[i] = proxy
                break
        if cfg.config.telegram_proxy and self._proxy_key(
            cfg.config.telegram_proxy
        ) == self._proxy_key(proxy):
            cfg.config.telegram_proxy = proxy
        cfg.save_config(cfg.config)

    @staticmethod
    def _proxy_key(proxy: ProxyConfig) -> str:
        return f"{proxy.name}|{proxy.to_url()}"

    @staticmethod
    def _latency_label(proxy: ProxyConfig) -> str:
        return f"{proxy.latency_ms:.0f} ms" if proxy.latency_ms > 0 else "—"
