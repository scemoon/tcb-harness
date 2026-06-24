from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.reactive import var
from textual.widgets import Static


class SubAgentHeader(Static):
    ALLOW_SELECT = False
    DEFAULT_CSS = """
    SubAgentHeader {
        width: auto;
        max-width: 1fr;
    }
    """


class SubAgent(Vertical, can_focus=True):
    """Sub-agent compact view — header (@type [status]) + latest line.

    During streaming: header shows "@type [running]", latest line updates.
    After completion: header shows "@type [completed]"/"[failed]".
    Ctrl+X to open full-screen SubAgentScreen with full structured output.
    """

    HELP = """
## Sub-agent

- **ctrl+x** Open full-screen output
- **up/down** Scroll (if content overflows)
"""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+x", "toggle", "Full screen", show=False, priority=True),
    ]

    ALLOW_MAXIMIZE = True

    DEFAULT_CSS = """
    SubAgent {
        height: auto;
        width: 1fr;
        min-height: 2;
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
        &.-status-failed SubAgentHeader {
            color: $text-error;
        }
    }
    """

    status: var[str] = var("running")
    latest_line: var[str] = var("")

    def __init__(
        self,
        agent_type: str,
        tool_id: str | None = None,
        prompt: str = "",
        *,
        replay: bool = False,
    ) -> None:
        super().__init__(id=tool_id)
        self.agent_type = agent_type
        self.prompt = prompt
        self._chunks: list[str] = []
        self._thinking_chunks: list[str] = []
        self._completed = replay
        self._status = "completed" if replay else "running"
        self._error = ""
        self._mounted = False

    def compose(self) -> ComposeResult:
        self.set_class(True, f"-status-{self._status}")
        yield SubAgentHeader(self._header_text(), id="subagent-header")
        latest_label = self.latest_line or ""
        yield Static(latest_label, id="subagent-latest")

    def on_mount(self) -> None:
        self._mounted = True
        self.styles.height = "auto"
        self.styles.min_height = 2

    def _header_text(self) -> str:
        label = self.agent_type
        status_tag = self._status_label()
        return f"@ {label} [{status_tag}]"

    def _status_label(self) -> str:
        if self._status == "running":
            return "running"
        elif self._status == "failed":
            return f"failed{': ' + self._error[:40] if self._error else ''}"
        return "complete"

    def _update_latest_line(self) -> str:
        full = "".join(self._chunks)
        lines = full.split("\n")
        for line in reversed(lines):
            if line.strip():
                return line.strip()
        return ""

    def append_chunk(self, text: str) -> None:
        self._chunks.append(text)
        self.latest_line = self._update_latest_line()
        if not self._mounted:
            return
        try:
            self.query_one("#subagent-latest", Static).update(self.latest_line)
        except Exception:
            pass

    def append_thinking(self, text: str) -> None:
        self._thinking_chunks.append(text)

    def complete(self, status: str = "completed", error: str = "") -> None:
        if self._completed:
            return
        self._completed = True
        self._status = status
        self._error = error
        if status == "failed":
            self.latest_line = f"Failed: {error[:80]}" if error else "Failed"
        else:
            self.latest_line = self._update_latest_line()
        if not self._mounted:
            return
        self.set_class(True, f"-status-{status}")
        self.set_class(False, "-status-running")
        try:
            header = self.query_one("#subagent-header", SubAgentHeader)
            header.update(self._header_text())
            self.query_one("#subagent-latest", Static).update(self.latest_line)
        except Exception:
            pass

    def action_toggle(self) -> None:
        """Ctrl+X: open full-screen view (works even while running)."""
        from tui.widgets.subagent_screen import SubAgentScreen
        self.app.push_screen(SubAgentScreen(
            agent_type=self.agent_type,
            subagent_id=self.id or "",
            chunks=list(self._chunks),
            thinking_chunks=list(self._thinking_chunks),
            status=self._status,
            error=self._error,
        ))
