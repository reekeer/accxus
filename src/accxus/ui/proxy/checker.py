from __future__ import annotations

from rigi import Button, ComposeResult, DataTable, Input, Label, RigiCard, RigiPane, Widget

from accxus.core.proxy.checker import check_proxy
from accxus.types.core import ProxyConfig


class ProxyCheckerTab(Widget):
    DEFAULT_CSS = """
    ProxyCheckerTab Button {
        min-width: 16;
        height: 3;
    }
    ProxyCheckerTab Input {
        height: 3;
    }
    """

    def compose(self) -> ComposeResult:
        yield RigiPane(
            RigiCard(
                Label("[bold cyan]Proxy Checker[/bold cyan]"),
                Label("[dim]Test proxy connectivity and measure latency[/dim]"),
                Input(
                    placeholder="socks5://user:pass@host:port or http://host:port",
                    id="proxy_url_input",
                ),
                Button("Check Proxy", id="check_proxy_btn", variant="primary"),
                title="  Check Proxy",
            ),
            RigiCard(
                DataTable(
                    id="proxy_check_results",
                    cursor_type="row",
                    zebra_stripes=True,
                ),
                title="  Results",
            ),
        )

    def on_mount(self) -> None:
        table = self.query_one("#proxy_check_results", DataTable)
        table.add_columns("Proxy", "Status", "IP", "Latency", "Error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "check_proxy_btn":
            await self._check_proxy()

    async def _check_proxy(self) -> None:
        input_widget = self.query_one("#proxy_url_input", Input)
        url = input_widget.value.strip()
        if not url:
            self.notify("Enter a proxy URL", severity="warning")
            return

        try:
            proxy = self._parse_proxy_url(url)
        except Exception as e:
            self.notify(f"Invalid proxy URL: {e}", severity="error")
            return

        self.notify(f"Checking {url}...", timeout=2)
        result = await check_proxy(proxy)

        table = self.query_one("#proxy_check_results", DataTable)
        status_color = "green" if result.ok else "red"
        status_text = f"[{status_color}]{'✓ OK' if result.ok else '✗ Failed'}[/{status_color}]"
        ip_text = result.ip or "—"
        latency_text = f"{result.latency_ms:.0f} ms" if result.ok else "—"
        error_text = result.error or "—"

        table.add_row(url, status_text, ip_text, latency_text, error_text)

        if result.ok:
            self.notify(
                f"✓ Proxy OK: {result.ip} ({result.latency_ms:.0f}ms)",
                severity="information",
            )
        else:
            self.notify(f"✗ Proxy failed: {result.error}", severity="error")

    @staticmethod
    def _parse_proxy_url(url: str) -> ProxyConfig:
        import urllib.parse

        parsed = urllib.parse.urlparse(url)
        if not parsed.scheme or not parsed.hostname:
            raise ValueError("Invalid proxy URL format")

        return ProxyConfig(
            scheme=parsed.scheme,  # type: ignore[arg-type]
            host=parsed.hostname,
            port=parsed.port or 1080,
            username=parsed.username or "",
            password=parsed.password or "",
        )
