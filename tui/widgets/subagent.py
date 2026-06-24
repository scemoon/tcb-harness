from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.reactive import var
from textual.widgets import Markdown, Static
from textual.widgets.markdown import MarkdownStream

from tui.pill import pill
from tui.protocol import ExpandProtocol


class SubAgentHeader(Static):
    ALLOW_SELECT = False
    DEFAULT_CSS = """
    SubAgentHeader {
        width: auto;
        max-width: 1fr;
    }
    """


class SubAgentContent(Markdown):
    DEFAULT_CSS = """
    SubAgentContent {
        margin: 0 1 0 2;
    }
    """


class SubAgent(Vertical, can_focus=True):
    """Sub-agent output — collapsible block with thinking-style header.

    During streaming: header shows "🧠 {agent_type}: {prompt_preview}", content visible.
    After completion: header shows "- {agent_type}" with content still visible.
    Ctrl+X or click on completed header to toggle expand/collapse.

    Content is rendered as Markdown.
    """

    HELP = """
## Sub-agent

- **ctrl+x** Toggle expand/collapse
- **click on header** Toggle expand/collapse
- **cursor keys** Scroll text
"""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+x", "toggle", "Toggle", show=False, priority=True),
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
    SubAgent {
        height: auto;
        width: 1fr;
        SubAgentHeader {
            color: $text-secondary;
        }
        &.-status-running SubAgentHeader {
            color: $text-warning;
            text-style: italic;
        }
        &.-status-completed SubAgentHeader {
            color: $text-success;
        }
    }
    """

    agent_type: var[str] = var("")
    status: var[str] = var("running")

    def __init__(
        self,
        agent_type: str,
        tool_id: str | None = None,
        prompt: str = "",
    ) -> None:
        super().__init__(id=tool_id)
        self.agent_type = agent_type
        self.prompt = prompt
        self.status = "running"
        self._chunks: list[str] = []
        self._stream: MarkdownStream | None = None
        self._completed = False
        self._collapsed = False
        self._mounted = False

    def compose(self) -> ComposeResult:
        self.set_class(True, f"-status-{self.status}")
        label = pill(self.agent_type, "$warning-muted", "$text-warning")
        yield SubAgentHeader(
            f"🧠 {self._prompt_preview()} {label}",
            markup=False,
            id="subagent-header",
        )
        yield SubAgentContent("")

    def on_mount(self) -> None:
        self._mounted = True
        self.styles.height = "auto"
        self.styles.min_height = 3
        content = self.query_one(SubAgentContent)
        content.styles.height = "auto"
        if self._chunks:
            self._stream = Markdown.get_stream(content)
            for chunk in self._chunks:
                self._stream.write(chunk)
            content.scroll_end()

    def _prompt_preview(self) -> str:
        if not self.prompt:
            return self.agent_type
        preview = self.prompt.split("\n")[0].strip()
        if len(preview) > 60:
            preview = preview[:57] + "..."
        return f"{self.agent_type}: {preview}"

    def append_chunk(self, text: str) -> None:
        self._chunks.append(text)
        if not self._mounted:
            return
        try:
            content = self.query_one(SubAgentContent)
            if self._stream is None:
                self._stream = Markdown.get_stream(content)
            self._stream.write(text)
            content.scroll_end()
        except Exception:
            pass

    def complete(self) -> None:
        if self._completed:
            return
        self._completed = True
        self.status = "completed"
        if not self._mounted:
            return
        self.set_class(True, "-status-completed")
        self.set_class(False, "-status-running")
        self._update_header()
        try:
            self.query_one(SubAgentContent).display = True
            self.query_one(SubAgentContent).styles.height = "auto"
        except Exception:
            pass

    def action_toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._update_header()
        try:
            self.query_one(SubAgentContent).display = not self._collapsed
        except Exception:
            pass

    def on_click(self, event) -> None:
        """Toggle when the header is clicked (only after completion)."""
        if not self._completed:
            return
        if getattr(event.widget, "id", None) == "subagent-header":
            self.action_toggle()
            event.stop()

    def _update_header(self) -> None:
        try:
            header = self.query_one(SubAgentHeader)
            label = pill(self.agent_type, "$warning-muted", "$text-warning")
            if not self._completed:
                header.update(f"🧠 {self._prompt_preview()} {label}")
            elif self._collapsed:
                header.update(f"+ {self.agent_type} {label}")
            else:
                header.update(f"- {self.agent_type} {label}")
        except Exception:
            pass

    # ── ExpandProtocol ──

    def can_expand(self) -> bool:
        return True

    def expand_block(self) -> None:
        if self._collapsed:
            self.action_toggle()

    def collapse_block(self) -> None:
        if not self._collapsed:
            self.action_toggle()

    def is_block_expanded(self) -> bool:
        return not self._collapsed

    # ── Forward scroll actions to inner Markdown ──

    def action_scroll_up(self) -> None:
        self.query_one(Markdown).scroll_up()

    def action_scroll_down(self) -> None:
        self.query_one(Markdown).scroll_down()

    def action_scroll_left(self) -> None:
        self.query_one(Markdown).scroll_left()

    def action_scroll_right(self) -> None:
        self.query_one(Markdown).scroll_right()

    def action_scroll_home(self) -> None:
        self.query_one(Markdown).scroll_home()

    def action_scroll_end(self) -> None:
        self.query_one(Markdown).scroll_end()

    def action_page_up(self) -> None:
        self.query_one(Markdown).scroll_page_up()

    def action_page_down(self) -> None:
        self.query_one(Markdown).scroll_page_down()

    def action_page_left(self) -> None:
        self.query_one(Markdown).scroll_page_left()

    def action_page_right(self) -> None:
        self.query_one(Markdown).scroll_page_right()
