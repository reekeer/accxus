from __future__ import annotations

import logging

from rigi import ComposeResult, Widget
from rigi.widgets import Button, DataTable

from accxus.platforms.telegram import sessions as tg_sessions
from accxus.types import SessionKind
from accxus.utils.session_convert import convert_telethon_to_pyrogram

log = logging.getLogger(__name__)


class TelegramConverterTab(Widget):
    DEFAULT_CSS = """
    TelegramConverterTab {
        height: 100%;
        width: 100%;
        padding: 1 2;
    }
    #conv_top_row {
        layout: horizontal;
        height: auto;
        margin-bottom: 1;
    }
    #conv_top_row Button { margin-right: 1; }
    #conv_table { height: 1fr; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._selected: set[str] = set()

    def compose(self) -> ComposeResult:
        with Widget(id="conv_top_row"):
            yield Button("Convert", id="btn_convert", variant="primary")
            yield Button("Select All", id="btn_select_all")
            yield Button("Clear", id="btn_clear")
        yield DataTable(id="conv_table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        self._reload_table()

    def _reload_table(self) -> None:
        tbl = self.query_one("#conv_table", DataTable)
        tbl.clear(columns=True)
        tbl.add_column("", key="sel")
        tbl.add_column("Name")
        tbl.add_column("ID")
        tbl.add_column("Phone")
        tbl.add_column("Kind")
        sessions = tg_sessions.list_sessions()
        available = {s.name for s in sessions}
        self._selected.intersection_update(available)
        for info in sessions:
            kind_label = info.kind.value.lower()
            tbl.add_row(
                "●" if info.name in self._selected else "○",
                info.name,
                str(info.user_id or "—"),
                info.phone or "—",
                kind_label,
                key=info.name,
            )

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
        tbl = self.query_one("#conv_table", DataTable)
        for info in tg_sessions.list_sessions():
            tbl.update_cell(info.name, "sel", "●" if info.name in self._selected else "○")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_convert":
            await self._do_convert()
        elif event.button.id == "btn_select_all":
            self._selected = {s.name for s in tg_sessions.list_sessions() if s.kind == SessionKind.TELETHON}
            self._sync_selected_rows()
        elif event.button.id == "btn_clear":
            self._selected.clear()
            self._sync_selected_rows()

    async def _do_convert(self) -> None:
        if not self._selected:
            self.app.notify("Select at least one session", severity="warning")
            return
        sessions = tg_sessions.list_sessions()
        to_convert = [s for s in sessions if s.name in self._selected]
        if not to_convert:
            return
        converted = 0
        failed = 0
        for info in to_convert:
            if info.kind != SessionKind.TELETHON:
                continue
            src = tg_sessions.session_path(info.name)
            dest_name = f"{info.name}_pyro"
            dest = tg_sessions.session_path(dest_name)
            if dest.exists():
                self.app.notify(
                    f"Session '{dest_name}' already exists, skipping",
                    severity="warning",
                )
                failed += 1
                continue
            ok = convert_telethon_to_pyrogram(src, dest)
            if ok:
                meta = tg_sessions.load_metadata()
                meta[dest_name] = {
                    "kind": SessionKind.PYROGRAM.value,
                    "status": info.status.value,
                    "phone": info.phone,
                    "user_id": info.user_id,
                }
                tg_sessions.save_metadata(meta)
                converted += 1
                self.app.notify(
                    f"Converted '{info.name}' -> '{dest_name}'",
                    severity="information",
                )
            else:
                failed += 1
                self.app.notify(
                    f"Failed to convert '{info.name}'",
                    severity="error",
                )
        self.app.notify(
            f"Converted: {converted}, Failed: {failed}",
            severity="information" if failed == 0 else "warning",
        )
        self._selected.clear()
        self._reload_table()
