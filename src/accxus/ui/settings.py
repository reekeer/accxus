from __future__ import annotations

import contextlib
import logging

from rigi import ComposeResult, Widget
from rigi.widgets import Button, Input, Label, Rule, Static

import accxus.config as cfg

log = logging.getLogger(__name__)


class SettingsTab(Widget):
    DEFAULT_CSS = """
    SettingsTab {
        height: 100%;
        width: 100%;
        overflow-y: auto;
        padding: 1 2;
    }
    SettingsTab Label { margin-bottom: 1; }
    SettingsTab Input { margin-bottom: 1; width: 46; height: 3; }
    SettingsTab Button { height: 3; min-width: 16; }
    SettingsTab Rule { margin: 1 0; }
    #api_row { layout: horizontal; height: auto; }
    #api_row Input { width: 22; margin-right: 2; }
    #btn_row { layout: horizontal; height: auto; margin-top: 1; }
    #btn_row Button { margin-right: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Label("[bold] Global Settings[/bold]")
        yield Rule()

        yield Label("[dim]Telegram API credentials[/dim]")
        with Widget(id="api_row"):
            yield Input(value=str(cfg.config.tg_api_id), placeholder="API ID", id="inp_api_id")
            yield Input(value=cfg.config.tg_api_hash, placeholder="API Hash", id="inp_api_hash")

        yield Rule()
        yield Label("[dim]Device fingerprint (sent to Telegram)[/dim]")
        yield Input(
            value=cfg.config.tg_device_model,
            placeholder="Telegram Desktop",
            id="inp_device",
        )
        yield Input(
            value=cfg.config.tg_app_version,
            placeholder="6.3.10 x64",
            id="inp_app_ver",
        )
        yield Input(
            value=cfg.config.tg_system_version,
            placeholder="Windows 11",
            id="inp_sys_ver",
        )

        yield Rule()
        yield Label("[dim]Default Telegram proxy (leave blank to disable)[/dim]")
        proxy_url = cfg.config.telegram_proxy.to_url() if cfg.config.telegram_proxy else ""
        yield Input(value=proxy_url, placeholder="socks5://user:pass@host:port", id="inp_proxy")

        with Widget(id="btn_row"):
            yield Button("Save", id="btn_save", variant="success")
            yield Button("Reset to saved", id="btn_reload", variant="default")

        yield Static("", id="status_msg")

        yield Rule()
        yield Label("[dim]Credits[/dim]")
        yield Static(
            "Author: [bold cyan]@IMDelewer[/bold cyan]\n"
            "Maintainer: [bold magenta]@xeltorV[/bold magenta]"
        )

    def _status(self, text: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#status_msg", Static).update(text)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_save":
            await self._save()
        elif event.button.id == "btn_reload":
            self._reload()

    async def _save(self) -> None:
        api_id_s = self.query_one("#inp_api_id", Input).value.strip()
        api_hash = self.query_one("#inp_api_hash", Input).value.strip()
        device = self.query_one("#inp_device", Input).value.strip()
        app_ver = self.query_one("#inp_app_ver", Input).value.strip()
        sys_ver = self.query_one("#inp_sys_ver", Input).value.strip()
        proxy_raw = self.query_one("#inp_proxy", Input).value.strip()

        if not api_id_s.isdigit():
            self._status("[red]API ID must be a number[/red]")
            return
        if not api_hash:
            self._status("[red]API Hash cannot be empty[/red]")
            return

        cfg.config.tg_api_id = int(api_id_s)
        cfg.config.tg_api_hash = api_hash
        cfg.TG_API_ID = cfg.config.tg_api_id
        cfg.TG_API_HASH = cfg.config.tg_api_hash

        if device:
            cfg.config.tg_device_model = device
        if app_ver:
            cfg.config.tg_app_version = app_ver
        if sys_ver:
            cfg.config.tg_system_version = sys_ver

        if proxy_raw:
            try:
                from urllib.parse import urlparse

                from accxus.types.core import ProxyConfig

                p = urlparse(proxy_raw)
                cfg.config.telegram_proxy = ProxyConfig(
                    scheme=p.scheme or "socks5",  # type: ignore[arg-type]
                    host=p.hostname or "",
                    port=p.port or 1080,
                    username=p.username or "",
                    password=p.password or "",
                )
            except Exception as exc:
                self._status(f"[red]Invalid proxy URL: {exc}[/red]")
                return
        else:
            cfg.config.telegram_proxy = None

        cfg.save_config(cfg.config)
        self._status("[green]✓ Settings saved[/green]")
        self.app.notify("Settings saved", title=" Settings")

    def _reload(self) -> None:
        reloaded = cfg.load_config()
        self.query_one("#inp_api_id", Input).value = str(reloaded.tg_api_id)
        self.query_one("#inp_api_hash", Input).value = reloaded.tg_api_hash
        self.query_one("#inp_device", Input).value = reloaded.tg_device_model
        self.query_one("#inp_app_ver", Input).value = reloaded.tg_app_version
        self.query_one("#inp_sys_ver", Input).value = reloaded.tg_system_version
        proxy_url = reloaded.telegram_proxy.to_url() if reloaded.telegram_proxy else ""
        self.query_one("#inp_proxy", Input).value = proxy_url
        self._status("[dim]Reloaded from disk[/dim]")
