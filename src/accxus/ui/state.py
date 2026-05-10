from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field


@dataclass
class AppState:
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=1000))


state = AppState()


class _UiLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.WARNING:
            return

        color_map = {
            "DEBUG": "dim",
            "INFO": "cyan",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold red",
        }
        color = color_map.get(record.levelname, "white")
        msg = self.format(record)
        state.logs.append(f"[{color}]{record.levelname:8}[/{color}]  {msg}")


_handler = _UiLogHandler()
_handler.setFormatter(logging.Formatter("%(name)s  %(message)s"))
logging.getLogger().addHandler(_handler)
