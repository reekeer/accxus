from __future__ import annotations

import contextlib
import logging
from typing import Any

from rigi import ComposeResult, Widget
from rigi.widgets import Button, Input, Label, Rule, Static

import accxus.config as cfg
from accxus.platforms.telegram import sessions as tg_sessions
from accxus.types.core import ProxyConfig
from accxus.types.telegram import SessionInfo

log = logging.getLogger(__name__)


class AddSessionTab(Widget):
    DEFAULT_CSS = """
    AddSessionTab {
        height: 100%;
        width: 100%;
        overflow-y: auto;
        padding: 1 2;
    }
    AddSessionTab Label { margin-bottom: 1; }
    AddSessionTab Input { margin-bottom: 1; width: 46; height: 3; }
    AddSessionTab Button { height: 3; min-width: 16; }
    AddSessionTab Rule  { margin: 1 0; }
    #top_form { display: block; }
    #top_form.hidden { display: none; }
    #credentials_row { layout: horizontal; height: auto; }
    #credentials_row Input { width: 22; margin-right: 2; }
    #send_row { layout: horizontal; height: auto; margin-bottom: 1; }
    #send_row Button { margin-right: 1; }
    #code_section { display: none; }
    #code_section.show { display: block; }
    #twofa_section { display: none; margin-top: 0; }
    #twofa_section.show { display: block; }
    #login_row { layout: horizontal; height: auto; margin-top: 1; }
    #login_row Button { margin-right: 1; }
    """

    _client: Any = None
    _hash: str = ""
    _name: str = ""
    _phone: str = ""
    _needs_2fa: bool = False

    def compose(self) -> ComposeResult:
        yield Label("[bold] Add Session by Phone[/bold]")
        yield Rule()

        with Widget(id="top_form"):
            yield Label("[dim]Session name[/dim]")
            yield Input(placeholder="my_account", id="inp_name")

            yield Label("[dim]Phone number[/dim]")
            yield Input(placeholder="+79001234567", id="inp_phone")

            yield Label("[dim]API credentials (leave blank to use global config)[/dim]")
            with Widget(id="credentials_row"):
                yield Input(value=str(cfg.TG_API_ID), placeholder="API ID", id="inp_api_id")
                yield Input(value=cfg.TG_API_HASH, placeholder="API Hash", id="inp_api_hash")

            yield Label("[dim]Proxy (optional, e.g. socks5://user:pass@host:port)[/dim]")
            yield Input(placeholder="socks5://127.0.0.1:1080", id="inp_proxy")

            with Widget(id="send_row"):
                yield Button("Send Code", id="btn_send", variant="primary")
                yield Button("Reset", id="btn_reset", variant="default")

        yield Rule()

        with Widget(id="code_section"):
            yield Label("[bold]Code from Telegram:[/bold]")
            yield Input(placeholder="12345", id="inp_code")

            with Widget(id="twofa_section"):
                yield Label("[bold]2FA Password:[/bold]")
                yield Input(placeholder="••••••••", id="inp_2fa", password=True)

            with Widget(id="login_row"):
                yield Button("Login", id="btn_login", variant="success")
                yield Button("Validate", id="btn_validate", variant="primary")
                yield Button("Reset", id="btn_reset2", variant="default")

        yield Static("", id="status_msg")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_send":
            await self._send_code()
        elif bid == "btn_login":
            if self._needs_2fa:
                await self._check_2fa()
            else:
                await self._do_login()
        elif bid == "btn_validate":
            await self._validate_code()
        elif bid in ("btn_reset", "btn_reset2"):
            await self._reset()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        inp_id = event.input.id
        if inp_id == "inp_code" and not self._needs_2fa:
            await self._do_login()
        elif inp_id == "inp_2fa" and self._needs_2fa:
            await self._check_2fa()

    def _status(self, text: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#status_msg", Static).update(text)

    def _collapse_form(self) -> None:
        self.query_one("#top_form").add_class("hidden")
        self.query_one("#code_section").add_class("show")

    def _show_2fa_section(self) -> None:
        self.query_one("#twofa_section").add_class("show")
        with contextlib.suppress(Exception):
            self.query_one("#inp_2fa", Input).focus()

    async def _validate_code(self) -> None:
        code = self.query_one("#inp_code", Input).value.strip()
        if not code:
            self._status("[red]Enter the code first[/red]")
            return
        if not code.isdigit():
            self._status("[yellow]Warning: Code should contain only digits[/yellow]")
            return
        if len(code) != 5:
            self._status("[yellow]Warning: Code is usually 5 digits[/yellow]")
            return
        self._status("[green]✓ Code format looks valid[/green]")

    def _parse_proxy(self) -> ProxyConfig | None:
        raw = self.query_one("#inp_proxy", Input).value.strip()
        if not raw:
            return None
        try:
            from urllib.parse import urlparse

            p = urlparse(raw)
            return ProxyConfig(
                scheme=p.scheme or "socks5",  # type: ignore[arg-type]
                host=p.hostname or "",
                port=p.port or 1080,
                username=p.username or "",
                password=p.password or "",
            )
        except Exception as e:
            self._status(f"[red]Invalid proxy URL: {e}[/red]")
            return None

    async def _send_code(self) -> None:
        from pyrogram.errors import FloodWait

        from accxus.platforms.telegram.client import make_client

        name = self.query_one("#inp_name", Input).value.strip()
        phone = self.query_one("#inp_phone", Input).value.strip()
        api_id_s = self.query_one("#inp_api_id", Input).value.strip()
        api_hash = self.query_one("#inp_api_hash", Input).value.strip()

        if not name:
            self._status("[red]Enter a session name[/red]")
            return
        if not phone:
            self._status("[red]Enter a phone number[/red]")
            return

        self._name, self._phone = name, phone
        proxy = self._parse_proxy()
        api_id = int(api_id_s) if api_id_s.isdigit() else cfg.TG_API_ID
        _hash = api_hash or cfg.TG_API_HASH

        self.query_one("#btn_send", Button).disabled = True
        self._status("[dim]Connecting…[/dim]")
        try:
            self._client = make_client(name, api_id=api_id, api_hash=_hash, proxy=proxy)
            await self._client.connect()
            sent = await self._client.send_code(phone)
            self._hash = sent.phone_code_hash
            self._collapse_form()
            self._status(f"[green]Code sent to {phone} — enter it below[/green]")
        except FloodWait as e:
            self._status(f"[red]FloodWait {e.value}s — try again later[/red]")
            self.query_one("#btn_send", Button).disabled = False
        except Exception as e:
            self._status(f"[red]{e}[/red]")
            self.query_one("#btn_send", Button).disabled = False
            if self._client and self._client.is_connected:
                await self._client.disconnect()
            self._client = None

    async def _do_login(self) -> None:
        from pyrogram.errors import (
            PhoneCodeExpired,
            PhoneCodeInvalid,
            PhoneNumberUnoccupied,
            SessionPasswordNeeded,
        )

        code = self.query_one("#inp_code", Input).value.strip()
        if not code:
            self._status("[red]Enter the code[/red]")
            return
        self.query_one("#btn_login", Button).disabled = True
        self.query_one("#btn_validate", Button).disabled = True
        self._status("[dim]Signing in…[/dim]")
        try:
            try:
                await self._client.sign_in(
                    phone_number=self._phone,
                    phone_code_hash=self._hash,
                    phone_code=code,
                )
            except PhoneNumberUnoccupied:
                await self._client.sign_up(
                    phone_number=self._phone,
                    phone_code_hash=self._hash,
                    phone_code=code,
                    first_name="User",
                )
            except SessionPasswordNeeded:
                self._needs_2fa = True
                self._show_2fa_section()
                self._status("[yellow]2FA required — enter password below and click Login[/yellow]")
                self.query_one("#btn_login", Button).disabled = False
                self.query_one("#btn_validate", Button).disabled = False
                return
            except (PhoneCodeInvalid, PhoneCodeExpired) as e:
                self._status(f"[red]{type(e).__name__}[/red]")
                self.query_one("#btn_login", Button).disabled = False
                self.query_one("#btn_validate", Button).disabled = False
                return
            await self._finish()
        except Exception as e:
            self._status(f"[red]{e}[/red]")
            self.query_one("#btn_login", Button).disabled = False
            self.query_one("#btn_validate", Button).disabled = False

    async def _check_2fa(self) -> None:
        password = self.query_one("#inp_2fa", Input).value.strip()
        if not password:
            self._status("[red]Enter the 2FA password[/red]")
            return
        self.query_one("#btn_login", Button).disabled = True
        self._status("[dim]Checking 2FA…[/dim]")
        try:
            await self._client.check_password(password)
            await self._finish()
        except Exception as e:
            self._status(f"[red]{e}[/red]")
            self.query_one("#btn_login", Button).disabled = False

    async def _finish(self) -> None:
        try:
            me = await self._client.get_me()
            phone = f"+{me.phone_number}" if me.phone_number else self._phone
            info = SessionInfo(
                name=self._name,
                phone=phone,
                first_name=me.first_name or "",
                last_name=me.last_name or "",
                username=me.username or "",
                dc_id=await self._client.storage.dc_id(),
            )
            tg_sessions.update_metadata(self._name, info)
            await self._client.disconnect()
            self._client = None
            full = f"{info.first_name} {info.last_name}".strip()
            self._status(
                f"[green]✓ Logged in as [bold]{full}[/bold] "
                f"(@{info.username or '—'})  {phone}[/green]"
            )
            self.app.notify(f"Session '{self._name}' added", title=" Add Session")
        except Exception as e:
            self._status(f"[red]{e}[/red]")

    async def _reset(self) -> None:
        if self._client and self._client.is_connected:
            with contextlib.suppress(Exception):
                await self._client.disconnect()
        self._client = None
        self._hash = self._name = self._phone = ""
        self._needs_2fa = False
        self.query_one("#top_form").remove_class("hidden")
        self.query_one("#code_section").remove_class("show")
        self.query_one("#twofa_section").remove_class("show")
        self.query_one("#btn_send", Button).disabled = False
        with contextlib.suppress(Exception):
            self.query_one("#btn_login", Button).disabled = False
            self.query_one("#btn_validate", Button).disabled = False
        for inp in ("#inp_code", "#inp_2fa"):
            with contextlib.suppress(Exception):
                self.query_one(inp, Input).value = ""
        self._status("[dim]Reset. Enter phone and click Send Code.[/dim]")
