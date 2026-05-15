from __future__ import annotations

from rigi import ComposeResult, Widget
from rigi.widgets import TabGroup

from accxus.ui.utils.telegram_converter import TelegramConverterTab


class TelegramTab(Widget):
    DEFAULT_CSS = """
    TelegramTab {
        height: 100%;
        width: 100%;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield TabGroup(
            [
                ("Converter", lambda: TelegramConverterTab()),
            ]
        )
