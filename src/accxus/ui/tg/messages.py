from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable

from rigi import ComposeResult, Widget
from rigi.widgets import Button, DataTable, Input, Label, RichLog, TextArea
from rigi.widgets.bottom_panel import RigiBottomPanel

from accxus.core.types import SendResult
from accxus.platforms.telegram import messaging as tg_msg
from accxus.platforms.telegram.sessions import list_sessions

log = logging.getLogger(__name__)


class MessagesTab(Widget):
    DEFAULT_CSS = """
    MessagesTab {
        layout: horizontal;
        height: 100%;
        width: 100%;
    }
    #msg_left {
        width: 30;
        height: 100%;
        padding: 1;
    }
    #msg_center {
        width: 1fr;
        height: 100%;
        padding: 1 2;
    }
    #msg_left Label { margin-bottom: 1; }
    #msg_session_buttons {
        layout: horizontal;
        height: auto;
        margin-bottom: 1;
    }
    #msg_session_buttons Button {
        margin-right: 1;
        height: 3;
        min-width: 8;
    }
    #sess_list { height: 1fr; }
    #selected_status { height: auto; margin-top: 1; }
    #targets_area { height: 7; margin-bottom: 1; }
    #msg_area { height: 8; margin-bottom: 1; }
    #hint { height: auto; margin-bottom: 1; }
    #msg_log { height: 1fr; min-height: 6; margin-top: 1; }
    #ctrl_row { layout: horizontal; height: auto; align: left middle; }
    #ctrl_row Button { margin-right: 1; height: 3; }
    #ctrl_row Label { margin-right: 1; }
    #delay_inp { width: 14; height: 3; margin-right: 1; }
    #retry_inp { width: 8; height: 3; margin-right: 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._selected: set[str] = set()
        self._running: bool = False
        self._stop: bool = False
        self._send_task: asyncio.Task[None] | None = None

    def compose(self) -> ComposeResult:
        with Widget(id="msg_left"):
            yield Label("[bold]Sessions[/bold]\n[dim]Select row, then Toggle/Enter[/dim]")
            with Widget(id="msg_session_buttons"):
                yield Button("Toggle", id="btn_toggle_session")
                yield Button("All", id="btn_select_all")
                yield Button("Refresh", id="btn_refresh_sessions")
            yield DataTable(id="sess_list", cursor_type="row", zebra_stripes=True)
            yield Label("[dim]Selected: 0[/dim]", id="selected_status")

        with Widget(id="msg_center"):
            yield Label("[bold]Targets[/bold] [dim](one per line: @user / +phone / id)[/dim]")
            yield TextArea(id="targets_area", language=None)
            yield Label("[bold]Message template[/bold]")
            yield TextArea(id="msg_area", language=None)
            yield Label(
                "[dim]{name}  {phone}  {username}  {random}  {random:N}  {random:word}[/dim]",
                id="hint",
            )
            with Widget(id="ctrl_row"):
                yield Button("Send All", id="btn_send", variant="success")
                yield Button("Stop", id="btn_stop", variant="error", disabled=True)
                yield Input(value="1.0", id="delay_inp", placeholder="delay (sec)")
                yield Label("[dim]s delay[/dim]")
                yield Input(value="1", id="retry_inp", placeholder="retries")
                yield Label("[dim]retries[/dim]")
            yield RichLog(id="msg_log", markup=True)

    def on_mount(self) -> None:
        self._reload_sessions()

    def _reload_sessions(self) -> None:
        tbl = self.query_one("#sess_list", DataTable)
        tbl.clear(columns=True)
        tbl.add_column("", key="sel")
        tbl.add_column("Session")
        tbl.add_column("Phone")
        sessions = list_sessions()
        available = {info.name for info in sessions}
        self._selected.intersection_update(available)
        for info in sessions:
            tbl.add_row("○", info.name, info.phone or "—", key=info.name)
        self._sync_selected_rows()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = str(event.row_key.value) if event.row_key.value is not None else None
        if not key:
            return
        if key in self._selected:
            self._selected.discard(key)
        else:
            self._selected.add(key)
        self._sync_selected_rows()

    def _sync_selected_rows(self) -> None:
        tbl = self.query_one("#sess_list", DataTable)
        for info in list_sessions():
            tbl.update_cell(info.name, "sel", "●" if info.name in self._selected else "○")
        self.query_one("#selected_status", Label).update(
            f"[dim]Selected: {len(self._selected)}[/dim]"
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "btn_send":
            self._queue_send()
        elif event.button.id == "btn_stop":
            self._stop = True
            log.info("stop requested by user")
            self._write_log("[yellow]Stop requested[/yellow]")
        elif event.button.id == "btn_toggle_session":
            self._toggle_focused_session()
        elif event.button.id == "btn_select_all":
            self._select_all_sessions()
        elif event.button.id == "btn_refresh_sessions":
            self._reload_sessions()

    def _focused_session(self) -> str | None:
        tbl = self.query_one("#sess_list", DataTable)
        try:
            key = tbl.coordinate_to_cell_key(tbl.cursor_coordinate).row_key.value
        except Exception:
            return None
        return str(key) if key is not None else None

    def _toggle_focused_session(self) -> None:
        key = self._focused_session()
        if not key:
            self.app.notify("Select a session row first", severity="warning")
            self._write_log("[yellow]No focused session row[/yellow]")
            return
        if key in self._selected:
            self._selected.discard(key)
        else:
            self._selected.add(key)
        log.info("message session toggled: %s selected=%s", key, key in self._selected)
        self._sync_selected_rows()

    def _select_all_sessions(self) -> None:
        sessions = {info.name for info in list_sessions()}
        if self._selected == sessions:
            self._selected.clear()
        else:
            self._selected = sessions
        log.info("message sessions selected: %d", len(self._selected))
        self._sync_selected_rows()

    def _write_log(self, text: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#msg_log", RichLog).write(text)
        with contextlib.suppress(Exception):
            self.app.query_one(RigiBottomPanel).write_output(text)

    def _queue_send(self) -> None:
        if self._send_task is not None and not self._send_task.done():
            self._write_log("[yellow]Send already running[/yellow]")
            log.warning("send already running")
            return
        self._send_task = asyncio.create_task(self._start_send())

    async def _start_send(self) -> None:
        self._running = True
        self._stop = False
        self.query_one("#btn_send", Button).disabled = True
        self.query_one("#btn_stop", Button).disabled = False
        self._write_log("[dim]Send All clicked[/dim]")
        log.info("send all clicked")
        targets_raw = self.query_one("#targets_area", TextArea).text.strip()
        template = self.query_one("#msg_area", TextArea).text.strip()
        delay_raw = self.query_one("#delay_inp", Input).value.strip()
        retry_raw = self.query_one("#retry_inp", Input).value.strip()

        if not self._selected:
            focused = self._focused_session()
            if focused:
                self._selected.add(focused)
                self._sync_selected_rows()
                self._write_log(f"[dim]Auto-selected focused session: {focused}[/dim]")
            else:
                self.app.notify("Select at least one session", severity="warning")
                self._write_log("[yellow]Send not started: no session selected[/yellow]")
                log.warning("bulk send not started: no session selected")
                self._running = False
                self._stop = False
                self.query_one("#btn_send", Button).disabled = False
                self.query_one("#btn_stop", Button).disabled = True
                return
        if not targets_raw or not template:
            self.app.notify("Fill in targets and message template", severity="warning")
            self._write_log(
                "[yellow]Send not started: targets or message template is empty[/yellow]"
            )
            log.warning("bulk send not started: targets/template empty")
            self._running = False
            self._stop = False
            self.query_one("#btn_send", Button).disabled = False
            self.query_one("#btn_stop", Button).disabled = True
            return

        targets = [t.strip() for t in targets_raw.splitlines() if t.strip()]
        if not targets:
            self.app.notify("Add at least one target", severity="warning")
            self._write_log("[yellow]Send not started: no targets[/yellow]")
            log.warning("bulk send not started: no targets")
            self._running = False
            self._stop = False
            self.query_one("#btn_send", Button).disabled = False
            self.query_one("#btn_stop", Button).disabled = True
            return
        delay = float(delay_raw) if delay_raw.replace(".", "", 1).isdigit() else 1.0
        retries = int(retry_raw) if retry_raw.isdigit() and int(retry_raw) >= 1 else 1
        sessions = list(self._selected)
        log_view = self.query_one("#msg_log", RichLog)
        log_view.clear()
        self._write_log(
            f"[dim]Sending {len(sessions)} session(s) × {len(targets)} target(s)...[/dim]"
        )

        log.info(
            "starting bulk send: %d session(s), %d target(s), delay=%.1fs, retries=%d",
            len(sessions),
            len(targets),
            delay,
            retries,
        )

        def _on_result(r: SendResult) -> None:
            if r.success:
                log.info("sent OK: [%s] -> %s", r.session, r.target)
                self._write_log(f"[green]OK[/green]   [{r.session}] -> {r.target}")
            else:
                log.error("send FAIL: [%s] -> %s  %s", r.session, r.target, r.error)
                self._write_log(f"[red]FAIL[/red] [{r.session}] -> {r.target}  {r.error}")

        try:
            await self._run_send(sessions, targets, template, delay, retries, _on_result)
        finally:
            self._running = False
            self._stop = False
            self.query_one("#btn_send", Button).disabled = False
            self.query_one("#btn_stop", Button).disabled = True
            self._send_task = None

    async def _run_send(
        self,
        sessions: list[str],
        targets: list[str],
        template: str,
        delay: float,
        retries: int,
        on_result: Callable[..., None],
    ) -> None:
        try:
            await tg_msg.send_bulk(
                sessions=sessions,
                targets=targets,
                template=template,
                delay=delay,
                retries=retries,
                on_result=on_result,
                stop_flag=lambda: self._stop,
            )
        except Exception as e:
            log.exception("bulk send error")
            self._write_log(f"[red]Bulk send error:[/red] {e}")
        finally:
            self._write_log("[dim]Done[/dim]")
            log.info("bulk send done")
