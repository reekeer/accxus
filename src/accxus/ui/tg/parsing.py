from __future__ import annotations

import contextlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from rigi import ComposeResult, Widget
from rigi.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    RichLog,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

import accxus.config as cfg
from accxus.platforms.telegram import parsing as tg_parsing
from accxus.platforms.telegram.sessions import list_sessions

log = logging.getLogger(__name__)

_GROUPS_FILE = cfg.DATA_DIR / "groups.json"
_SNAPSHOTS_FILE = cfg.DATA_DIR / "profile_snapshots.json"

_KIND_ICONS = {"private": "👤", "group": "👥", "channel": "📢", "other": "❓"}
_KIND_LABELS: list[tuple[str, str]] = [
    ("All", "all"),
    ("👤 Personal", "private"),
    ("👥 Groups", "group"),
    ("📢 Channels", "channel"),
]


def _load_groups() -> dict[str, Any]:
    if _GROUPS_FILE.exists():
        try:
            return json.loads(_GROUPS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_groups(groups: dict[str, Any]) -> None:
    _GROUPS_FILE.write_text(json.dumps(groups, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_snapshots() -> dict[str, Any]:
    if _SNAPSHOTS_FILE.exists():
        try:
            return json.loads(_SNAPSHOTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_snapshots(snaps: dict[str, Any]) -> None:
    _SNAPSHOTS_FILE.write_text(json.dumps(snaps, indent=2, ensure_ascii=False), encoding="utf-8")


def _session_select_choices() -> list[tuple[str, str]]:
    items = [(s.name, s.name) for s in list_sessions()]
    return items or [("—", "—")]


def _get_session(widget: Widget, sel_id: str) -> str | None:
    """Return selected session name or None if nothing is selected."""
    val = widget.query_one(sel_id, Select).value
    if not isinstance(val, str) or val == "—":
        return None
    return val


class ParsingTab(Widget):
    DEFAULT_CSS = """
    ParsingTab { height: 100%; width: 100%; }
    ParsingTab TabbedContent { height: 1fr; }
    .pform { padding: 1 2; height: 100%; overflow-y: auto; }
    .pform Label { margin-bottom: 1; }
    .pform Input { margin-bottom: 1; width: 44; }
    .pform Select { margin-bottom: 1; width: 44; }
    .prow { layout: horizontal; height: auto; margin-bottom: 1; }
    .prow Input { width: 28; margin-right: 1; }
    .prow Button { margin-right: 1; }
    .plog { height: 12; margin-top: 1; }
    #groups_table { height: 10; margin-bottom: 1; }
    #chats_table { height: 1fr; margin-bottom: 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._parsed_users: list[Any] = []
        self._fetched_dialogs: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        choices = _session_select_choices()
        with TabbedContent():
            with TabPane("Chats", id="tp_chats"), Widget(classes="pform", id="chats_pane"):
                yield Label("[bold]Chat List[/bold]")
                yield Select(choices, id="chats_sess", prompt="Select session")
                yield Select(_KIND_LABELS, value="all", id="chats_kind")
                with Widget(classes="prow"):
                    yield Button("Fetch Chats", id="btn_fetch_chats", variant="primary")
                yield Static("", id="chats_status")
                yield DataTable(id="chats_table", cursor_type="row", zebra_stripes=True)
            with TabPane("Export Chat", id="tp_export"), Widget(classes="pform", id="export_pane"):
                yield Label("[bold]Export Chat History[/bold]")
                yield Select(choices, id="exp_sess", prompt="Select session")
                yield Input(placeholder="Chat: @group / username / ID", id="exp_chat")
                yield Input(placeholder="Output file  (default: export_<chat>.json)", id="exp_out")
                yield Input(placeholder="Limit (blank = all)", id="exp_limit")
                with Widget(classes="prow"):
                    yield Button("Export JSON", id="btn_exp_json", variant="success")
                    yield Button("Export TXT", id="btn_exp_txt", variant="primary")
                yield Static("", id="exp_status")
                yield RichLog(id="export_log", markup=True, classes="plog")
            with TabPane("Parse Users", id="tp_parse"), Widget(classes="pform", id="parse_pane"):
                yield Label("[bold]Parse Group Members[/bold]")
                yield Select(choices, id="pu_sess", prompt="Select session")
                yield Input(placeholder="Group: @group / username / ID", id="pu_chat")
                with Widget(classes="prow"):
                    yield Button("Parse", id="btn_parse", variant="success")
                yield Static("", id="pu_status")
                yield Label("[dim]Save parsed users to a group:[/dim]")
                with Widget(classes="prow"):
                    yield Input(placeholder="Group name", id="pu_grp_name")
                    yield Button("Save to Group", id="btn_save_grp", disabled=True)
                yield RichLog(id="parse_log", markup=True, classes="plog")
            with TabPane("Groups", id="tp_groups"), Widget(classes="pform", id="groups_pane"):
                yield Label("[bold]Internal User Groups[/bold]")
                yield DataTable(id="groups_table", cursor_type="row", zebra_stripes=True)
                with Widget(classes="prow"):
                    yield Button("Refresh", id="btn_grp_refresh")
                    yield Button("Export Group", id="btn_grp_export", variant="primary")
                    yield Button("Delete Group", id="btn_grp_delete", variant="error")
                yield Static("", id="grp_status")
            with TabPane("Profiles", id="tp_profiles"), Widget(classes="pform", id="profiles_pane"):
                yield Label("[bold]Profile Snapshots[/bold]")
                yield Label("[dim]Save and compare user profile states over time[/dim]")
                yield Select(choices, id="prof_sess", prompt="Select session")
                yield Input(placeholder="User @username or ID", id="prof_user")
                with Widget(classes="prow"):
                    yield Button("Snapshot Now", id="btn_snap", variant="success")
                    yield Button("Show History", id="btn_prof_history")
                yield RichLog(id="profiles_log", markup=True, classes="plog")

    def on_mount(self) -> None:
        self._reload_groups_table()

    def _build_chats_pane(self) -> None:
        pane = self.query_one("#chats_pane")
        choices = _session_select_choices()
        pane.mount(Label("[bold]Chat List[/bold]"))
        pane.mount(Select(choices, id="chats_sess", prompt="Select session"))
        pane.mount(Select(_KIND_LABELS, value="all", id="chats_kind"))
        pane.mount(
            Widget(
                Button("Fetch Chats", id="btn_fetch_chats", variant="primary"),
                classes="prow",
            )
        )
        pane.mount(Static("", id="chats_status"))
        pane.mount(DataTable(id="chats_table", cursor_type="row", zebra_stripes=True))

    def _init_chats_table(self) -> None:
        tbl = self.query_one("#chats_table", DataTable)
        tbl.clear(columns=True)
        tbl.add_column("", key="kind")
        tbl.add_column("Title", key="title")
        tbl.add_column("@Username", key="uname")
        tbl.add_column("ID", key="chat_id")
        tbl.add_column("Unread", key="unread")

    async def _do_fetch_chats(self) -> None:
        session = _get_session(self, "#chats_sess")
        if not session:
            self.app.notify("Select a session first", severity="warning")
            return

        kind_val = self.query_one("#chats_kind", Select).value
        kind = str(kind_val) if isinstance(kind_val, str) else "all"

        status = self.query_one("#chats_status", Static)
        self.query_one("#btn_fetch_chats", Button).disabled = True
        status.update("[dim]Fetching chats…[/dim]")
        self._init_chats_table()

        try:
            dialogs = await tg_parsing.list_dialogs(session, kind=kind)
            self._fetched_dialogs = dialogs
            tbl = self.query_one("#chats_table", DataTable)
            for d in dialogs:
                icon = _KIND_ICONS.get(d["kind"], "❓")
                uname = f"@{d['username']}" if d["username"] else "—"
                unread = str(d["unread"]) if d["unread"] else "·"
                tbl.add_row(icon, d["title"], uname, str(d["id"]), unread)
            status.update(f"✅ {len(dialogs)} chats fetched")
            log.info("fetched %d dialogs from session %s (filter=%s)", len(dialogs), session, kind)
        except Exception as e:
            status.update(f"❌ {e}")
            log.error("fetch chats error: %s", e)
        finally:
            self.query_one("#btn_fetch_chats", Button).disabled = False

    def _build_export_pane(self) -> None:
        pane = self.query_one("#export_pane")
        choices = _session_select_choices()
        pane.mount(Label("[bold]Export Chat History[/bold]"))
        pane.mount(Select(choices, id="exp_sess", prompt="Select session"))
        pane.mount(Input(placeholder="Chat: @group / username / ID", id="exp_chat"))
        pane.mount(Input(placeholder="Output file  (default: export_<chat>.json)", id="exp_out"))
        pane.mount(Input(placeholder="Limit (blank = all)", id="exp_limit"))
        pane.mount(
            Widget(
                Button("Export JSON", id="btn_exp_json", variant="success"),
                Button("Export TXT", id="btn_exp_txt", variant="primary"),
                classes="prow",
            )
        )
        pane.mount(Static("", id="exp_status"))
        pane.mount(RichLog(id="export_log", markup=True, classes="plog"))

    def _build_parse_pane(self) -> None:
        pane = self.query_one("#parse_pane")
        choices = _session_select_choices()
        pane.mount(Label("[bold]Parse Group Members[/bold]"))
        pane.mount(Select(choices, id="pu_sess", prompt="Select session"))
        pane.mount(Input(placeholder="Group: @group / username / ID", id="pu_chat"))
        pane.mount(
            Widget(
                Button("Parse", id="btn_parse", variant="success"),
                classes="prow",
            )
        )
        pane.mount(Static("", id="pu_status"))
        pane.mount(Label("[dim]Save parsed users to a group:[/dim]"))
        pane.mount(
            Widget(
                Input(placeholder="Group name", id="pu_grp_name"),
                Button("Save to Group", id="btn_save_grp", disabled=True),
                classes="prow",
            )
        )
        pane.mount(RichLog(id="parse_log", markup=True, classes="plog"))

    def _build_groups_pane(self) -> None:
        pane = self.query_one("#groups_pane")
        pane.mount(Label("[bold]Internal User Groups[/bold]"))
        pane.mount(DataTable(id="groups_table", cursor_type="row", zebra_stripes=True))
        pane.mount(
            Widget(
                Button("Refresh", id="btn_grp_refresh"),
                Button("Export Group", id="btn_grp_export", variant="primary"),
                Button("Delete Group", id="btn_grp_delete", variant="error"),
                classes="prow",
            )
        )
        pane.mount(Static("", id="grp_status"))
        self._reload_groups_table()

    def _reload_groups_table(self) -> None:
        try:
            tbl = self.query_one("#groups_table", DataTable)
        except Exception:
            return
        tbl.clear(columns=True)
        tbl.add_columns("Group Name", "Users", "Created")
        for name, data in _load_groups().items():
            tbl.add_row(name, str(len(data.get("users", []))), data.get("created", "—"), key=name)

    def _build_profiles_pane(self) -> None:
        pane = self.query_one("#profiles_pane")
        choices = _session_select_choices()
        pane.mount(Label("[bold]Profile Snapshots[/bold]"))
        pane.mount(Label("[dim]Save and compare user profile states over time[/dim]"))
        pane.mount(Select(choices, id="prof_sess", prompt="Select session"))
        pane.mount(Input(placeholder="User @username or ID", id="prof_user"))
        pane.mount(
            Widget(
                Button("Snapshot Now", id="btn_snap", variant="success"),
                Button("Show History", id="btn_prof_history"),
                classes="prow",
            )
        )
        pane.mount(RichLog(id="profiles_log", markup=True, classes="plog"))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_fetch_chats":
            await self._do_fetch_chats()
        elif bid == "btn_exp_json":
            await self._do_export("json")
        elif bid == "btn_exp_txt":
            await self._do_export("txt")
        elif bid == "btn_parse":
            await self._do_parse()
        elif bid == "btn_save_grp":
            self._save_group()
        elif bid == "btn_grp_refresh":
            self._reload_groups_table()
        elif bid == "btn_grp_export":
            self._export_group()
        elif bid == "btn_grp_delete":
            self._delete_group()
        elif bid == "btn_snap":
            await self._do_snapshot()
        elif bid == "btn_prof_history":
            self._show_profile_history()

    async def _do_export(self, fmt: str) -> None:
        session = _get_session(self, "#exp_sess")
        chat = self.query_one("#exp_chat", Input).value.strip()
        if not session or not chat:
            self.app.notify("Select a session and enter a chat", severity="warning")
            return

        limit_raw = self.query_one("#exp_limit", Input).value.strip()
        out_raw = self.query_one("#exp_out", Input).value.strip()
        limit = int(limit_raw) if limit_raw.isdigit() else 0
        dest = Path(out_raw or f"export_{chat.lstrip('@')}.{fmt}")
        status = self.query_one("#exp_status", Static)
        log_view = self.query_one("#export_log", RichLog)

        for bid in ("btn_exp_json", "btn_exp_txt"):
            self.query_one(f"#{bid}", Button).disabled = True
        status.update("[dim]Connecting…[/dim]")

        def _prog(n: int) -> None:
            status.update(f"[dim]Fetched {n} messages…[/dim]")

        try:
            count = await tg_parsing.save_chat_history(
                session, chat, dest, fmt=fmt, limit=limit, on_progress=_prog
            )
            status.update(f"✅ {count} messages → {dest}")
            log_view.write(f"✅ Export complete: {dest}  ({count} messages)")
            log.info("export done: %s messages from %s -> %s", count, chat, dest)
        except Exception as e:
            status.update(f"❌ {e}")
            log_view.write(f"❌ Export failed: {e}")
            log.error("export error: %s", e)
        finally:
            for bid in ("btn_exp_json", "btn_exp_txt"):
                self.query_one(f"#{bid}", Button).disabled = False

    async def _do_parse(self) -> None:
        session = _get_session(self, "#pu_sess")
        chat = self.query_one("#pu_chat", Input).value.strip()
        if not session or not chat:
            self.app.notify("Select a session and enter a group", severity="warning")
            return

        status = self.query_one("#pu_status", Static)
        log_view = self.query_one("#parse_log", RichLog)
        self.query_one("#btn_parse", Button).disabled = True

        def _prog(n: int) -> None:
            status.update(f"[dim]Parsed {n} users…[/dim]")

        try:
            users = await tg_parsing.parse_chat_members(session, chat, on_progress=_prog)
            self._parsed_users = [
                {
                    "id": u.id,
                    "username": u.username,
                    "first_name": u.first_name,
                    "last_name": u.last_name,
                    "phone": u.phone,
                }
                for u in users
            ]
            status.update(f"✅ Parsed {len(users)} users")
            log_view.write(f"✅ Parsed {len(users)} users from {chat!r}")
            log.info("parsed %d users from %s", len(users), chat)
            self.query_one("#btn_save_grp", Button).disabled = False
        except Exception as e:
            status.update(f"❌ {e}")
            log_view.write(f"❌ Parse failed: {e}")
            log.error("parse error: %s", e)
        finally:
            self.query_one("#btn_parse", Button).disabled = False

    def _save_group(self) -> None:
        gname = self.query_one("#pu_grp_name", Input).value.strip()
        if not gname:
            self.app.notify("Enter a group name", severity="warning")
            return
        if not self._parsed_users:
            self.app.notify("No parsed users to save", severity="warning")
            return
        groups = _load_groups()
        groups[gname] = {
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "users": self._parsed_users,
        }
        _save_groups(groups)
        self._reload_groups_table()
        self.app.notify(f"Saved {len(self._parsed_users)} users → group '{gname}'", title="Groups")

    def _selected_group(self) -> str | None:
        try:
            tbl = self.query_one("#groups_table", DataTable)
            key = tbl.coordinate_to_cell_key(tbl.cursor_coordinate).row_key.value
            return str(key) if key is not None else None
        except Exception:
            return None

    def _export_group(self) -> None:
        name = self._selected_group()
        if not name:
            self.app.notify("Select a group first", severity="warning")
            return
        groups = _load_groups()
        data = groups.get(name)
        if not data:
            return
        dest = Path(f"group_{name}.json")
        dest.write_text(json.dumps(data["users"], indent=2, ensure_ascii=False), encoding="utf-8")
        with contextlib.suppress(Exception):
            self.query_one("#grp_status", Static).update(f"✅ → {dest}")
        self.app.notify(f"Group '{name}' exported → {dest}", title="Groups")

    def _delete_group(self) -> None:
        name = self._selected_group()
        if not name:
            self.app.notify("Select a group first", severity="warning")
            return
        groups = _load_groups()
        groups.pop(name, None)
        _save_groups(groups)
        self._reload_groups_table()
        self.app.notify(f"Group '{name}' deleted", title="Groups", severity="warning")

    async def _do_snapshot(self) -> None:
        session = _get_session(self, "#prof_sess")
        user_id = self.query_one("#prof_user", Input).value.strip()
        if not session or not user_id:
            self.app.notify("Select a session and enter a user", severity="warning")
            return

        log_view = self.query_one("#profiles_log", RichLog)
        self.query_one("#btn_snap", Button).disabled = True
        try:
            info = await tg_parsing.get_user_info(session, user_id)
            info["timestamp"] = datetime.now().isoformat()
            snaps = _load_snapshots()
            key = user_id.lstrip("@")
            snaps.setdefault(key, []).append(info)
            _save_snapshots(snaps)
            log_view.write(
                f"✅ Snapshot: "
                f"{info['first_name']} {info['last_name']}  "
                f"@{info['username'] or '—'}  "
                f"[dim]{info['timestamp']}[/dim]"
            )
            log.info("snapshot saved for %s", user_id)
        except Exception as e:
            log_view.write(f"❌ Snapshot failed: {e}")
            log.error("snapshot error: %s", e)
        finally:
            self.query_one("#btn_snap", Button).disabled = False

    def _show_profile_history(self) -> None:
        user_id = self.query_one("#prof_user", Input).value.strip()
        log_view = self.query_one("#profiles_log", RichLog)
        key = user_id.lstrip("@")
        history = _load_snapshots().get(key, [])
        if not history:
            log_view.write(f"[dim]No snapshots for {user_id!r}[/dim]")
            return
        log_view.write(f"[bold]History for {user_id}  ({len(history)} snapshots):[/bold]")
        for s in reversed(history):
            log_view.write(
                f"  [dim]{s['timestamp']}[/dim]  "
                f"{s.get('first_name','')} {s.get('last_name','')}  "
                f"@{s.get('username') or '—'}  "
                f"[dim]bio:[/dim] {s.get('bio') or '—'}"
            )
