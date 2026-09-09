from textual.app import ComposeResult
from textual.binding import Binding
from textual.content import Content
from textual.screen import ModalScreen
from textual import containers
from textual.widgets import Static

from tui.acp import protocol
from tui.widgets.tool_call import compose_tool_content


class ToolContentScreen(ModalScreen[None]):
    """Full-screen view of tool call content."""

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close", show=False),
        Binding("q", "dismiss(None)", "Close", show=False),
    ]

    def __init__(self, tool_call: protocol.ToolCall) -> None:
        self._tool_call = tool_call
        super().__init__()

    def compose(self) -> ComposeResult:
        tool_call = self._tool_call
        title = tool_call.get("title", "Tool Content")
        status = tool_call.get("status", "")
        header_text = f"🔧 {title}"
        if status == "failed":
            header_text += " ✘"
        elif status == "completed":
            header_text += " ✔"
        yield Static(Content(header_text), id="tool-content-header")
        with containers.VerticalScroll(id="full-tool-content"):
            content = tool_call.get("content", []) or []
            yield from compose_tool_content(content, self.app)

    DEFAULT_CSS = """
    ToolContentScreen {
        align: center middle;
        background: $surface 95%;
    }
    #tool-content-header {
        dock: top;
        width: 100%;
        padding: 1;
        background: $panel;
        text-style: bold;
        color: $text-primary;
        height: 3;
    }
    #full-tool-content {
        width: 100%;
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
        scrollbar-gutter: stable;
    }
    """
