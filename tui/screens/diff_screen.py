from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from tui.widgets.diff_view import make_diff


class DiffScreen(ModalScreen[None]):
    """Full-screen view of a file diff.

    Opened when a file is selected from the ModifiedFiles sidebar. Displays
    the same DiffView widget that ``Conversation.post_diff`` would have mounted
    inline, but as a dedicated modal screen instead of a conversation block.
    """

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close", show=False, priority=True),
        Binding("q", "dismiss(None)", "Close", show=False, priority=True),
    ]

    DEFAULT_CSS = """
    DiffScreen {
        background: $surface;
    }

    #diff-header {
        dock: top;
        width: 100%;
        padding: 1 2;
        background: $panel;
        color: $text-primary;
        text-style: bold;
        height: 3;
    }

    #diff-header-meta {
        color: $text-muted;
        text-style: none;
    }

    #diff-scroll {
        width: 100%;
        height: 1fr;
        padding: 0 1 0 1;
    }

    #diff-scroll > DiffView {
        width: 100%;
        height: auto;
    }
    """

    def __init__(
        self,
        path: str,
        before: str | None,
        after: str,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._path = path
        self._before = before
        self._after = after

    def compose(self) -> ComposeResult:
        filename = self._path.rsplit("/", 1)[-1] or self._path
        meta = "untracked" if self._before is None else "modified"
        yield Static(
            f"[b]📝 {filename}[/b]  [#888888]{meta}[/]",
            id="diff-header",
            markup=True,
        )
        with VerticalScroll(id="diff-scroll"):
            yield make_diff(self._path, self._path, self._before, self._after)

    def on_mount(self) -> None:
        self.title = f"Diff: {self._path}"