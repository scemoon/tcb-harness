from __future__ import annotations

from typing import ClassVar

from textual import containers
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.content import Content
from textual.reactive import var
from textual.widgets import Static

from tui.protocol import ExpandProtocol


class SubAgentHeader(Static):
    ALLOW_SELECT = False
    DEFAULT_CSS = """
    SubAgentHeader {
        width: auto;
        max-width: 1fr;
    }
    """


class SubAgent(containers.VerticalGroup, can_focus=True):
    """Sub-agent compact view — animated header + latest line with ctrl+x hint.

    During streaming: header shows a spinner + latest line updates live.
    After completion: header shows static marker.
    Ctrl+X to open full-screen SubAgentScreen with full structured output.
    """

    DEFAULT_CLASSES = "block"

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
        padding: 0 1;
        border-left: thick $secondary;
        background: $surface-darken-1;

        SubAgentHeader {
            color: $text-secondary;
            text-style: bold;
        }

        &.-status-running {
            border-left: thick $warning;
            background: $boost;
            SubAgentHeader {
                color: $warning;
                text-style: bold italic;
            }
            #subagent-latest {
                color: $text;
            }
        }

        &.-status-completed {
            border-left: thick $success;
            SubAgentHeader {
                color: $success;
            }
            #subagent-latest {
                color: $text-muted;
            }
        }

        &.-status-failed {
            border-left: thick $error;
            SubAgentHeader {
                color: $error;
            }
            #subagent-latest {
                color: $error;
            }
        }
    }
    """

    status: var[str] = var("running")
    latest_line: var[str] = var("")
    spinner_frame: var[int] = var(0)

    SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(
        self,
        agent_type: str,
        tool_id: str | None = None,
        prompt: str = "",
    ) -> None:
        super().__init__(id=tool_id)
        self.agent_type = agent_type
        self.prompt = prompt
        self._chunks: list[str] = []
        self._thinking_chunks: list[str] = []
        self._completed = False
        self._status = "running"
        self._error = ""
        self._mounted = False
        self._spin_timer = None

    def compose(self) -> ComposeResult:
        self.set_class(True, f"-status-{self._status}")
        yield SubAgentHeader(self._header_text(), id="subagent-header")
        yield Static(self._latest_content, id="subagent-latest")

    def on_mount(self) -> None:
        self._mounted = True
        self.styles.height = "auto"
        self.styles.min_height = 2
        self._start_spinner()
        self._refresh()

    def _start_spinner(self) -> None:
        if self._spin_timer is not None:
            return
        self._spin_timer = self.set_interval(0.1, self._tick_spinner)

    def _stop_spinner(self) -> None:
        if self._spin_timer is not None:
            self._spin_timer.stop()
            self._spin_timer = None

    def _tick_spinner(self) -> None:
        if self._status == "running":
            self.spinner_frame = (self.spinner_frame + 1) % len(self.SPINNER_FRAMES)
            self._refresh_header()

    def watch_status(self, _old: str, _new: str) -> None:
        if _new != "running":
            self._stop_spinner()

    def _refresh(self) -> None:
        if not self._mounted:
            return
        try:
            self.set_class(True, f"-status-{self._status}")
            if self._status != "running":
                self.set_class(False, "-status-running")
            self.query_one("#subagent-header", SubAgentHeader).update(self._header_text())
            self.query_one("#subagent-latest", Static).update(self._latest_content)
        except Exception:
            pass

    def _refresh_header(self) -> None:
        if not self._mounted:
            return
        try:
            self.query_one("#subagent-header", SubAgentHeader).update(self._header_text())
        except Exception:
            pass

    def _header_text(self) -> str:
        label = self.agent_type
        status_tag = self._status_label()
        if self._status == "running":
            spin = self.SPINNER_FRAMES[self.spinner_frame]
            return f"{spin} @ {label} [{status_tag}]"
        elif self._status == "completed":
            return f"✓ @ {label} [{status_tag}]"
        elif self._status == "failed":
            return f"✗ @ {label} [{status_tag}]"
        return f"@ {label} [{status_tag}]"

    @property
    def _latest_content(self) -> Content:
        text = (self.latest_line or "").strip()
        hint = Content.from_markup("  [$text-muted]ctrl+x 展开查看")
        if text:
            return Content.assemble(text, hint)
        return Content.from_markup("[$text-muted]⏳ 等待输出…  ctrl+x 展开查看")

    def _status_label(self) -> str:
        if self._status == "running":
            return "running"
        elif self._status == "failed":
            return f"failed{': ' + self._error[:40] if self._error else ''}"
        return "completed"

    def _update_latest_line(self) -> str:
        MAX_LEN = 50
        full = "".join(self._chunks)
        lines = full.split("\n")
        for line in reversed(lines):
            line = line.strip()
            if line:
                if len(line) > MAX_LEN:
                    return line[:MAX_LEN] + "..."
                return line
        return ""

    def append_chunk(self, text: str) -> None:
        self._chunks.append(text)
        self.latest_line = self._update_latest_line()
        self._refresh_latest()

    def append_thinking(self, text: str) -> None:
        self._thinking_chunks.append(text)

    def complete(self, status: str = "completed", error: str = "") -> None:
        if self._completed:
            return
        self._completed = True
        self._status = status
        self._error = error
        if status == "failed":
            self.latest_line = f"Failed: {error[:60]}" if error else "Failed"
        else:
            self.latest_line = self._update_latest_line()
        self._stop_spinner()
        self._refresh()

    def _refresh_latest(self) -> None:
        if not self._mounted:
            return
        try:
            self.query_one("#subagent-latest", Static).update(self._latest_content)
        except Exception:
            pass

    def can_expand(self) -> bool:
        return True

    def expand_block(self) -> None:
        self.action_toggle()

    def collapse_block(self) -> None:
        pass

    def is_block_expanded(self) -> bool:
        return False

    def action_toggle(self) -> None:
        """Ctrl+X: open full-screen view (works even while running)."""
        from tui.widgets.subagent_screen import SubAgentScreen
        self.app.push_screen(SubAgentScreen(self))