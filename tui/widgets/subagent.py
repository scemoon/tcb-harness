from __future__ import annotations

import logging

from textual import containers
from textual.app import ComposeResult
from textual.content import Content
from textual.css.query import NoMatches
from textual.reactive import var
from textual.widgets import Markdown, Static

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
    """Sub-agent view — clickable header with expandable inline body.

    Styles aligned with main-agent ToolCall / AgentThought conventions.

    - **Collapsed**: header (arrow + icon + label + status) + preview line.
    - **Expanded**  : header + body (thinking, text output, tool calls).

    Ctrl+N opens the full-screen SubAgentScreen.
    """

    DEFAULT_CLASSES = "block"

    HELP = """
## Sub-agent

- **click header** Expand/collapse inline view
- **ctrl+n** Open full-screen output
- **up/down** Scroll (if content overflows)
"""

    ALLOW_MAXIMIZE = True

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
            &:hover {
                background: $primary-muted 30%;
            }
        }

        #subagent-latest {
            padding: 0 0 0 2;
        }

        #subagent-body {
            display: none;
            padding: 0 0 0 1;
        }

        &.-expanded {
            #subagent-latest { display: none; }
            #subagent-body  { display: block; }
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

        #subagent-thought-content {
            color: $text-muted;
            text-style: italic;
            padding: 0 1 0 2;
            display: none;
            margin-bottom: 1;
        }
        #subagent-thought-content.-visible {
            display: block;
        }

        #subagent-text-content {
            margin: 0 0 1 0;
        }

        #subagent-tools {
            height: auto;
            layout: vertical;
        }

        #subagent-footer-hint {
            color: $text-muted;
            height: 1;
            padding: 0 1;
            margin-top: 1;
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
        self._expanded = False
        self._spin_timer = None
        self._update_callbacks: list = []
        # Tool calls invoked *inside* this subagent, rendered as real ToolCall
        # cards (same style as the main conversation).
        self._tool_calls: dict = {}
        self._tool_order: list[str] = []
        # Tool calls stashed during replay flush (mounted once the SubAgent
        # itself is mounted). See Conversation._flush_replay_buffer.
        self._pending_tool_calls: list = []
        # Ordered event queue for chronological rendering (used by SubAgentScreen)
        self._events: list = []
        # Direct streaming hook for SubAgentScreen (bypasses _notify_update for chunks)
        self._screen_hook = None
        # Diagnostics counters (for log correlation)
        self._chunk_count_log: int = 0
        self._byte_count_log: int = 0

    def compose(self) -> ComposeResult:
        self.set_class(True, f"-status-{self._status}")
        self.set_class(self._expanded, "-expanded")
        yield SubAgentHeader(self._header_text(), id="subagent-header", markup=False)
        yield Static(self._latest_content, id="subagent-latest")
        with containers.Vertical(id="subagent-body"):
            yield Static("", id="subagent-thought-content")
            yield Markdown("", id="subagent-text-content")
            yield containers.Vertical(id="subagent-tools")
            yield Static("[$text-muted]ctrl+n 全屏查看", id="subagent-footer-hint")

    def on_mount(self) -> None:
        self._mounted = True
        self.styles.height = "auto"
        self.styles.min_height = 2
        self._start_spinner()
        # Flush any tool calls that were pending before mount (replay path).
        if self._pending_tool_calls:
            pending = list(self._pending_tool_calls)
            self._pending_tool_calls.clear()
            for tool_id, tc in pending:
                self.run_worker(self._mount_tool_call_widget(tool_id, tc))
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
        hint = "  [$text-muted] ctrl+n 全屏"
        if text:
            return Content.assemble(Content(text), Content.from_markup(hint))
        return Content.from_markup(f"[$text-muted]⏳ 等待输出…{hint}")

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

    # ── Expand / collapse ──

    def _toggle_expand(self) -> None:
        self._expanded = not self._expanded
        self.set_class(self._expanded, "-expanded")
        self._refresh_header()
        if self._expanded:
            self._refresh_full_body()
        self._refresh_latest()

    def on_click(self, event) -> None:
        """Click header to toggle expand/collapse."""
        if getattr(event.widget, "id", None) == "subagent-header":
            self._toggle_expand()
            event.stop()

    # ── Inline body content ──

    def _refresh_full_body(self) -> None:
        """Rebuild the full inline body — thinking, text, tools."""
        if not self._mounted or not self._expanded:
            return
        try:
            # Thinking
            thought = self.query_one("#subagent-thought-content", Static)
            if self._thinking_chunks:
                thought.display = True
                raw = "".join(self._thinking_chunks).strip()
                thought.update(raw)
            else:
                thought.display = False

            # Text output (markdown)
            text_widget = self.query_one("#subagent-text-content", Markdown)
            full_text = "".join(self._chunks)
            text_widget.update(full_text)

            # Tool calls — mount any that aren't yet in the DOM
            for tool_id in self._tool_order:
                tc = self._tool_calls.get(tool_id)
                if tc is not None:
                    self.run_worker(self._mount_tool_call_widget(tool_id, tc))
        except Exception:
            _sa_logger.exception("_refresh_full_body failed")

    # ── Streaming updates ──

    def append_chunk(self, text: str) -> None:
        self._chunks.append(text)
        self._events.append(("text", text))
        self._chunk_count_log += 1
        self._byte_count_log += len(text or "")
        self.latest_line = self._update_latest_line()
        self._refresh_latest()
        if self._expanded:
            self.call_after_refresh(self._refresh_full_body)
        hook = self._screen_hook
        if hook:
            self.run_worker(hook(text), exit_on_error=False)
        else:
            self._notify_update()

    def append_thinking(self, text: str) -> None:
        self._thinking_chunks.append(text)
        self._events.append(("thinking", text))
        if self._expanded:
            self.call_after_refresh(self._refresh_full_body)
        self._notify_update()

    async def _mount_tool_call_widget(self, tool_id: str, tool_call) -> None:
        """Mount or update a ToolCall card inside the body."""
        from tui.widgets.tool_call import ToolCall as ToolCallWidget

        try:
            tools = self.query_one("#subagent-tools", containers.Vertical)
        except Exception:
            return  # body not composed yet
        tools.display = True
        try:
            existing = tools.get_child_by_id(tool_id)
        except NoMatches:
            existing = None
        try:
            if existing is not None:
                await existing.update_tool_call(tool_call)
            else:
                await tools.mount(ToolCallWidget(tool_call, id=tool_id))
        except Exception:
            _sa_logger.exception("mount/update tool call failed %s", tool_id)

    async def add_or_update_tool_call(self, tool_id: str, tool_call) -> None:
        """Track a tool call so the full-screen SubAgentScreen can display it,
        and mount it as a real ToolCall card inline when expanded."""
        self._tool_calls[tool_id] = tool_call
        if tool_id not in self._tool_order:
            self._tool_order.append(tool_id)
        self._events.append(("tool", (tool_id, tool_call)))
        # Show the current tool name as the inline preview line.
        title = tool_call.get("title", "") if isinstance(tool_call, dict) else ""
        if title:
            self.latest_line = title
            self._refresh_latest()
        if self._mounted:
            await self._mount_tool_call_widget(tool_id, tool_call)
        self._notify_update()

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
        if self._expanded:
            self.call_after_refresh(self._refresh_full_body)
        self._notify_update()

    def _notify_update(self) -> None:
        for cb in self._update_callbacks:
            try:
                cb()
            except Exception:
                _sa_logger.warning("subagent update callback failed", exc_info=True)

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
