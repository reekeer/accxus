from __future__ import annotations

from rigi import Button, ComposeResult, DataTable, Label, RigiCard, RigiPane, Widget

import accxus.config as cfg
from accxus.core.proxy.checker import check_proxy, lookup_proxy_country
from accxus.types.core import ProxyConfig


class ViewProxiesTab(Widget):
    DEFAULT_CSS = """
    ViewProxiesTab Button {
        min-width: 16;
        height: 3;
    }
    """

    def compose(self) -> ComposeResult:
        yield RigiPane(
            RigiCard(
                Label("[bold cyan]Configured Proxies[/bold cyan]"),
                Label("[dim]View and manage your proxy configuration[/dim]"),
                Button("Refresh", id="refresh_proxies_btn", variant="primary"),
                Button("Update Ping", id="update_proxy_ping_btn", variant="success"),
                Label("[dim]Select a row to make it the Telegram proxy[/dim]"),
                title="  Proxies",
            ),
            RigiCard(
                DataTable(
                    id="proxies_table",
                    cursor_type="row",
                    zebra_stripes=True,
                ),
                title="  Proxy List",
            ),
            RigiCard(
                Label(id="telegram_proxy_info", markup=True),
                Button("Clear Telegram Proxy", id="clear_tg_proxy_btn", variant="error"),
                title="  Telegram Proxy",
            ),
        )

    def on_mount(self) -> None:
        self.run_worker(self._load_proxies())

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh_proxies_btn":
            await self._load_proxies()
        elif event.button.id == "update_proxy_ping_btn":
            await self._update_proxy_details()
        elif event.button.id == "clear_tg_proxy_btn":
            await self._clear_telegram_proxy()

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key.value
        if not isinstance(key, str) or key == "__current__":
            return
        proxy = next((p for p in cfg.config.proxies if self._proxy_key(p) == key), None)
        if proxy is None:
            return
        cfg.config.telegram_proxy = proxy
        cfg.save_config(cfg.config)
        self.notify(f"Telegram proxy set: {proxy.display_name}", severity="information")
        await self._load_proxies()

    async def _load_proxies(self) -> None:
        table = self.query_one("#proxies_table", DataTable)
        table.clear(columns=True)
        table.add_columns("Name", "Country", "Ping", "Type", "Host", "Port", "Auth", "URL")

        tg_info = self.query_one("#telegram_proxy_info", Label)
        if cfg.config.telegram_proxy:
            proxy = cfg.config.telegram_proxy
            label = proxy.display_name
            tg_info.update(
                f"[bold]Current:[/bold] [cyan]{label}[/cyan]\n"
                f"[dim]{proxy.country_label} · {self._latency_label(proxy)} · "
                f"{proxy.scheme} · {proxy.host}:{proxy.port}[/dim]"
            )
        else:
            tg_info.update("[dim]No Telegram proxy configured[/dim]")

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

    async def _clear_telegram_proxy(self) -> None:
        cfg.config.telegram_proxy = None
        cfg.save_config(cfg.config)
        self.notify("✓ Telegram proxy cleared", severity="information")
        await self._load_proxies()

    async def _update_proxy_details(self) -> None:
        if not cfg.config.proxies:
            self.notify("No saved proxies to update", severity="warning")
            return
        self.notify("Updating proxy ping and country...", timeout=2)
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
        self.notify("Proxy details updated", severity="information")

    @staticmethod
    def _proxy_key(proxy: ProxyConfig) -> str:
        return f"{proxy.name}|{proxy.to_url()}"

    @staticmethod
    def _latency_label(proxy: ProxyConfig) -> str:
        return f"{proxy.latency_ms:.0f} ms" if proxy.latency_ms > 0 else "—"
