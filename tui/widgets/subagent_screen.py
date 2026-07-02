from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalGroup, VerticalScroll
from textual.screen import Screen
from textual.widgets import Header, Markdown, Static
from textual.widgets.markdown import MarkdownStream

_sa_logger = logging.getLogger("tui.widgets.subagent_screen")

from tui.widgets.subagent import SubAgent


class SubAgentScreen(Screen):
    """Full-screen view of a SubAgent output.

    Styled to match main-convention styles:
    - thinking → AgentThought-style (tall border, italic muted, ctrl+x toggle)
    - text    → AgentResponse-style (MarkdownStream incremental rendering)
    - tools   → ToolCall cards (same as main conversation)
    """

    BINDINGS: list[BindingType] = [
        Binding("escape", "app.pop_screen", "Back", priority=True),
        Binding("ctrl+x", "toggle_thought", "Toggle thought", show=False, priority=True),
        Binding("up", "scroll_up", "Up", priority=True),
        Binding("down", "scroll_down", "Down", priority=True),
        Binding("pageup", "scroll_page_up", "Page Up", priority=True),
        Binding("pagedown", "scroll_page_down", "Page Down", priority=True),
        Binding("home", "scroll_home", "Home", priority=True),
        Binding("end", "scroll_end", "End", priority=True),
    ]

    DEFAULT_CSS = """
    SubAgentScreen {
        background: $surface;
    }

    #subagent-scroll {
        padding: 0 1;
        height: 1fr;
        overflow-y: auto;
        scrollbar-gutter: stable;
    }

    #subagent-task {
        margin-bottom: 1;
    }

    #subagent-thought-section {
        display: none;
        margin-bottom: 1;
        border-left: tall $secondary 60%;
        padding: 0 0 0 1;
    }
    #subagent-thought-section.-visible {
        display: block;
    }

    #subagent-thought-header {
        color: $text;
        text-style: bold;
        padding: 0 2;
        height: 1;
        &:hover {
            background: $primary-muted 30%;
        }
    }

    #subagent-thought-content {
        color: $text-muted;
        text-style: italic;
        padding: 0 1 0 2;
        display: none;
    }
    #subagent-thought-content.-visible {
        display: block;
    }

    #subagent-output {
        margin-bottom: 1;
    }

    #subagent-screen-tools {
        padding: 0 1;
        height: auto;
        margin-top: 1;
    }

    #subagent-screen-tools ToolCall {
        margin: 0 0 0 1;
    }

    #subagent-screen-footer {
        dock: bottom;
        height: 1;
        padding: 0 1;
        color: $text-muted;
        background: $boost;
    }
    """

    def __init__(self, subagent: SubAgent) -> None:
        super().__init__()
        self.subagent = subagent
        self._auto_follow = True
        self._refresh_timer = None
        self._thought_collapsed = False
        self._stream: MarkdownStream | None = None
        self._chunks_rendered: int = 0
        self._syncing_tools: bool = False
        self._pending_update: bool = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll(id="subagent-scroll"):
            yield Markdown("", id="subagent-task")
            with Vertical(id="subagent-thought-section"):
                yield Static("⏳ thinking:", id="subagent-thought-header")
                yield Static("", id="subagent-thought-content")
            yield Markdown("", id="subagent-output")
            with VerticalGroup(id="subagent-screen-tools"):
                yield from self._compose_tool_calls()
        yield Static(
            "[$text-muted]esc[/] 返回  "
            "[$text-muted]ctrl+x[/] 折叠思考  "
            "[$text-muted]↑↓[/] 滚动  "
            "[$text-muted]end[/] 跟随最新",
            id="subagent-screen-footer",
        )

    def _compose_tool_calls(self) -> ComposeResult:
        from tui.widgets.tool_call import ToolCall as ToolCallWidget

        sa = self.subagent
        for tool_id in sa._tool_order:
            tc = sa._tool_calls.get(tool_id)
            if isinstance(tc, dict):
                yield ToolCallWidget(tc, id=f"scr-{tool_id}")

    async def on_mount(self) -> None:
        self.title = self._make_title()
        self.sub_title = self._make_subtitle()
        self._render_initial()
        await self._sync_tool_calls_async()
        self.subagent._update_callbacks.append(self._on_subagent_update)
        self._refresh_timer = self.set_interval(0.05, self._poll_subagent)

    def on_unmount(self) -> None:
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
            self._refresh_timer = None
        self._stream = None
        try:
            self.subagent._update_callbacks.remove(self._on_subagent_update)
        except ValueError:
            pass

    # ── Callback: debounced via call_after_refresh ──

    def _on_subagent_update(self) -> None:
        if self._pending_update:
            return
        self._pending_update = True
        self.call_after_refresh(self._flush_pending_update)

    def _flush_pending_update(self) -> None:
        self._pending_update = False
        try:
            sa = self.subagent

            # Stream new text chunks (incremental via MarkdownStream)
            if self._stream and sa._chunks:
                rendered = self._chunks_rendered
                if len(sa._chunks) > rendered:
                    self._chunks_rendered = len(sa._chunks)
                    fragment = "".join(sa._chunks[rendered:])
                    self._stream.write(fragment)

            # Thinking section (Static.update is cheap)
            self._update_thinking()

            # Auto-scroll
            if self._auto_follow:
                scroll = self.query_one("#subagent-scroll", VerticalScroll)
                scroll.scroll_end(animate=False)

            # Footer
            self._update_footer()

            # Tool calls (guarded)
            self._sync_tool_calls()

            # Title
            self.title = self._make_title()
            self.sub_title = self._make_subtitle()
        except Exception:
            _sa_logger.exception("_flush_pending_update failed")

    # ── Initial render ──

    def _render_initial(self) -> None:
        """Render initial state once on mount (not for streaming updates).

        Uses Markdown.update() for immediate synchronous display so that
        historical / already-completed sessions show content right away.
        MarkdownStream is only used for subsequent incremental writes.
        """
        sa = self.subagent
        try:
            # Task
            task = self.query_one("#subagent-task", Markdown)
            if sa.prompt:
                prompt_preview = sa.prompt if len(sa.prompt) <= 200 else sa.prompt[:200] + "..."
                task.update(f"> ### 任务\n\n> {prompt_preview}")
                task.display = True
            else:
                task.display = False

            # Thinking
            self._update_thinking()

            # Output: synchronously show existing content, then create stream
            output = self.query_one("#subagent-output", Markdown)
            if sa._chunks:
                output.update("".join(sa._chunks))
            self._chunks_rendered = len(sa._chunks)
            self._stream = Markdown.get_stream(output)

            # Footer
            self._update_footer()
        except Exception:
            _sa_logger.exception("_render_initial failed")

    # ── Polling safety net + completion handler ──

    def _poll_subagent(self) -> None:
        sa = self.subagent
        if sa._status == "running":
            # Catch missed updates (e.g. callback lost during screen transition)
            if self._stream and len(sa._chunks) > self._chunks_rendered:
                self.call_after_refresh(self._flush_pending_update)
            return

        # Not running — finalise and stop polling
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
            self._refresh_timer = None

        # Write any remaining chunks
        if self._stream and len(sa._chunks) > self._chunks_rendered:
            rendered = self._chunks_rendered
            self._chunks_rendered = len(sa._chunks)
            self._stream.write("".join(sa._chunks[rendered:]))

        # Append failure / completion signal to stream
        if sa._status == "failed":
            raw = "".join(sa._chunks)
            self._stream.write(
                f"\n\n---\n**❌ Failed:** {sa._error}\n\n"
                f"**Partial output:**\n```\n{raw[:4000] if raw else '(none)'}\n```"
            )

        self.call_after_refresh(self._final_refresh)

    def _final_refresh(self) -> None:
        """One last UI refresh after subagent completes."""
        try:
            self._update_thinking()
            self._update_footer()
            self.title = self._make_title()
            self.sub_title = self._make_subtitle()
            self._sync_tool_calls()
        except Exception:
            _sa_logger.exception("_final_refresh failed")

    # ── Shared UI helpers ──

    def _update_thinking(self) -> None:
        try:
            sa = self.subagent
            thought_section = self.query_one("#subagent-thought-section", Vertical)
            thought_content = self.query_one("#subagent-thought-content", Static)
            if sa._thinking_chunks:
                thought_section.display = True
                thought_section.set_class(True, "-visible")
                raw = "".join(sa._thinking_chunks).strip()
                thought_content.update(raw)
                # Auto-expand during streaming
                if sa._status == "running":
                    self._thought_collapsed = False
                thought_content.set_class(not self._thought_collapsed, "-visible")
                thought_content.display = not self._thought_collapsed
            else:
                thought_section.display = False
                thought_section.set_class(False, "-visible")
            self._update_thought_header()
        except Exception:
            _sa_logger.warning("_update_thinking failed", exc_info=True)

    def _update_footer(self) -> None:
        try:
            thought_label = "折叠思考" if not self._thought_collapsed else "展开思考"
            self.query_one("#subagent-screen-footer", Static).update(
                "[$text-muted]esc[/] 返回  "
                f"[$text-muted]ctrl+x[/] {thought_label}  "
                "[$text-muted]↑↓[/] 滚动  "
                "[$text-muted]end[/] 跟随最新"
            )
        except Exception:
            pass

    def _update_thought_header(self) -> None:
        try:
            header = self.query_one("#subagent-thought-header", Static)
            if sa := self.subagent:
                if sa._status == "running":
                    header.update("⏳ thinking:")
                elif self._thought_collapsed:
                    header.update("+ Thought")
                else:
                    header.update("- Thought")
        except Exception:
            pass

    # ── Thought toggle ──

    def action_toggle_thought(self) -> None:
        self._thought_collapsed = not self._thought_collapsed
        self._update_thinking()
        self._update_footer()

    def on_click(self, event) -> None:
        if getattr(event.widget, "id", None) == "subagent-thought-header":
            self.action_toggle_thought()
            event.stop()

    # ── Tool call sync (guarded) ──

    def _sync_tool_calls(self) -> None:
        self.run_worker(self._sync_tool_calls_async(), exit_on_error=False)

    async def _sync_tool_calls_async(self) -> None:
        if self._syncing_tools:
            return
        self._syncing_tools = True
        try:
            container = self.query_one("#subagent-screen-tools", VerticalGroup)
        except Exception:
            self._syncing_tools = False
            return
        from tui.widgets.tool_call import ToolCall as ToolCallWidget

        existing: dict[str, ToolCallWidget] = {
            w.id: w for w in container.children if isinstance(w, ToolCallWidget)
        }
        sa = self.subagent
        for tool_id in sa._tool_order:
            tc = sa._tool_calls.get(tool_id)
            if not isinstance(tc, dict):
                continue
            scr_id = f"scr-{tool_id}"
            widget = existing.get(scr_id)
            try:
                if widget is None:
                    await container.mount(ToolCallWidget(tc, id=scr_id))
                else:
                    await widget.update_tool_call(tc)
            except Exception:
                _sa_logger.exception("mount/update tool call failed %s", tool_id)
        self._syncing_tools = False

    # ── Scroll actions ──

    def _scroll_widget(self) -> VerticalScroll | None:
        return self.query_one("#subagent-scroll", VerticalScroll)

    def action_scroll_up(self) -> None:
        self._auto_follow = False
        if w := self._scroll_widget():
            w.scroll_up()

    def action_scroll_down(self) -> None:
        if w := self._scroll_widget():
            w.scroll_down()

    def action_scroll_page_up(self) -> None:
        self._auto_follow = False
        if w := self._scroll_widget():
            w.scroll_page_up()

    def action_scroll_page_down(self) -> None:
        if w := self._scroll_widget():
            w.scroll_page_down()

    def action_scroll_home(self) -> None:
        self._auto_follow = False
        if w := self._scroll_widget():
            w.scroll_home()

    def action_scroll_end(self) -> None:
        self._auto_follow = True
        if w := self._scroll_widget():
            w.scroll_end(animate=False)

    # ── Title ──

    def _make_title(self) -> str:
        sa = self.subagent
        status_icon = {
            "running": "🔄",
            "completed": "✔",
            "failed": "✗",
        }.get(sa._status, "?")
        return f"{status_icon} Subagent ({sa.agent_type})"

    def _make_subtitle(self) -> str:
        sa = self.subagent
        chunks = len("".join(sa._chunks))
        tools = len(sa._tool_calls)
        parts = [sa._status]
        if chunks:
            parts.append(f"{chunks}B")
        if tools:
            parts.append(f"{tools} tool calls")
        return " | ".join(parts)
