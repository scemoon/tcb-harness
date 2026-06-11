from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Static


class AgentThought(Vertical, can_focus=True):
    """The agent's 'thoughts' with collapsible header.

    During streaming: header shows "⏳ thinking:", content visible.
    After completion: header shows "- Thought" (expanded) or "+ Thought" (collapsed).
    Ctrl+X or click on header toggles expand/collapse.
    """

    HELP = """
## Agent thoughts

- **ctrl+x** Toggle expand/collapse
- **click on header** Toggle expand/collapse
- **cursor keys** Scroll text
"""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+x", "toggle", "Toggle", show=False),
        Binding("up", "scroll_up", "Scroll Up", show=False),
        Binding("down", "scroll_down", "Scroll Down", show=False),
        Binding("left", "scroll_left", "Scroll Left", show=False),
        Binding("right", "scroll_right", "Scroll Right", show=False),
        Binding("home", "scroll_home", "Scroll Home", show=False),
        Binding("end", "scroll_end", "Scroll End", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
        Binding("ctrl+pageup", "page_left", "Page Left", show=False),
        Binding("ctrl+pagedown", "page_right", "Page Right", show=False),
    ]

    ALLOW_MAXIMIZE = True

    DEFAULT_CSS = """
    AgentThought {
        height: auto;
        width: 1fr;
    }
    """

    loading: reactive[bool] = reactive(False)

    def watch_loading(self, loading: bool) -> None:
        self.set_class(loading, "-loading")

    def __init__(self, initial_content: str = "", *, replay: bool = False):
        super().__init__()
        self._initial_content = initial_content
        self._buffer: list[str] = [initial_content]
        self._completed = False
        self._collapsed = False
        self._replay = replay

    def compose(self) -> ComposeResult:
        yield Static("⏳ thinking:", id="thought-header")
        yield Static(self._initial_content, id="thought-content", markup=False)

    def on_mount(self) -> None:
        # Force proper sizing — Vertical defaults to height: 1fr which
        # collapses to 0 inside a VerticalScroll parent.
        self.styles.height = "auto"
        self.styles.min_height = 3
        self._completed = self._replay
        self._collapsed = False
        self._update_header()
        content = self.query_one("#thought-content", Static)
        content.display = True

    async def append_fragment(self, fragment: str) -> None:
        self._buffer.append(fragment)
        content = self.query_one("#thought-content", Static)
        content.update("".join(self._buffer))

    def mark_completed(self) -> None:
        if self._completed:
            return
        self._completed = True
        self._collapsed = False
        self._update_header()

    def action_toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._update_header()
        self.query_one("#thought-content", Static).display = not self._collapsed

    def on_click(self, event) -> None:
        """Toggle when the header is clicked (only after completion)."""
        if not self._completed:
            return
        if getattr(event.widget, "id", None) == "thought-header":
            self.action_toggle()
            event.stop()

    def _update_header(self) -> None:
        header = self.query_one("#thought-header", Static)
        if not self._completed:
            header.update("⏳ thinking:")
        elif self._collapsed:
            header.update("+ Thought")
        else:
            header.update("- Thought")

    # ── Forward scroll actions to inner content (Static, may be no-op) ──

    def action_scroll_up(self) -> None:
        self._try_scroll("scroll_up")

    def action_scroll_down(self) -> None:
        self._try_scroll("scroll_down")

    def action_scroll_left(self) -> None:
        self._try_scroll("scroll_left")

    def action_scroll_right(self) -> None:
        self._try_scroll("scroll_right")

    def action_scroll_home(self) -> None:
        self._try_scroll("scroll_home")

    def action_scroll_end(self) -> None:
        self._try_scroll("scroll_end")

    def action_page_up(self) -> None:
        self._try_scroll("page_up")

    def action_page_down(self) -> None:
        self._try_scroll("page_down")

    def action_page_left(self) -> None:
        self._try_scroll("page_left")

    def action_page_right(self) -> None:
        self._try_scroll("page_right")

    def _try_scroll(self, action: str) -> None:
        """Call a scroll action on the inner content if it supports it."""
        content = self.query_one("#thought-content")
        method = getattr(content, action, None)
        if callable(method):
            method()
