from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import Any

from rigi import ComposeResult, ModalScreen, Widget
from rigi.widgets import (
    ActionMenuItemData,
    Button,
    DataTable,
    Image,
    Input,
    Label,
    Static,
)
from textual.events import Click, MouseDown

import accxus.config as cfg
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


# ---------------------------------------------------------------------------
# LoginScreen
# ---------------------------------------------------------------------------
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
            with Widget(id="step1"):
                yield Input(placeholder="Session name  (e.g. main)", id="inp_name")
                yield Input(placeholder="Phone  (+79001234567)", id="inp_phone")
                yield Button("Send Code", id="btn_send", variant="primary")
            with Widget(id="step2"):
                yield Input(placeholder="Code from Telegram app", id="inp_code")
            with Widget(id="step3"):
                yield Input(placeholder="2FA password", id="inp_2fa", password=True)
            with Widget(id="lbtn_row"):
                yield Button("Login", id="btn_login", variant="success", disabled=True)
                yield Button("Cancel", id="btn_cancel")
            yield Static("", id="lstat")

    def on_mount(self) -> None:
        self.query_one("#step2").styles.display = "none"
        self.query_one("#step3").styles.display = "none"

    def _show_step(self, step: int) -> None:
        for i in (1, 2, 3):
            widget = self.query_one(f"#step{i}", Widget)
            widget.styles.display = "block" if i == step else "none"

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
            self._show_step(2)
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
                self._show_step(3)
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
                user_id=me.id,
                dc_id=await self._client.storage.dc_id(),
            )
            tg_sessions.update_metadata(self._name, info)
            await self._client.disconnect()
            stat.update("[green]✓ Logged in successfully[/green]")
            await asyncio.sleep(0.5)
            self.dismiss(self._name)
        except Exception as e:
            stat.update(f"[red]{e}[/red]")


# ---------------------------------------------------------------------------
# ImportSessionScreen
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# RenameScreen
# ---------------------------------------------------------------------------
class RenameScreen(ModalScreen[str | None]):
    DEFAULT_CSS = """
    RenameScreen { align: center middle; }
    #ren_box {
        width: 50;
        height: auto;
        border: round $primary;
        padding: 1 2;
        background: $surface;
    }
    #ren_box Input { margin-bottom: 1; }
    #ren_row { layout: horizontal; height: auto; margin-top: 1; }
    #ren_row Button { margin-right: 1; }
    """

    def __init__(self, old_name: str) -> None:
        super().__init__()
        self._old_name = old_name

    def compose(self) -> ComposeResult:
        with Widget(id="ren_box"):
            yield Label(f"[bold] Rename — {self._old_name}[/bold]\n")
            yield Input(placeholder="New session name", id="inp_name")
            with Widget(id="ren_row"):
                yield Button("Rename", id="btn_rename", variant="success")
                yield Button("Cancel", id="btn_cancel")
            yield Static("", id="ren_stat")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_cancel":
            self.dismiss(None)
        elif event.button.id == "btn_rename":
            new_name = self.query_one("#inp_name", Input).value.strip()
            stat = self.query_one("#ren_stat", Static)
            if not new_name:
                stat.update("[red]Enter a name[/red]")
                return
            old_path = tg_sessions.session_path(self._old_name)
            new_path = tg_sessions.session_path(new_name)
            if new_path.exists():
                stat.update("[red]Name already exists[/red]")
                return
            old_path.rename(new_path)
            meta = tg_sessions.load_metadata()
            if self._old_name in meta:
                meta[new_name] = meta.pop(self._old_name)
                tg_sessions.save_metadata(meta)
            self.dismiss(new_name)


