from __future__ import annotations

import asyncio
import logging
from typing import Any

from rigi import ComposeResult, ModalScreen, Widget
from rigi.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    Static,
)

from accxus.platforms.telegram import (
    client as tg_client,
)
from accxus.platforms.telegram import (
    profile as tg_profile,
)
from accxus.platforms.telegram import (
    sessions as tg_sessions,
)
from accxus.types import SessionInfo, SessionStatus

log = logging.getLogger(__name__)


class LoginScreen(ModalScreen[str | None]):
    DEFAULT_CSS = """
    LoginScreen { align: center middle; }
    #lbox {
        width: 56;
        height: auto;
        border: round $primary;
        padding: 1 2;
        background: $surface;
    }
    #lbox Label { margin-bottom: 1; }
    #lbox Input { margin-bottom: 1; }
    #lbtn_row { layout: horizontal; height: auto; margin-top: 1; }
    #lbtn_row Button { margin-right: 1; }
    #code_row, #twofa_row { display: none; }
    #code_row.show, #twofa_row.show { display: block; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._hash: str = ""
        self._client: Any = None
        self._needs_2fa: bool = False
        self._phone: str = ""
        self._name: str = ""

    def compose(self) -> ComposeResult:
        with Widget(id="lbox"):
            yield Label("[bold] Add New Telegram Session[/bold]\n")
            yield Input(placeholder="Session name  (e.g. main)", id="inp_name")
            yield Input(placeholder="Phone  (+79001234567)", id="inp_phone")
            yield Button("Send Code", id="btn_send", variant="primary")
            with Widget(id="code_row"):
                yield Input(placeholder="Code from Telegram app", id="inp_code")
            with Widget(id="twofa_row"):
                yield Input(placeholder="2FA password", id="inp_2fa", password=True)
            with Widget(id="lbtn_row"):
                yield Button("Login", id="btn_login", variant="success", disabled=True)
                yield Button("Cancel", id="btn_cancel")
            yield Static("", id="lstat")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_cancel":
            if self._client and self._client.is_connected:
                await self._client.disconnect()
            self.dismiss(None)
        elif bid == "btn_send":
            await self._send_code()
        elif bid == "btn_login":
            if self._needs_2fa:
                await self._check_2fa()
            else:
                await self._do_login()

    async def _send_code(self) -> None:
        from pyrogram.errors import FloodWait

        name = self.query_one("#inp_name", Input).value.strip()
        phone = self.query_one("#inp_phone", Input).value.strip()
        stat = self.query_one("#lstat", Static)
        if not name:
            stat.update("[red]Enter a session name[/red]")
            return
        if not phone:
            stat.update("[red]Enter the phone number[/red]")
            return
        self._name, self._phone = name, phone
        stat.update("[dim]Connecting…[/dim]")
        self.query_one("#btn_send", Button).disabled = True
        try:
            self._client = tg_client.make_client(name)
            await self._client.connect()
            sent = await self._client.send_code(phone)
            self._hash = sent.phone_code_hash
            self.query_one("#code_row").add_class("show")
            self.query_one("#btn_login", Button).disabled = False
            stat.update(f"[green]Code sent to {phone} — enter it below[/green]")
        except FloodWait as e:
            stat.update(f"[red]FloodWait — retry in {e.value}s[/red]")
            self.query_one("#btn_send", Button).disabled = False
        except Exception as e:
            stat.update(f"[red]{e}[/red]")
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
        stat = self.query_one("#lstat", Static)
        if not code:
            stat.update("[red]Enter the code[/red]")
            return
        stat.update("[dim]Signing in…[/dim]")
        self.query_one("#btn_login", Button).disabled = True
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
                self.query_one("#twofa_row").add_class("show")
                self.query_one("#btn_login", Button).disabled = False
                stat.update("[yellow]2FA enabled — enter password above, then click Login[/yellow]")
                return
            except (PhoneCodeInvalid, PhoneCodeExpired) as e:
                stat.update(f"[red]{type(e).__name__} — request a new code[/red]")
                self.query_one("#btn_login", Button).disabled = False
                return
            await self._finish()
        except Exception as e:
            stat.update(f"[red]{e}[/red]")
            self.query_one("#btn_login", Button).disabled = False

    async def _check_2fa(self) -> None:
        password = self.query_one("#inp_2fa", Input).value.strip()
        stat = self.query_one("#lstat", Static)
        if not password:
            stat.update("[red]Enter the 2FA password[/red]")
            return
        stat.update("[dim]Checking 2FA…[/dim]")
        self.query_one("#btn_login", Button).disabled = True
        try:
            await self._client.check_password(password)
            await self._finish()
        except Exception as e:
            stat.update(f"[red]{e}[/red]")
            self.query_one("#btn_login", Button).disabled = False

    async def _finish(self) -> None:
        stat = self.query_one("#lstat", Static)
        try:
            me = await self._client.get_me()
            phone = f"+{me.phone_number}" if me.phone_number else self._phone
            from accxus.types.telegram import SessionInfo  # noqa: PLC0415

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
            stat.update("[green]✓ Logged in successfully[/green]")
            await asyncio.sleep(0.5)
            self.dismiss(self._name)
        except Exception as e:
            stat.update(f"[red]{e}[/red]")


class ImportSessionScreen(ModalScreen[str | None]):
    DEFAULT_CSS = """
    ImportSessionScreen { align: center middle; }
    #imp_box {
        width: 60;
        height: auto;
        border: round $primary;
        padding: 1 2;
        background: $surface;
    }
    #imp_box Input { margin-bottom: 1; }
    #imp_row { layout: horizontal; height: auto; margin-top: 1; }
    #imp_row Button { margin-right: 1; }
    """

    def compose(self) -> ComposeResult:
        with Widget(id="imp_box"):
            yield Label("[bold] Import Session File[/bold]\n")
            yield Label("[dim]Supports: Pyrogram .session and Telethon .session files[/dim]")
            yield Input(placeholder="Path to .session file", id="inp_src")
            yield Input(placeholder="New session name", id="inp_name")
            with Widget(id="imp_row"):
                yield Button("Import", id="btn_imp", variant="success")
                yield Button("Cancel", id="btn_cancel")
            yield Static("", id="imp_stat")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_cancel":
            self.dismiss(None)
        elif event.button.id == "btn_imp":
            await self._do_import()

    async def _do_import(self) -> None:
        from pathlib import Path

        src_raw = self.query_one("#inp_src", Input).value.strip()
        name = self.query_one("#inp_name", Input).value.strip()
        stat = self.query_one("#imp_stat", Static)
        if not src_raw or not name:
            stat.update("[red]Fill in both fields[/red]")
            return
        src = Path(src_raw).expanduser()
        self.query_one("#btn_imp", Button).disabled = True
        ok, msg = tg_sessions.import_session(src, name)
        if ok:
            stat.update(f"[green]✓ {msg}[/green]")
            await asyncio.sleep(0.5)
            self.dismiss(name)
        else:
            stat.update(f"[red]{msg}[/red]")
            self.query_one("#btn_imp", Button).disabled = False


class EditProfileScreen(ModalScreen[bool]):
    DEFAULT_CSS = """
    EditProfileScreen { align: center middle; }
    #ep_box {
        width: 56;
        height: auto;
        border: round $primary;
        padding: 1 2;
        background: $surface;
    }
    #ep_box Input { margin-bottom: 1; }
    #ep_row { layout: horizontal; height: auto; margin-top: 1; }
    #ep_row Button { margin-right: 1; }
    """

    def __init__(self, session_name: str, info: SessionInfo) -> None:
        super().__init__()
        self._session = session_name
        self._info = info

    def compose(self) -> ComposeResult:
        with Widget(id="ep_box"):
            yield Label(f"[bold] Edit Profile — {self._session}[/bold]\n")
            yield Input(value=self._info.first_name, placeholder="First name", id="inp_first")
            yield Input(value=self._info.last_name, placeholder="Last name", id="inp_last")
            yield Input(value=self._info.bio, placeholder="Bio", id="inp_bio")
            with Widget(id="ep_row"):
                yield Button("Save", id="btn_save", variant="success")
                yield Button("Cancel", id="btn_cancel")
            yield Static("", id="ep_stat")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_cancel":
            self.dismiss(False)
        elif event.button.id == "btn_save":
            await self._save()

    async def _save(self) -> None:
        first = self.query_one("#inp_first", Input).value.strip()
        last = self.query_one("#inp_last", Input).value.strip()
        bio = self.query_one("#inp_bio", Input).value.strip()
        stat = self.query_one("#ep_stat", Static)
        stat.update("[dim]Saving…[/dim]")
        self.query_one("#btn_save", Button).disabled = True
        try:
            await tg_profile.update_profile(
                self._session, first_name=first, last_name=last, bio=bio
            )
            stat.update("[green]✓ Profile updated[/green]")
            await asyncio.sleep(0.4)
            self.dismiss(True)
        except Exception as e:
            stat.update(f"[red]{e}[/red]")
            self.query_one("#btn_save", Button).disabled = False


class SetAvatarScreen(ModalScreen[bool]):
    DEFAULT_CSS = """
    SetAvatarScreen { align: center middle; }
    #av_box {
        width: 60;
        height: auto;
        border: round $primary;
        padding: 1 2;
        background: $surface;
    }
    #av_box Input { margin-bottom: 1; }
    #av_row { layout: horizontal; height: auto; margin-top: 1; }
    #av_row Button { margin-right: 1; }
    """

    def __init__(self, session_name: str) -> None:
        super().__init__()
        self._session = session_name

    def compose(self) -> ComposeResult:
        with Widget(id="av_box"):
            yield Label(f"[bold] Set Avatar — {self._session}[/bold]\n")
            yield Label("[dim]Full path to an image file (jpg / png)[/dim]")
            yield Input(placeholder="/home/user/photo.jpg", id="inp_path")
            with Widget(id="av_row"):
                yield Button("Upload", id="btn_upload", variant="success")
                yield Button("Cancel", id="btn_cancel")
            yield Static("", id="av_stat")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_cancel":
            self.dismiss(False)
        elif event.button.id == "btn_upload":
            await self._upload()

    async def _upload(self) -> None:
        path = self.query_one("#inp_path", Input).value.strip()
        stat = self.query_one("#av_stat", Static)
        stat.update("[dim]Uploading…[/dim]")
        self.query_one("#btn_upload", Button).disabled = True
        try:
            await tg_profile.set_avatar(self._session, path)
            stat.update("[green]✓ Avatar updated[/green]")
            await asyncio.sleep(0.4)
            self.dismiss(True)
        except Exception as e:
            stat.update(f"[red]{e}[/red]")
            self.query_one("#btn_upload", Button).disabled = False


class ExportChatScreen(ModalScreen[bool]):
    DEFAULT_CSS = """
    ExportChatScreen { align: center middle; }
    #ec_box {
        width: 62;
        height: auto;
        border: round $primary;
        padding: 1 2;
        background: $surface;
    }
    #ec_box Input { margin-bottom: 1; }
    #ec_row { layout: horizontal; height: auto; margin-top: 1; }
    #ec_row Button { margin-right: 1; }
    """

    def __init__(self, session_name: str) -> None:
        super().__init__()
        self._session = session_name

    def compose(self) -> ComposeResult:
        with Widget(id="ec_box"):
            yield Label(f"[bold] Export Chat — {self._session}[/bold]\n")
            yield Input(placeholder="Chat: @group / username / chat_id", id="inp_chat")
            yield Input(placeholder="Output file  (default: export_<chat>.json)", id="inp_out")
            yield Input(placeholder="Limit messages (blank = all)", id="inp_limit")
            with Widget(id="ec_row"):
                yield Button("Export JSON", id="btn_json", variant="success")
                yield Button("Export TXT", id="btn_txt", variant="primary")
                yield Button("Cancel", id="btn_cancel")
            yield Static("", id="ec_stat")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_cancel":
            self.dismiss(False)
        elif event.button.id in ("btn_json", "btn_txt"):
            fmt = "json" if event.button.id == "btn_json" else "txt"
            await self._do_export(fmt)

    async def _do_export(self, fmt: str) -> None:
        from pathlib import Path

        from accxus.platforms.telegram import parsing as tg_parsing

        chat = self.query_one("#inp_chat", Input).value.strip()
        out_raw = self.query_one("#inp_out", Input).value.strip()
        limit_raw = self.query_one("#inp_limit", Input).value.strip()
        stat = self.query_one("#ec_stat", Static)
        if not chat:
            stat.update("[red]Enter a chat username or ID[/red]")
            return
        limit = int(limit_raw) if limit_raw.isdigit() else 0
        dest = Path(out_raw or f"export_{chat.lstrip('@')}.{fmt}")
        stat.update("[dim]Exporting…[/dim]")
        for btn_id in ("btn_json", "btn_txt"):
            self.query_one(f"#{btn_id}", Button).disabled = True

        def _progress(n: int) -> None:
            stat.update(f"[dim]Fetched {n} messages…[/dim]")

        try:
            count = await tg_parsing.save_chat_history(
                self._session, chat, dest, fmt=fmt, limit=limit, on_progress=_progress
            )
            stat.update(f"[green]✓ Exported {count} messages → {dest}[/green]")
        except Exception as e:
            stat.update(f"[red]{e}[/red]")
        finally:
            for btn_id in ("btn_json", "btn_txt"):
                self.query_one(f"#{btn_id}", Button).disabled = False


class SessionsTab(Widget):
    DEFAULT_CSS = """
    SessionsTab {
        layout: horizontal;
        height: 100%;
        width: 100%;
    }
    #sess_left {
        width: 40;
        height: 100%;
        padding: 1;
    }
    #sess_right {
        width: 1fr;
        height: 100%;
        padding: 1 2;
    }
    #sess_top_row {
        layout: horizontal;
        height: auto;
        margin-bottom: 1;
    }
    #sess_top_row Button { margin-right: 1; }
    #sess_table { height: 1fr; }
    #sess_bot_row {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    #sess_bot_row Button { margin-right: 1; }
    #detail_info { height: auto; margin-bottom: 1; }
    #action_row {
        layout: horizontal;
        height: auto;
    }
    #action_row Button { margin-right: 1; margin-bottom: 1; }
    """

    _accessed: str | None = None
    _info: SessionInfo | None = None

    def compose(self) -> ComposeResult:
        with Widget(id="sess_left"):
            with Widget(id="sess_top_row"):
                yield Button("＋ Add", id="btn_add", variant="primary")
                yield Button("Import", id="btn_import")
                yield Button("✓ Check All", id="btn_check_all")
            yield DataTable(id="sess_table", cursor_type="row", zebra_stripes=True)
            with Widget(id="sess_bot_row"):
                yield Button("Access", id="btn_access", variant="success")
                yield Button("Delete", id="btn_delete", variant="error")

        with Widget(id="sess_right"):
            yield Static(
                "[dim]Select a session, then click [bold]Access[/bold] to load its info[/dim]",
                id="detail_info",
            )
            with Widget(id="action_row"):
                yield Button("Edit Profile", id="btn_edit", disabled=True)
                yield Button("Set Avatar", id="btn_avatar", disabled=True)
                yield Button("Export Chat", id="btn_export", disabled=True)

    def on_mount(self) -> None:
        self._reload_table()

    def _reload_table(self) -> None:
        tbl = self.query_one("#sess_table", DataTable)
        tbl.clear(columns=True)
        tbl.add_column("Session", key="name")
        tbl.add_column("Phone", key="phone")
        tbl.add_column("DC", key="dc")
        tbl.add_column("Status", key="status")
        for info in tg_sessions.list_sessions():
            status_str = self._status_markup(info.status)
            tbl.add_row(
                info.name, info.phone or "—", str(info.dc_id or "—"), status_str, key=info.name
            )

    @staticmethod
    def _status_markup(s: SessionStatus) -> str:
        return {
            SessionStatus.VALID: "[green]✓ valid[/green]",
            SessionStatus.INVALID: "[red]✗ invalid[/red]",
            SessionStatus.CHECKING: "[yellow]… checking[/yellow]",
            SessionStatus.UNKNOWN: "[dim]? unknown[/dim]",
        }.get(s, "[dim]?[/dim]")

    def _selected_name(self) -> str | None:
        tbl = self.query_one("#sess_table", DataTable)
        try:
            key = tbl.coordinate_to_cell_key(tbl.cursor_coordinate).row_key.value
            return str(key) if key is not None else None
        except Exception:
            return None

    def _set_action_btns(self, enabled: bool) -> None:
        for bid in ("btn_edit", "btn_avatar", "btn_export"):
            self.query_one(f"#{bid}", Button).disabled = not enabled

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_add":
            self.run_worker(self._handle_add())

        elif bid == "btn_import":
            self.run_worker(self._handle_import())

        elif bid == "btn_check_all":
            await self._check_all()

        elif bid == "btn_access":
            name = self._selected_name()
            if name:
                await self._do_access(name)
            else:
                self.app.notify("Select a session first", severity="warning")

        elif bid == "btn_delete":
            name = self._selected_name()
            if name:
                self._do_delete(name)
            else:
                self.app.notify("Select a session first", severity="warning")

        elif bid == "btn_edit" and self._accessed and self._info:
            self.run_worker(self._handle_edit())

        elif bid == "btn_avatar" and self._accessed:
            self.run_worker(self._handle_avatar())

        elif bid == "btn_export" and self._accessed:
            self.run_worker(self._handle_export())

    async def _handle_add(self) -> None:
        name = await self.app.push_screen_wait(LoginScreen())
        if name:
            self._reload_table()
            self.app.notify(f"Session '{name}' added", title=" Sessions")

    async def _handle_import(self) -> None:
        name = await self.app.push_screen_wait(ImportSessionScreen())
        if name:
            self._reload_table()
            self.app.notify(f"Session '{name}' imported", title=" Sessions")

    async def _handle_edit(self) -> None:
        if self._accessed and self._info:
            updated = await self.app.push_screen_wait(EditProfileScreen(self._accessed, self._info))
            if updated:
                await self._do_access(self._accessed)

    async def _handle_avatar(self) -> None:
        if self._accessed:
            await self.app.push_screen_wait(SetAvatarScreen(self._accessed))

    async def _handle_export(self) -> None:
        if self._accessed:
            await self.app.push_screen_wait(ExportChatScreen(self._accessed))

    async def _do_access(self, name: str) -> None:
        detail = self.query_one("#detail_info", Static)
        detail.update("[dim]Connecting…[/dim]")
        self._set_action_btns(False)
        try:
            info = await tg_client.fetch_info(name)
            tg_sessions.update_metadata(name, info)
            self._accessed = name
            self._info = info
            self._reload_table()
            kind_label = f"[dim]({info.kind.name.lower()})[/dim]"
            detail.update(
                f"[bold]{info.first_name} {info.last_name}[/bold]  "
                f"{'@' + info.username if info.username else ''}\n"
                f"[dim]Phone:[/dim]   {info.phone or '—'}\n"
                f"[dim]DC:[/dim]      {info.dc_id or '—'}\n"
                f"[dim]Bio:[/dim]     {info.bio or '—'}\n"
                f"[dim]Session:[/dim] {name}.session  {kind_label}"
            )
            self._set_action_btns(True)
        except Exception as e:
            detail.update(f"[red]Connection error: {e}[/red]")
            log.exception(f"[sessions] access failed for {name!r}")

    async def _check_all(self) -> None:
        sessions = tg_sessions.list_sessions()
        if not sessions:
            self.app.notify("No sessions to check", severity="warning")
            return
        self.app.notify(f"Checking {len(sessions)} sessions…", title=" Sessions")
        tbl = self.query_one("#sess_table", DataTable)
        for info in sessions:
            tbl.update_cell(info.name, "status", "[yellow]… checking[/yellow]")

        names = [s.name for s in sessions]
        results = await tg_client.check_all_validity(names)

        tg_sessions.update_metadata_statuses(results)
        sessions_by_name = {info.name: info for info in tg_sessions.list_sessions()}
        for name, status in results.items():
            tbl.update_cell(name, "status", self._status_markup(status))
            if name in sessions_by_name:
                tbl.update_cell(name, "dc", str(sessions_by_name[name].dc_id or "—"))
        valid = sum(1 for s in results.values() if s == SessionStatus.VALID)
        self.app.notify(f"✓ {valid}/{len(results)} valid", title=" Sessions")

    def _do_delete(self, name: str) -> None:
        tg_sessions.delete_session(name)
        if self._accessed == name:
            self._accessed = None
            self._info = None
            self.query_one("#detail_info", Static).update(
                "[dim]Select a session, then click [bold]Access[/bold] to load its info[/dim]"
            )
            self._set_action_btns(False)
        self._reload_table()
        self.app.notify(f"Session '{name}' deleted", title=" Sessions", severity="warning")
