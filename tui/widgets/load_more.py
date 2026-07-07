from __future__ import annotations

from textual.binding import Binding
from textual.message import Message
from textual.widgets import Static


class LoadMoreIndicator(Static, can_focus=True):
    """Clickable 'load earlier messages' indicator at top of conversation."""

    class LoadMorePressed(Message):
        pass

    BINDINGS = [
        Binding("enter", "press", "Load"),
    ]

    def __init__(self, count: int, batch: int = 50) -> None:
        self.count = count
        label = f"  ▲  Load {min(count, batch)} earlier messages ({count} remaining)  ▲  "
        super().__init__(label)

    def action_press(self) -> None:
        self.post_message(self.LoadMorePressed())