# ---------------------------------------------------------------------------
# EditProfileScreen
# ---------------------------------------------------------------------------
class EditProfileScreen(ModalScreen[bool]):
    DEFAULT_CSS = """
    EditProfileScreen { align: center middle; }
    #ep_box {
        width: 60;
        height: auto;
        border: round $primary;
        padding: 1 2;
        background: $surface;
    }
    #ep_avatar_row {
        layout: horizontal;
        height: auto;
        margin-bottom: 1;
    }
    #ep_avatar_img {
        width: 12;
        height: 6;
        margin-right: 2;
    }
    #ep_avatar_btns {
        width: 1fr;
        height: auto;
    }
    #ep_avatar_btns Button { margin-bottom: 1; }
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
            with Widget(id="ep_avatar_row"):
                yield Image(id="ep_avatar_img", width=12, height=6)
                with Widget(id="ep_avatar_btns"):
                    yield Button("Load from TG", id="btn_load_avatar")
                    yield Input(
                        placeholder="Path to new avatar",
                        id="inp_avatar_path",
                    )
                    yield Button("Set Avatar", id="btn_set_avatar", variant="primary")
                    yield Button("Delete Avatar", id="btn_del_avatar", variant="error")
            yield Input(
                value=self._info.first_name,
                placeholder="First name",
                id="inp_first",
            )
            yield Input(
                value=self._info.last_name,
                placeholder="Last name",
                id="inp_last",
            )
            yield Input(
                value=self._info.username or "",
                placeholder="Username",
                id="inp_username",
                disabled=True,
            )
            yield Input(
                value=self._info.bio,
                placeholder="Bio",
                id="inp_bio",
            )
            yield Input(
                placeholder="Date of birth (not editable)",
                id="inp_dob",
                disabled=True,
            )
            with Widget(id="ep_row"):
                yield Button("Save", id="btn_save", variant="success")
                yield Button("Cancel", id="btn_cancel")
            yield Static("", id="ep_stat")

    def on_mount(self) -> None:
        self.run_worker(self._load_avatar())

    async def _load_avatar(self) -> None:
        try:
            path = await tg_profile.download_avatar(self._session)
            if path:
                self.query_one("#ep_avatar_img", Image).load(path)
        except Exception:
            pass

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_cancel":
            self.dismiss(False)
        elif bid == "btn_save":
            await self._save()
        elif bid == "btn_load_avatar":
            self.run_worker(self._load_avatar())
        elif bid == "btn_set_avatar":
            self.run_worker(self._set_avatar())
        elif bid == "btn_del_avatar":
            self.run_worker(self._delete_avatar())

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

    async def _set_avatar(self) -> None:
        path = self.query_one("#inp_avatar_path", Input).value.strip()
        stat = self.query_one("#ep_stat", Static)
        if not path:
            stat.update("[red]Enter avatar path[/red]")
            return
        stat.update("[dim]Uploading avatar…[/dim]")
        try:
            await tg_profile.set_avatar(self._session, path)
            stat.update("[green]✓ Avatar set[/green]")
            self.query_one("#ep_avatar_img", Image).load(path)
        except Exception as e:
            stat.update(f"[red]{e}[/red]")

    async def _delete_avatar(self) -> None:
        stat = self.query_one("#ep_stat", Static)
        stat.update("[dim]Deleting avatar…[/dim]")
        try:
            await tg_profile.delete_avatar(self._session)
            stat.update("[green]✓ Avatar deleted[/green]")
            self.query_one("#ep_avatar_img", Image).load("")
        except Exception as e:
            stat.update(f"[red]{e}[/red]")


# ---------------------------------------------------------------------------
# SessionsTab
# ---------------------------------------------------------------------------
class SessionsTab(Widget):
    DEFAULT_CSS = """
    SessionsTab {
        height: 100%;
        width: 100%;
        padding: 1 2;
    }
    #sess_top_row {
        layout: horizontal;
        height: auto;
        margin-bottom: 1;
    }
    #sess_top_row Button { margin-right: 1; }
    #sess_table { height: 1fr; }
    """

    def compose(self) -> ComposeResult:
        with Widget(id="sess_top_row"):
            yield Button("＋ Add", id="btn_add", variant="primary")
            yield Button("Import", id="btn_import")
            yield Button("Refresh", id="btn_refresh")
        yield DataTable(id="sess_table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        self._reload_table()

    def _reload_table(self) -> None:
        tbl = self.query_one("#sess_table", DataTable)
        tbl.clear(columns=True)
        tbl.add_column("Name", key="name")
        tbl.add_column("ID", key="id")
        tbl.add_column("Phone", key="phone")
        tbl.add_column("Username", key="username")
        tbl.add_column("DC", key="dc")
        tbl.add_column("Status", key="status")
        for info in tg_sessions.list_sessions():
            status_str = self._status_markup(info.status)
            active_mark = " ●" if cfg.config.active_session == info.name else ""
            tbl.add_row(
                f"{info.name}{active_mark}",
                str(info.user_id or "—"),
                info.phone or "—",
                info.username or "—",
                str(info.dc_id or "—"),
                status_str,
                key=info.name,
            )

    @staticmethod
    def _status_markup(s: SessionStatus) -> str:
        return {
            SessionStatus.VALID: "[green]✓ valid[/green]",
            SessionStatus.INVALID: "[red]✗ invalid[/red]",
            SessionStatus.CHECKING: "[yellow]… checking[/yellow]",
            SessionStatus.UNKNOWN: "[dim]? unknown[/dim]",
        }.get(s, "[dim]?[/dim]")

    def on_click(self, event: Click) -> None:
        with contextlib.suppress(Exception):
            panel = self.app.query_one("#rigi-action-panel")
            panel.remove()

    def on_mouse_down(self, event: MouseDown) -> None:
        if event.button == 3:
            event.stop()
            tbl = self.query_one("#sess_table", DataTable)
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
        sessions = tg_sessions.list_sessions()
        if row_idx < 0 or row_idx >= len(sessions):
            return
        name = sessions[row_idx].name
        is_active = cfg.config.active_session == name
        items: list[ActionMenuItemData] = [
            ActionMenuItemData(
                "Validate",
                callback=lambda n=name: self.run_worker(self._validate_one(n)),
                color="green",
            ),
            ActionMenuItemData(
                "Rename",
                callback=lambda n=name: self.run_worker(self._rename(n)),
            ),
            ActionMenuItemData(
                "Edit Profile",
                callback=lambda n=name: self.run_worker(self._edit_profile(n)),
            ),
            ActionMenuItemData(
                f"Set Active {'✓' if is_active else ''}",
                callback=lambda n=name: self._set_active(n),
                disabled=is_active,
            ),
            ActionMenuItemData(
                "Delete",
                callback=lambda n=name: self._do_delete(n),
                color="red",
            ),
        ]
        self.app.show_action_menu(items, title=name, x=x, y=y)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_add":
            self.run_worker(self._handle_add())
        elif bid == "btn_import":
            self.run_worker(self._handle_import())
        elif bid == "btn_refresh":
            self._reload_table()

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

    async def _validate_one(self, name: str) -> None:
        tbl = self.query_one("#sess_table", DataTable)
        tbl.update_cell(name, "status", "[yellow]… checking[/yellow]")
        try:
            status = await tg_client.check_validity(name)
            tg_sessions.update_metadata_statuses({name: status})
            tbl.update_cell(name, "status", self._status_markup(status))
            if status == SessionStatus.VALID:
                info = await tg_client.fetch_info(name)
                tg_sessions.update_metadata(name, info)
                self._reload_table()
            self.app.notify(f"{name}: {status.value}", title=" Sessions")
        except Exception as e:
            log.exception("validate failed for %s", name)
            self.app.notify(f"Validate error: {e}", severity="error")

    async def _rename(self, name: str) -> None:
        new_name = await self.app.push_screen_wait(RenameScreen(name))
        if new_name:
            if cfg.config.active_session == name:
                cfg.config.active_session = new_name
                cfg.save_config(cfg.config)
            self._reload_table()
            self.app.notify(f"Renamed to '{new_name}'", title=" Sessions")

    async def _edit_profile(self, name: str) -> None:
        try:
            info = await tg_client.fetch_info(name)
            tg_sessions.update_metadata(name, info)
        except Exception as e:
            log.exception("fetch info failed for %s", name)
            self.app.notify(f"Fetch info error: {e}", severity="error")
            return
        updated = await self.app.push_screen_wait(EditProfileScreen(name, info))
        if updated:
            try:
                info = await tg_client.fetch_info(name)
                tg_sessions.update_metadata(name, info)
            except Exception:
                pass
            self._reload_table()
            self.app.notify("Profile updated", title=" Sessions")

    def _set_active(self, name: str) -> None:
        cfg.config.active_session = name
        cfg.save_config(cfg.config)
        self._reload_table()
        self.app.notify(f"Active session: {name}", title=" Sessions")

    def _do_delete(self, name: str) -> None:
        tg_sessions.delete_session(name)
        if cfg.config.active_session == name:
            cfg.config.active_session = None
            cfg.save_config(cfg.config)
        self._reload_table()
        self.app.notify(
            f"Session '{name}' deleted",
            title=" Sessions",
            severity="warning",
        )
