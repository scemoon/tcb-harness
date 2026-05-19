from __future__ import annotations

from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.widgets import Static, RichLog
from rich.text import Text


class LogsPanel(ScrollableContainer):
    def compose(self) -> ComposeResult:
        yield RichLog(id="log-output", highlight=True, markup=True)

    def on_mount(self):
        log = self.query_one("#log-output", RichLog)
        log.write(Text("Log panel ready.", style="dim"))

    def log(self, level: str, message: str):
        log = self.query_one("#log-output", RichLog)
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        color = {"info": "white", "warn": "yellow", "error": "red", "debug": "dim blue"}.get(
            level, "white"
        )
        log.write(Text(f"[{ts}] [{level.upper()}] {message}", style=color))
