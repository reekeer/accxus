from __future__ import annotations

import contextlib
import urllib.parse

from rigi import ComposeResult, Widget
from rigi.layout.pane import Card, Pane
from rigi.widgets import Button, Input, Label, Select, Static

import accxus.config as cfg
from accxus.core.proxy.checker import check_proxy, lookup_proxy_country
from accxus.types.core import ProxyConfig


class AddProxyTab(Widget):
    DEFAULT_CSS = """
    AddProxyTab Pane {
        overflow-y: auto;
    }
    AddProxyTab Card {
        height: auto;
    }
    AddProxyTab Button {
        min-width: 18;
        height: 3;
        margin-right: 1;
    }
    AddProxyTab Input {
        height: 3;
        margin-bottom: 1;
    }
    AddProxyTab Select {
        height: 3;
        margin-bottom: 1;
    }
    .button-row {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Pane(
            Card(
                Label("[bold cyan]Add Proxy[/bold cyan]"),
                Label("[dim]Add a new proxy to your configuration[/dim]"),
                Label("\n[bold]Name[/bold]"),
                Input(placeholder="Auto: Flag Country - #1", id="proxy_name"),
                Label("\n[bold]Method #1 - Auto[/bold]"),
                Input(
                    placeholder="socks5://username:password@127.0.0.1:1080",
                    id="proxy_auto_url",
                ),
                Label("\n[bold]Method #2 - Manual[/bold]"),
                Label("\n[bold]Schema:[/bold]"),
                Select(
                    id="proxy_scheme",
                    options=[
                        ("SOCKS5", "socks5"),
                        ("SOCKS4", "socks4"),
                        ("HTTP", "http"),
                        ("HTTPS", "https"),
                    ],
                    value="socks5",
                ),
                Label("[dim]Host (ip:port):[/dim]"),
                Input(placeholder="127.0.0.1:1080", id="proxy_host_port"),
                Label("[dim]Credentials (username@password):[/dim]"),
                Input(placeholder="username@password", id="proxy_credentials", password=True),
                Label(""),
                Widget(
                    Button("Save", id="add_proxy_btn", variant="primary"),
                    classes="button-row",
                ),
                Static("", id="proxy_status"),
                title="  Add Proxy",
            ),
            Card(
                Label(id="proxy_preview", markup=True),
                title="  Preview",
            ),
        )

    def on_input_changed(self, _: Input.Changed) -> None:
        self._update_preview()

    def on_select_changed(self, _: Select.Changed) -> None:
        self._update_preview()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add_proxy_btn":
            await self._add_proxy()

    def _update_preview(self) -> None:
        with contextlib.suppress(Exception):
            proxy = self._get_proxy_from_inputs()
            self.query_one("#proxy_preview", Label).update(f"[cyan]{proxy.to_url()}[/cyan]")

    def _get_proxy_from_inputs(self) -> ProxyConfig:
        name = self.query_one("#proxy_name", Input).value.strip()
        auto_url = self.query_one("#proxy_auto_url", Input).value.strip()
        scheme = self.query_one("#proxy_scheme", Select).value
        host_port = self.query_one("#proxy_host_port", Input).value.strip()
        credentials = self.query_one("#proxy_credentials", Input).value.strip()

        if auto_url:
            parsed = urllib.parse.urlparse(auto_url)
            if not parsed.scheme or not parsed.hostname:
                raise ValueError("Auto proxy must be a full URL")
            return ProxyConfig(
                name=name,
                scheme=parsed.scheme,  # type: ignore[arg-type]
                host=parsed.hostname,
                port=parsed.port or 1080,
                username=urllib.parse.unquote(parsed.username or ""),
                password=urllib.parse.unquote(parsed.password or ""),
            )

        if not host_port:
            raise ValueError("Enter Auto URL or Manual host ip:port")

        host, sep, port_str = host_port.rpartition(":")
        if not sep or not host or not port_str:
            raise ValueError("Host must be in ip:port format")
        try:
            port = int(port_str)
        except ValueError as e:
            raise ValueError("Port must be a number") from e

        username = ""
        password = ""
        if credentials:
            username, sep, password = credentials.partition("@")
            if not sep:
                raise ValueError("Credentials must be username@password")

        return ProxyConfig(
            name=name,
            scheme=scheme,  # type: ignore[arg-type]
            host=host,
            port=port,
            username=username,
            password=password,
        )

    async def _add_proxy(self) -> None:
        status = self.query_one("#proxy_status", Static)
        try:
            proxy = self._get_proxy_from_inputs()
            status.update("[dim]Saving proxy...[/dim]")
            proxy = await self._prepare_proxy(proxy)
            cfg.config.telegram_proxy = proxy
            cfg.config.proxies = [p for p in cfg.config.proxies if p.name != proxy.name]
            cfg.config.proxies.append(proxy)
            cfg.save_config(cfg.config)
            label = proxy.display_name
            status.update(f"[green]✓ Proxy saved: {label}[/green]")
            self.notify(f"✓ Proxy saved: {label}", severity="information")
            self.query_one("#proxy_name", Input).value = ""
            self.query_one("#proxy_auto_url", Input).value = ""
            self.query_one("#proxy_host_port", Input).value = ""
            self.query_one("#proxy_credentials", Input).value = ""
        except Exception as e:
            status.update(f"[red]Error: {e}[/red]")
            self.notify(f"Failed to save proxy: {e}", severity="error")

    async def _prepare_proxy(self, proxy: ProxyConfig) -> ProxyConfig:
        if not proxy.country or not proxy.country_code:
            country, country_code = await lookup_proxy_country(proxy, timeout=6.0)
            proxy.country = proxy.country or country
            proxy.country_code = proxy.country_code or country_code
        result = await check_proxy(proxy, timeout=6.0)
        if result.ok:
            proxy.exit_ip = result.ip or ""
            proxy.latency_ms = result.latency_ms
        if not proxy.name:
            proxy.name = self._next_auto_name(proxy)
        return proxy

    @staticmethod
    def _next_auto_name(proxy: ProxyConfig) -> str:
        base = proxy.country_label
        prefix = f"{base} - #"
        nums: list[int] = []
        for saved in cfg.config.proxies:
            if saved.name.startswith(prefix):
                suffix = saved.name.removeprefix(prefix)
                if suffix.isdigit():
                    nums.append(int(suffix))
        return f"{prefix}{max(nums, default=0) + 1}"
