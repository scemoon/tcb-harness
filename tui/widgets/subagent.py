from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from textual import containers
from textual.app import ComposeResult
from textual.content import Content
from textual.reactive import var
from textual.widgets import Static

_sa_logger = logging.getLogger("tui.widgets.subagent")


class SubAgentHeader(Static):
    ALLOW_SELECT = False
    DEFAULT_CSS = """
    SubAgentHeader {
        width: auto;
        max-width: 1fr;
    }
    """


class SubAgent(containers.VerticalGroup, can_focus=True):
    """Sub-agent view — header + dynamically updated latest line.

    Ctrl+N opens the full-screen SubAgentScreen.
    """

    DEFAULT_CLASSES = "block"

    HELP = """
## Sub-agent

- **ctrl+n** Open full-screen output
"""

    DEFAULT_CSS = """
    SubAgent {
        height: auto;
        width: 1fr;
        min-height: 2;
        border-left: tall $secondary;

        SubAgentHeader {
            color: $text-secondary;
            text-style: bold;
            padding: 0 1;
        }

        #subagent-latest {
            padding: 0 0 0 2;
        }

        &.-status-running {
            border-left: tall $warning;
            SubAgentHeader {
                color: $warning;
                text-style: bold italic;
            }
        }

        &.-status-completed {
            border-left: tall $success;
            SubAgentHeader {
                color: $success;
            }
        }

        &.-status-failed {
            border-left: tall $error;
            SubAgentHeader {
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
        # Single handler set by SubAgentScreen for real-time event delivery
        self._screen_handler: Callable[[str, Any], Coroutine[Any, Any, None]] | None = None
        # Tool calls invoked *inside* this subagent (tracked for SubAgentScreen)
        self._tool_calls: dict = {}
        self._tool_order: list[str] = []
        # Ordered event queue for chronological rendering (used by SubAgentScreen)
        self._events: list = []
        # Diagnostics counters (for log correlation)
        self._chunk_count_log: int = 0
        self._byte_count_log: int = 0

    def compose(self) -> ComposeResult:
        self.set_class(True, f"-status-{self._status}")
        yield SubAgentHeader(self._header_text(), id="subagent-header", markup=False)
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

    # ── Refresh helpers ──

    def _refresh(self) -> None:
        if not self._mounted:
            return
        try:
            self.set_class(True, f"-status-{self._status}")
            if self._status != "running":
                self.set_class(False, "-status-running")
            self.query_one("#subagent-header", SubAgentHeader).update(self._header_text())
        except Exception:
            pass

    def _refresh_header(self) -> None:
        if not self._mounted:
            return
        try:
            self.query_one("#subagent-header", SubAgentHeader).update(self._header_text())
        except Exception:
            pass

    # ── Header content (aligned with ToolCall style) ──

    def _header_text(self) -> Content:
        parts = [
            Content.from_markup(f"🧠 Subagent ({self.agent_type})"),
        ]
        if self._status == "running":
            spin = self.SPINNER_FRAMES[self.spinner_frame]
            parts.append(Content.from_markup(f" [$text-warning]{spin}"))
        elif self._status == "completed":
            parts.append(Content.from_markup(" [$success]✔"))
        elif self._status == "failed":
            from tui.pill import pill
            tag = f": {self._error[:40]}" if self._error else ""
            parts.append(Content.assemble(" ", pill(f"failed{tag}", "$error-muted", "$error")))
        return Content.assemble(*parts)

    # ── Preview line (shown when collapsed) ──

    @property
    def _latest_content(self) -> Content:
        text = (self.latest_line or "").strip()
        if text:
            return Content(text)
        return Content.from_markup("[$text-muted]⏳ 等待输出…")

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

    # ── Streaming updates ──

    def append_chunk(self, text: str) -> None:
        self._chunks.append(text)
        self._events.append(("text", text))
        self._chunk_count_log += 1
        self._byte_count_log += len(text or "")
        self.latest_line = self._update_latest_line()
        self._refresh_latest()
        if self._screen_handler is not None:
            self.run_worker(self._screen_handler("text", text), exit_on_error=False)

    def append_thinking(self, text: str) -> None:
        self._thinking_chunks.append(text)
        self._events.append(("thinking", text))
        if self._screen_handler is not None:
            self.run_worker(self._screen_handler("thinking", text), exit_on_error=False)

    async def add_or_update_tool_call(self, tool_id: str, tool_call) -> None:
        """Track a tool call so the full-screen SubAgentScreen can display it."""
        self._tool_calls[tool_id] = tool_call
        if tool_id not in self._tool_order:
            self._tool_order.append(tool_id)
        self._events.append(("tool", (tool_id, tool_call)))
        # Show the current tool name as the inline preview line.
        title = tool_call.get("title", "") if isinstance(tool_call, dict) else ""
        if title:
            self.latest_line = title
            self._refresh_latest()
        if self._screen_handler is not None:
            self.run_worker(self._screen_handler("tool", (tool_id, tool_call)), exit_on_error=False)

    def complete(self, status: str = "completed", error: str = "") -> None:
        _sa_logger.debug(
            "[WIDGET-SUBagent] complete id=%s status=%s err=%r chunks=%d bytes=%d "
            "was_completed=%s",
            self.id, status, (error or "")[:80], self._chunk_count_log,
            self._byte_count_log, self._completed,
        )
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
        if self._screen_handler is not None:
            self.run_worker(self._screen_handler("complete", {"status": status, "error": error}), exit_on_error=False)

    def _refresh_latest(self) -> None:
        if not self._mounted:
            return
        try:
            self.query_one("#subagent-latest", Static).update(self._latest_content)
        except Exception:
            pass

    def action_fullscreen(self) -> None:
        """Ctrl+N: open full-screen view (works even while running)."""
        from tui.widgets.subagent_screen import SubAgentScreen
        self.app.push_screen(SubAgentScreen(self))
