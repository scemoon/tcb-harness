from __future__ import annotations

import asyncio
import logging
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Grid, VerticalGroup, VerticalScroll
from textual.css.query import NoMatches
from textual.geometry import Offset, Region, Spacing
from textual.layouts.vertical import WidgetPlacement
from textual.reactive import reactive
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Header, Static

from tui.menus import MenuItem
from tui.protocol import ExpandProtocol, MenuProtocol
from tui.widgets.agent_response import AgentResponse
from tui.widgets.agent_thought import AgentThought
from tui.widgets.conversation import Cursor, CursorContainer
from tui.widgets.menu import Menu
from tui.widgets.subagent import SubAgent
from tui.widgets.tool_call import ToolCall as ToolCallWidget

_sa_logger = logging.getLogger("tui.widgets.subagent_screen")


_SELECTABLE_BLOCK_TYPES: tuple[type[Widget], ...] = (
    AgentResponse,
    AgentThought,
    ToolCallWidget,
)


def _is_selectable(child: Widget) -> bool:
    return isinstance(child, _SELECTABLE_BLOCK_TYPES)


class SubAgentScreen(Screen):
    """Full-screen view of a SubAgent output.

    Renders identically to the main Conversation:
    - AgentResponse for streaming text (MarkdownStream)
    - ToolCall cards mounted inline between text blocks
    - AgentThought (thinking) as inline siblings at position of occurrence
    - All widgets as siblings in a single #content container
    - Vertical-bar block cursor in a left-side CursorContainer, matching
      Conversation's visual treatment.

    Mirrors Conversation's block cursor: Ctrl+J/K move between blocks,
    Enter opens a Menu (copy / maximize), Ctrl+X toggles expand/collapse
    on ExpandProtocol blocks.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "app.pop_screen", "Back", priority=True),
        Binding("ctrl+j", "cursor_down", "Next block", show=False, priority=True),
        Binding("ctrl+k", "cursor_up", "Prev block", show=False, priority=True),
        Binding("enter", "select_block", "Block menu", show=False, priority=True),
        Binding("ctrl+x", "toggle_expand", "Toggle expand", show=False, priority=True),
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
        padding-left: 1;
    }

    #scroll {
        height: 1fr;
        overflow-y: auto;
        scrollbar-gutter: stable;
    }

    #content-grid {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 1 1fr;
        grid-gutter: 0;
        height: auto;
        width: 1fr;
    }

    #cursor-container {
        width: 1;
        height: auto;
        color: $foreground 7%;

        &> Cursor {
            height: 0;
            width: 1;
            border-left: outer $text-accent;
            visibility: visible;
            &.-blink {
                border-left: outer $text-accent 20%;
            }
        }
    }

    #content {
        layout: stream;
        width: 1fr;
        overflow: hidden;
        height: auto;
        padding: 0 0 0 0;
    }

    #content > AgentResponse {
        min-height: 1;
        padding: 0 0 0 0;
        overflow-x: auto;
        scrollbar-size-horizontal: 0;
        layout: stream;
    }

    #content > ToolCall {
        margin: 0 0 0 1 !important;
        width: 1fr;
        layout: stream;
        height: auto;
    }

    #content > AgentThought {
        margin: 1 1 1 0;
    }

    #content > ToolCall ToolCallHeader {
        color: $text-secondary;
        pointer: pointer;
        width: auto;
        max-width: 1fr;
        margin: 0 1 0 0;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }

    #content > ToolCall #tool-content {
        display: none;
    }

    #content > ToolCall.-has-content #tool-content {
        margin: 1 1 1 0;
    }

    #content > ToolCall.-expanded #tool-content {
        display: block;
        max-height: 60vh;
        overflow-y: hidden;
    }

    #content > ToolCall.-expanded ToolCallHeader {
        text-wrap: wrap;
        text-overflow: fold;
    }

    #content > AgentResponse > MarkdownBlock:last-child,
    #content > AgentThought > #thought-content MarkdownBlock:last-child {
        margin-bottom: 0;
    }

    #footer {
        dock: bottom;
        height: 1;
        padding: 0 1;
        color: $text-muted;
        background: $boost;
    }
    """

    class Content(VerticalGroup, can_focus=False):
        """Matches Conversation.Contents — strips bottom margin from last child."""

        def process_layout(
            self, placements: list[WidgetPlacement]
        ) -> list[WidgetPlacement]:
            if placements:
                last = placements[-1]
                top, right, _bottom, left = last.margin
                placements[-1] = last._replace(
                    margin=Spacing(top, right, 0, left)
                )
            return placements

    cursor_offset: reactive[int] = reactive(-1)

    def __init__(self, subagent: SubAgent) -> None:
        super().__init__()
        self.subagent = subagent
        self._events_idx: int = 0
        self._sync_pending = False
        self._post_lock = asyncio.Lock()
        self._current_response: AgentResponse | None = None
        self._current_thought: AgentThought | None = None
        self._auto_follow = True

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll(id="scroll"):
            with Grid(id="content-grid"):
                with CursorContainer(id="cursor-container"):
                    yield Cursor()
                with VerticalGroup(id="content-wrap"):
                    yield self.Content(id="content")
        yield Static(
            "[$text-muted]esc[/] 返回  "
            "[$text-muted]ctrl+j/k[/] 移动  "
            "[$text-muted]enter[/] 菜单  "
            "[$text-muted]ctrl+x[/] 折叠  "
            "[$text-muted]↑↓[/] 滚动",
            id="footer",
        )

    # ── Lifecycle ──

    async def on_mount(self) -> None:
        self.subagent._update_callbacks.append(self._on_subagent_update)
        await self._sync_ui()
        try:
            self.query_one("#scroll", VerticalScroll).focus()
        except Exception:
            pass

    def on_unmount(self) -> None:
        self._current_response = None
        self._current_thought = None
        try:
            self.subagent._update_callbacks.remove(self._on_subagent_update)
        except ValueError:
            pass

    # ── Event processing ──

    def _on_subagent_update(self) -> None:
        if self._sync_pending:
            return
        self._sync_pending = True
        self.run_worker(self._sync_ui(), exit_on_error=False)

    async def _sync_ui(self) -> None:
        try:
            async with self._post_lock:
                container = self.query_one("#content", VerticalGroup)
                while self._events_idx < len(self.subagent._events):
                    entry = self.subagent._events[self._events_idx]
                    self._events_idx += 1
                    if entry[0] == "thinking":
                        await self._handle_thinking(container, entry[1])
                    elif entry[0] == "text":
                        self._complete_current_thought()
                        await self._handle_text(container, entry[1])
                    elif entry[0] == "tool":
                        self._complete_current_thought()
                        await self._handle_tool(container, entry[1])

            # If subagent is done, complete any lingering active thought
            if self._current_thought is not None and not self._current_thought._completed:
                if self.subagent._status in ("completed", "failed"):
                    self._current_thought.mark_completed()
                    self._current_thought = None

            self._update_title()
            self._update_footer()
            self._refresh_block_cursor()
            if self._auto_follow:
                self.call_after_refresh(self._scroll_to_end)
        except Exception:
            _sa_logger.exception("_sync_ui failed")
        finally:
            self._sync_pending = False
            if self._events_idx < len(self.subagent._events):
                self._on_subagent_update()

    async def _handle_thinking(self, container: VerticalGroup, fragment: str) -> None:
        if self._current_thought is None:
            self._current_thought = AgentThought(fragment)
            await container.mount(self._current_thought)
        else:
            await self._current_thought.append_fragment(fragment)

    async def _handle_text(self, container: VerticalGroup, fragment: str) -> None:
        if self._current_response is None:
            self._current_response = AgentResponse("")
            await container.mount(self._current_response)
        await self._current_response.append_fragment(fragment)

    async def _handle_tool(self, container: VerticalGroup, data) -> None:
        tool_id, tc = data
        self._current_response = None

        scr_id = f"scr-{tool_id}"
        try:
            existing: ToolCallWidget = container.get_child_by_id(scr_id)  # type: ignore[assignment]
            await existing.update_tool_call(tc)
        except NoMatches:
            await container.mount(ToolCallWidget(tc, id=scr_id))
        except Exception:
            _sa_logger.exception("_handle_tool failed %s", tool_id)

    def _complete_current_thought(self) -> None:
        if self._current_thought is not None and not self._current_thought._completed:
            self._current_thought.mark_completed()
            self._current_thought = None

    def _scroll_to_end(self) -> None:
        try:
            self.query_one("#scroll", VerticalScroll).scroll_end(animate=False)
        except Exception:
            pass

    # ── Block cursor ──

    def _selectable_children(self) -> list[Widget]:
        try:
            container = self.query_one("#content", VerticalGroup)
        except Exception:
            return []
        return [child for child in container.children if _is_selectable(child)]

    @property
    def cursor_block(self) -> Widget | None:
        if self.cursor_offset == -1:
            return None
        children = self._selectable_children()
        if not children or self.cursor_offset >= len(children):
            return None
        return children[self.cursor_offset]

    def _cursor_widget(self) -> Cursor | None:
        try:
            return self.query_one("#cursor-container Cursor", Cursor)
        except Exception:
            return None

    def _content_region(self) -> Region | None:
        try:
            return self.query_one("#content", VerticalGroup).content_region
        except Exception:
            return None

    def _refresh_block_cursor(self) -> None:
        cursor = self._cursor_widget()
        if cursor is None:
            return
        block = self.cursor_block
        if block is None:
            cursor.follow(None)
            return
        cursor.follow(block)
        scroll = self._scroll_widget()
        if scroll is not None:
            self.call_after_refresh(
                scroll.scroll_to_center, block, immediate=True
            )

    def action_cursor_down(self) -> None:
        children = self._selectable_children()
        if not children:
            return
        if self.cursor_offset == -1:
            self.cursor_offset = 0
        elif self.cursor_offset < len(children) - 1:
            self.cursor_offset += 1
        else:
            self.cursor_offset = -1
        self._auto_follow = False
        self._refresh_block_cursor()

    def action_cursor_up(self) -> None:
        children = self._selectable_children()
        if not children:
            return
        if self.cursor_offset == -1:
            self.cursor_offset = len(children) - 1
        elif self.cursor_offset > 0:
            self.cursor_offset -= 1
        else:
            self.cursor_offset = -1
        self._auto_follow = False
        self._refresh_block_cursor()

    async def action_select_block(self) -> None:
        block = self.cursor_block
        if block is None:
            return
        menu_options: list[MenuItem] = [
            MenuItem("[u]C[/]opy to clipboard", "copy_to_clipboard", "c"),
            MenuItem("Co[u]p[/u]y to prompt", "copy_to_prompt", "p"),
        ]
        if getattr(block, "ALLOW_MAXIMIZE", False):
            menu_options.append(MenuItem("[u]M[/u]aximize", "maximize_block", "m"))
        if isinstance(block, MenuProtocol):
            menu_options.extend(block.get_block_menu())
        if isinstance(block, ExpandProtocol):
            if block.is_block_expanded():
                menu_options.append(MenuItem("[u]C[/]ollapse", "collapse_block", "x"))
            else:
                menu_options.append(MenuItem("E[x]pand", "expand_block", "x"))
        menu = Menu(block, menu_options)
        try:
            container = self.query_one("#content", VerticalGroup)
            region = container.content_region
            menu.styles.offset = Offset(
                region.x + 1,
                block.virtual_region.y + container.virtual_region.y,
            )
        except Exception:
            pass
        await self.app.mount(menu)
        menu.focus()

    def action_copy_to_clipboard(self, block: Widget | None = None) -> None:
        if block is None:
            block = self.cursor_block
        if isinstance(block, MenuProtocol):
            text = block.get_block_content("clipboard")
        else:
            text = None
        if text:
            self.app.copy_to_clipboard(text)
            self.flash("Copied to clipboard")

    def action_copy_to_prompt(self) -> None:
        block = self.cursor_block
        if isinstance(block, MenuProtocol):
            text = block.get_block_content("prompt")
        else:
            text = None
        if text:
            self.flash("Copied to prompt")
            self.app.pop_screen()

    def action_maximize_block(self) -> None:
        if (block := self.cursor_block) is not None:
            self.app.screen.maximize(block, container=False)
            block.focus()

    def action_expand_block(self) -> None:
        if (block := self.cursor_block) is not None and isinstance(block, ExpandProtocol):
            block.expand_block()
            self._refresh_block_cursor()

    def action_collapse_block(self) -> None:
        if (block := self.cursor_block) is not None and isinstance(block, ExpandProtocol):
            block.collapse_block()
            self._refresh_block_cursor()

    def action_toggle_expand(self) -> None:
        block = self.cursor_block
        if block is None:
            # No cursor → fall back to "toggle latest completed thought"
            try:
                container = self.query_one("#content", VerticalGroup)
                for child in reversed(container.children):
                    if isinstance(child, AgentThought) and child._completed:
                        child.action_toggle()
                        return
            except Exception:
                return
            return
        if isinstance(block, ExpandProtocol):
            if block.is_block_expanded():
                block.collapse_block()
            else:
                block.expand_block()
            self._refresh_block_cursor()

    # ── Title / Footer ──

    def _update_title(self) -> None:
        sa = self.subagent
        status_icon = {"running": "🔄", "completed": "✔", "failed": "✗"}.get(sa._status, "?")
        self.title = f"{status_icon} Subagent ({sa.agent_type})"
        chunks = len("".join(sa._chunks))
        tools = len(sa._tool_calls)
        parts = [sa._status]
        if chunks:
            parts.append(f"{chunks}B")
        if tools:
            parts.append(f"{tools} tool calls")
        self.sub_title = " | ".join(parts)

    def _update_footer(self) -> None:
        try:
            self.query_one("#footer", Static).update(
                "[$text-muted]esc[/] 返回  "
                "[$text-muted]ctrl+j/k[/] 移动  "
                "[$text-muted]enter[/] 菜单  "
                "[$text-muted]ctrl+x[/] 折叠  "
                "[$text-muted]↑↓[/] 滚动"
            )
        except Exception:
            pass

    # ── Scroll actions ──

    def _scroll_widget(self) -> VerticalScroll | None:
        try:
            return self.query_one("#scroll", VerticalScroll)
        except Exception:
            return None

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

    # ── Scroll tracking ──

    def on_scroll(self, event) -> None:
        try:
            scroll = self.query_one("#scroll", VerticalScroll)
            at_end = scroll.scroll_y >= scroll.max_scroll_y - 1
            self._auto_follow = at_end
        except Exception:
            pass