from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import string
import time
from typing import Any

from rigi import ComposeResult, Widget
from rigi.widgets import Button, Input, Label, RichLog, Select, TextArea

import accxus.config as cfg
from accxus.core.sms.manager import SmsManager
from accxus.platforms.telegram import client as tg_client
from accxus.platforms.telegram import sessions as tg_sessions
from accxus.types.telegram import SessionInfo, SessionStatus

log = logging.getLogger(__name__)


class RegistrationTab(Widget):
    DEFAULT_CSS = """
    RegistrationTab {
        height: 100%;
        width: 100%;
        padding: 1 2;
    }
    #reg_top {
        layout: horizontal;
        height: auto;
    }
    #reg_left {
        width: 1fr;
        padding: 0 1;
    }
    #reg_center {
        width: 1fr;
        padding: 0 1;
    }
    #reg_right {
        width: 1fr;
        padding: 0 1;
    }
    #reg_country {
        height: 3;
        margin-bottom: 1;
    }
    #reg_proxy {
        height: 3;
        margin-bottom: 1;
    }
    #reg_count {
        height: 3;
        margin-bottom: 1;
    }
    #reg_btn_row {
        layout: horizontal;
        height: auto;
        margin-bottom: 1;
    }
    #reg_btn_row Button {
        margin-right: 1;
    }
    #reg_stats {
        height: auto;
        margin-bottom: 1;
    }
    #reg_first_names {
        height: 6;
        margin-bottom: 1;
    }
    #reg_usernames {
        height: 6;
        margin-bottom: 1;
    }
    #reg_log {
        height: 1fr;
        border: solid #30363d;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._stop_event = asyncio.Event()
        self._worker: Any = None

    def compose(self) -> ComposeResult:
        with Widget(id="reg_top"):
            with Widget(id="reg_left"):
                yield Label("[bold]Country[/bold]")
                yield Select(id="reg_country", options=[], prompt="Select country")
                yield Label("[bold]Proxy[/bold]")
                yield Select(id="reg_proxy", options=[], prompt="No proxy")
                yield Label("[bold]Count[/bold]")
                yield Input(value="1", id="reg_count", placeholder="How many accounts")
                with Widget(id="reg_btn_row"):
                    yield Button("Start", id="btn_start", variant="success")
                    yield Button("Stop", id="btn_stop", variant="error", disabled=True)
                yield Label("", id="reg_stats")
            with Widget(id="reg_center"):
                yield Label("[bold]First names (one per line)[/bold]")
                yield TextArea(id="reg_first_names", language=None)
            with Widget(id="reg_right"):
                yield Label("[bold]Usernames (templates: random, random:N, random:word)[/bold]")
                yield TextArea(id="reg_usernames", language=None)
        yield RichLog(id="reg_log", markup=True)

    def on_mount(self) -> None:
        self.run_worker(self._load_form_data())

    def _log(self, text: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#reg_log", RichLog).write(text)

    async def _load_form_data(self) -> None:
        proxy_options: list[tuple[str, str]] = [("No proxy", "")]
        for p in cfg.config.proxies:
            proxy_options.append((p.display_name or p.to_url(), p.to_url()))
        with contextlib.suppress(Exception):
            self.query_one("#reg_proxy", Select).set_options(proxy_options)

        self._log("[dim]Loading countries from SMS providers...[/dim]")
        try:
            manager = SmsManager.from_config(cfg.config.sms_providers)
            if not manager.active_providers:
                self._log("[yellow]No SMS providers configured[/yellow]")
                return
            results = await manager.list_countries_for_service("tg")
            options: list[tuple[str, str]] = []
            for provider_name, countries in results.items():
                for cid, name, price in countries:
                    label = f"{name} ({provider_name}) — {price:.2f} ₽"
                    value = f"{provider_name}:{cid}:{price:.2f}"
                    options.append((label, value))
            if options:
                self.query_one("#reg_country", Select).set_options(options)
                self._log(f"[green]Loaded {len(options)} countries[/green]")
            else:
                self._log("[yellow]No countries available for Telegram[/yellow]")
        except Exception as e:
            self._log(f"[red]Failed to load countries: {e}[/red]")

    def _update_stats(self) -> None:
        count_str = self.query_one("#reg_count", Input).value.strip()
        count = int(count_str) if count_str.isdigit() else 0
        country_val = self.query_one("#reg_country", Select).value
        if isinstance(country_val, str) and ":" in country_val:
            try:
                price = float(country_val.rsplit(":", 1)[1])
                total = price * count
                self.query_one("#reg_stats", Label).update(
                    f"Price: {price:.2f} ₽ | Total: {total:.2f} ₽"
                )
            except Exception:
                self.query_one("#reg_stats", Label).update("")
        else:
            self.query_one("#reg_stats", Label).update("")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "reg_country":
            self._update_stats()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_start":
            self._stop_event.clear()
            self._worker = self.run_worker(self._do_bulk_register())
            self.query_one("#btn_start", Button).disabled = True
            self.query_one("#btn_stop", Button).disabled = False
        elif bid == "btn_stop":
            self._stop_event.set()
            self._log("[yellow]Stop requested...[/yellow]")

    async def _do_bulk_register(self) -> None:
        try:
            count_str = self.query_one("#reg_count", Input).value.strip()
            count = int(count_str) if count_str.isdigit() else 1
            country_val = self.query_one("#reg_country", Select).value

            if not isinstance(country_val, str) or ":" not in country_val:
                self._log("[red]Select a country first[/red]")
                return

            parts = country_val.split(":")
            provider_name = parts[0]
            country_id = int(parts[1])

            proxy_val = self.query_one("#reg_proxy", Select).value
            proxy = None
            if isinstance(proxy_val, str) and proxy_val:
                proxy = next(
                    (
                        p
                        for p in cfg.config.proxies
                        if p.to_url() == proxy_val or p.display_name == proxy_val
                    ),
                    None,
                )

            first_names_text = self.query_one("#reg_first_names", TextArea).text
            first_names = [line.strip() for line in first_names_text.splitlines() if line.strip()]
            if not first_names:
                first_names = ["User"]

            usernames_text = self.query_one("#reg_usernames", TextArea).text
            username_templates = [
                line.strip() for line in usernames_text.splitlines() if line.strip()
            ]

            manager = SmsManager.from_config(cfg.config.sms_providers)

            self._log(f"[bold]Starting bulk registration: {count} account(s)[/bold]")

            for i in range(count):
                if self._stop_event.is_set():
                    self._log("[yellow]Stopped[/yellow]")
                    break

                self._log(f"[dim]--- Account {i + 1}/{count} ---[/dim]")
                ok = await self._register_one(
                    manager,
                    provider_name,
                    country_id,
                    proxy,
                    first_names,
                    username_templates,
                )
                if not ok and not self._stop_event.is_set():
                    self._log("[red]Failed, continuing...[/red]")

            self._log("[bold]Bulk registration finished[/bold]")
        finally:
            self.query_one("#btn_start", Button).disabled = False
            self.query_one("#btn_stop", Button).disabled = True

    async def _register_one(
        self,
        manager: SmsManager,
        provider_name: str,
        country_id: int,
        proxy: Any,
        first_names: list[str],
        username_templates: list[str],
    ) -> bool:
        from pyrogram.errors import FloodWait, PhoneNumberOccupied

        max_retries = 5
        for _ in range(max_retries):
            if self._stop_event.is_set():
                return False

            try:
                activation = await manager.get_number("tg", country_id, provider=provider_name)
                self._log(f"[green]Got number: {activation.phone}[/green]")
            except Exception as e:
                self._log(f"[red]Get number failed: {e}[/red]")
                return False

            session_name = f"reg_{activation.phone.replace('+', '')}_{int(time.time())}"
            client = tg_client.make_client(session_name, proxy=proxy)

            try:
                await client.connect()
                sent = await client.send_code(activation.phone)
            except PhoneNumberOccupied:
                self._log("[yellow]Number occupied, cancelling and waiting 2 min...[/yellow]")
                await manager.cancel(activation)
                await client.disconnect()
                for _ in range(120):
                    if self._stop_event.is_set():
                        return False
                    await asyncio.sleep(1)
                continue
            except FloodWait as e:
                self._log(f"[red]FloodWait {e.value}s[/red]")
                await manager.cancel(activation)
                await client.disconnect()
                return False
            except Exception as e:
                self._log(f"[red]Send code failed: {e}[/red]")
                await manager.cancel(activation)
                await client.disconnect()
                return False

            self._log("[dim]Waiting for SMS code...[/dim]")
            code = await manager.wait_for_code(activation, timeout=120)
            if not code:
                self._log("[red]SMS not received[/red]")
                await manager.cancel(activation)
                await client.disconnect()
                return False

            self._log(f"[dim]Code: {code}[/dim]")

            first = random.choice(first_names)
            try:
                await client.sign_in(
                    phone_number=activation.phone,
                    phone_code_hash=sent.phone_code_hash,
                    phone_code=code,
                )
            except PhoneNumberOccupied:
                self._log(
                    "[yellow]Occupied during sign-in, cancelling and waiting 2 min...[/yellow]"
                )
                await manager.cancel(activation)
                await client.disconnect()
                for _ in range(120):
                    if self._stop_event.is_set():
                        return False
                    await asyncio.sleep(1)
                continue
            except Exception:
                # Account does not exist yet — sign up
                try:
                    await client.sign_up(
                        phone_number=activation.phone,
                        phone_code_hash=sent.phone_code_hash,
                        first_name=first,
                        last_name="",
                    )
                except Exception as e:
                    self._log(f"[red]Signup failed: {e}[/red]")
                    await manager.cancel(activation)
                    await client.disconnect()
                    return False

            username = ""
            if username_templates:
                username = self._generate_username(username_templates)
                try:
                    await client.set_username(username)
                    self._log(f"[dim]Username: @{username}[/dim]")
                except Exception as e:
                    self._log(f"[yellow]Username error: {e}[/yellow]")

            try:
                me = await client.get_me()
                info = SessionInfo(
                    name=session_name,
                    phone=activation.phone,
                    first_name=first,
                    last_name="",
                    username=username,
                    user_id=me.id,
                    dc_id=await client.storage.dc_id(),
                    status=SessionStatus.VALID,
                )
                tg_sessions.update_metadata(session_name, info)
            except Exception as e:
                self._log(f"[yellow]Metadata save error: {e}[/yellow]")

            await client.disconnect()
            await manager.confirm(activation)
            self._log(f"[green]✓ Saved: {session_name}[/green]")
            return True

        self._log("[red]Max retries exceeded[/red]")
        return False

    def _generate_username(self, templates: list[str]) -> str:
        template = random.choice(templates)
        if template == "random":
            return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        if template.startswith("random:"):
            spec = template.split(":", 1)[1]
            if spec.isdigit():
                return "".join(random.choices(string.ascii_lowercase + string.digits, k=int(spec)))
            if spec == "word":
                words = [
                    "alpha",
                    "beta",
                    "gamma",
                    "delta",
                    "neo",
                    "meta",
                    "cyber",
                    "flux",
                    "nova",
                    "zen",
                ]
                return random.choice(words) + "".join(random.choices(string.digits, k=3))
        return template
