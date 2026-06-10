from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static, ProgressBar


class ContextStats(Static):
    DEFAULT_CSS = """
    ContextStats {
        height: auto;
        padding: 0 1;

        Static {
            color: $text-secondary;
            margin: 0;
            padding: 0;
        }

        ProgressBar {
            margin: 0;
            padding: 0;
        }
    }
    """

    used_tokens: reactive[int] = reactive(0)
    max_tokens: reactive[int] = reactive(0)

    def __init__(
        self,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)

    def update_stats(self, used: int, max_tokens: int) -> None:
        self.used_tokens = used
        self.max_tokens = max_tokens

    def compose(self) -> ComposeResult:
        yield Static("0 tokens", id="context-tokens")
        yield ProgressBar(total=100, show_eta=False, show_percentage=False, id="context-progress")
        yield Static("0% used", id="context-percent")

    def watch_used_tokens(self, used: int) -> None:
        self._refresh_display()

    def watch_max_tokens(self, mx: int) -> None:
        self._refresh_display()

    def _refresh_display(self) -> None:
        used = self.used_tokens
        mx = self.max_tokens

        pct = (used / mx * 100) if mx > 0 else 0

        bar = self.query_one("#context-progress", ProgressBar)
        bar.update(progress=min(pct, 100), total=100)

        tokens = self.query_one("#context-tokens", Static)
        tokens.update(f"{used:,} tokens")

        pct_label = self.query_one("#context-percent", Static)
        pct_label.update(f"{pct:.0f}% used")
