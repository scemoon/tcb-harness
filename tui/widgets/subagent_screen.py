from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Grid, Vertical, VerticalGroup, VerticalScroll
from textual.css.query import NoMatches
from textual.geometry import Offset, Region, Spacing
from textual.layouts.grid import GridLayout
from textual.layouts.vertical import WidgetPlacement
from textual.reactive import reactive
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Header, Static

from rich.segment import Segment
from textual.strip import Strip

from tui.menus import MenuItem
from tui.protocol import BlockProtocol, ExpandProtocol, MenuProtocol
from tui.widgets.agent_response import AgentResponse
from tui.widgets.agent_thought import AgentThought
from tui.widgets.conversation import Cursor
from tui.widgets.menu import Menu
from tui.widgets.subagent import SubAgent
from tui.widgets.tool_call import ToolCall as ToolCallWidget

_sa_logger = logging.getLogger("tui.widgets.subagent_screen")
_DEBUG_LOG = Path.home() / ".cdh" / "logs" / "subagent_cursor_debug.log"

_TODO_TOOLS: frozenset[str] = frozenset({
    "TodoCreate", "TodoGet", "TodoList", "TodoUpdate",
    "TodoOutput", "TodoStop", "TodoClear",
})

_SELECTABLE_BLOCK_TYPES: tuple[type[Widget], ...] = (
    AgentResponse,
    AgentThought,
    ToolCallWidget,
)


def _is_selectable(child: Widget) -> bool:
    return isinstance(child, _SELECTABLE_BLOCK_TYPES)


class SubAgentCursorContainer(Vertical):
    def render_lines(self, crop: Region) -> list[Strip]:
        rich_style = self.visual_style.rich_style
        strips = [Strip([Segment("▌", rich_style)], cell_length=1)] * crop.height
        if crop.y == 0 and strips:
            strips[0] = Strip([Segment(" ", rich_style)], cell_length=1)
        return strips


class SubAgentContentsGrid(Grid):
    BLANK = True

    def pre_layout(self, layout) -> None:
        assert isinstance(layout, GridLayout)
        layout.stretch_height = True


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
        padding-bottom: 1;
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
    }

    #cursor-container > Cursor {
        height: 0;
        width: 1;
        border-left: outer $text-accent;
        visibility: visible;
        &.-blink {
            border-left: outer $text-accent 20%;
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
        _DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        _sa_logger.addHandler(logging.FileHandler(str(_DEBUG_LOG), mode="w"))
        _sa_logger.setLevel(logging.DEBUG)
        self.subagent = subagent
        self._event_lock = asyncio.Lock()
        self._current_response: AgentResponse | None = None
        self._current_thought: AgentThought | None = None
        self._auto_follow = True
        self._active_menu: Menu | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll(id="scroll"):
            with SubAgentContentsGrid(id="content-grid"):
                with SubAgentCursorContainer(id="cursor-container"):
                    yield Cursor()
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
        # Subscribe first so we don't miss events during replay
        self.subagent._screen_handler = self._on_event
        # Replay all existing events with yields so the UI can render progressively
        await self._replay_all()
        try:
            self.query_one("#scroll", VerticalScroll).focus()
        except Exception:
            pass

    def on_unmount(self) -> None:
        self.subagent._screen_handler = None
        self._current_response = None
        self._current_thought = None

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if self._active_menu is not None and action in (
            "select_block",
            "scroll_up",
            "scroll_down",
            "scroll_page_up",
            "scroll_page_down",
            "scroll_home",
            "scroll_end",
            "app.pop_screen",
        ):
            return False
        return True

    # ── Event processing ──

    async def _replay_all(self) -> None:
        """Process every event already in ``subagent._events``.

        Each event is followed by ``await asyncio.sleep(0)`` so the layout
        can settle between mounts – this avoids a long blocking stall
        before the screen becomes visible.
        """
        try:
            container = self.query_one("#content", VerticalGroup)
            for event_type, data in self.subagent._events:
                await self._handle_one(container, event_type, data)
                await asyncio.sleep(0)
            await self._flush_streams()
            self._post_process()
        except Exception:
            _sa_logger.exception("_replay_all failed")

    async def _on_event(self, event_type: str, data) -> None:
        """Handle a single real-time event from the SubAgent.

        Called via ``run_worker`` inside ``SubAgent.*`` methods.
        The lock serialises concurrently-scheduled workers.
        """
        async with self._event_lock:
            try:
                container = self.query_one("#content", VerticalGroup)
                await self._handle_one(container, event_type, data)
                self._post_process()
            except Exception:
                _sa_logger.exception("_on_event failed")

    async def _handle_one(self, container: VerticalGroup, event_type: str, data) -> None:
        """Dispatch a single event to the appropriate handler."""
        if event_type == "thinking":
            await self._handle_thinking(container, data)
        elif event_type == "text":
            self._complete_current_thought()
            await self._handle_text(container, data)
        elif event_type == "tool":
            self._complete_current_thought()
            await self._handle_tool(container, data)
        elif event_type == "complete":
            self._complete_current_thought()

    def _post_process(self) -> None:
        """Common work after every event – title, footer, cursor, scroll."""
        try:
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
            _sa_logger.exception("_post_process failed")

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

        # Skip todo tool calls — not relevant in subagent view
        title = tc.get("title", "") if isinstance(tc, dict) else ""
        tool_name = title.split(":")[0] if ":" in title else title
        if tool_name in _TODO_TOOLS:
            return

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
            self.query_one("#scroll", VerticalScroll).scroll_end(animate=True)
        except Exception:
            pass

    async def _flush_streams(self) -> None:
        """Ensure all markdown streams have finished processing before cursor navigation."""
        try:
            container = self.query_one("#content", VerticalGroup)
        except Exception:
            return
        for child in container.children:
            stream = getattr(child, "_stream", None)
            if stream is not None:
                _sa_logger.warning(
                    "▓ flush stream | widget=%s | task_alive=%s",
                    type(child).__name__,
                    stream._task is not None and not stream._task.done() if stream._task else False,
                )
                try:
                    await stream.stop()
                except Exception:
                    pass
            else:
                _sa_logger.warning(
                    "▓ no stream | widget=%s | children=%s",
                    type(child).__name__,
                    len(child.children) if hasattr(child, 'children') else '?',
                )

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

    @property
    def cursor_block_child(self) -> Widget | None:
        if (block := self.cursor_block) is not None:
            if isinstance(block, BlockProtocol):
                inner = block.get_cursor_block()
                if inner is not None:
                    _sa_logger.warning(
                        "┃  child inner=%s children=%s attached=%s",
                        type(inner).__name__,
                        len(block.children) if hasattr(block, 'children') else '?',
                        inner.is_attached,
                    )
                    return inner
                _sa_logger.warning(
                    "┃  child fallback → outer=%s children=%s",
                    type(block).__name__,
                    len(block.children) if hasattr(block, 'children') else '?',
                )
        return block

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
        block = self.cursor_block_child
        if block is not None:
            cursor.visible = True
            cursor.follow(block)
            _sa_logger.warning(
                "┃  follow | block=%s | offset=(%s,%s) | h=%s | visible=%s",
                type(block).__name__,
                cursor.offset.x, cursor.offset.y,
                cursor.styles.height,
                cursor.visible,
            )
            scroll = self._scroll_widget()
            if scroll is not None:
                scroll.focus()
                self.call_after_refresh(
                    scroll.scroll_to_center, block, immediate=True
                )
        else:
            cursor.visible = False
            cursor.follow(None)
        self.refresh_bindings()

    def action_cursor_up(self) -> None:
        children = self._selectable_children()
        _sa_logger.warning(
            "▲ cursor_up | offset=%s | num_children=%s | types=%s",
            self.cursor_offset,
            len(children),
            [type(c).__name__ for c in children],
        )
        if not children:
            return
        if self.cursor_offset == -1:
            self.cursor_offset = len(children) - 1
            cursor_block = self.cursor_block
            if isinstance(cursor_block, BlockProtocol):
                cursor_block.block_cursor_clear()
                cursor_block.block_cursor_up()
        else:
            cursor_block = self.cursor_block
            if isinstance(cursor_block, BlockProtocol):
                if cursor_block.block_cursor_up() is None:
                    if self.cursor_offset > 0:
                        self.cursor_offset -= 1
                        cursor_block = self.cursor_block
                        if isinstance(cursor_block, BlockProtocol):
                            cursor_block.block_cursor_clear()
                            cursor_block.block_cursor_up()
            else:
                if self.cursor_offset > 0:
                    self.cursor_offset -= 1
                    cursor_block = self.cursor_block
                    if isinstance(cursor_block, BlockProtocol):
                        cursor_block.block_cursor_clear()
                        cursor_block.block_cursor_up()
        self._auto_follow = False
        self._refresh_block_cursor()

    def action_cursor_down(self) -> None:
        children = self._selectable_children()
        if not children or self.cursor_offset == -1:
            return
        cursor_block = self.cursor_block
        if isinstance(cursor_block, BlockProtocol):
            if cursor_block.block_cursor_down() is None:
                if self.cursor_offset < len(children) - 1:
                    self.cursor_offset += 1
                    cursor_block = self.cursor_block
                    if isinstance(cursor_block, BlockProtocol):
                        cursor_block.block_cursor_clear()
                        cursor_block.block_cursor_down()
        else:
            if self.cursor_offset < len(children) - 1:
                self.cursor_offset += 1
                cursor_block = self.cursor_block
                if isinstance(cursor_block, BlockProtocol):
                    cursor_block.block_cursor_clear()
                    cursor_block.block_cursor_down()
        self._auto_follow = False
        self._refresh_block_cursor()

    async def action_select_block(self) -> None:
        block = self.cursor_block
        if block is None:
            return
        menu_options: list[MenuItem] = [
            MenuItem("[u]C[/]opy to clipboard", "copy_to_clipboard", "c"),
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
        await self.mount(menu)
        menu.focus()
        self._active_menu = menu

    @on(Menu.OptionSelected)
    async def on_menu_option_selected(self, event: Menu.OptionSelected) -> None:
        event.stop()
        event.menu.display = False
        if event.action is not None:
            await self.run_action(event.action, {"block": event.owner})
        self._active_menu = None
        self.call_after_refresh(event.menu.remove)

    @on(Menu.Dismissed)
    async def on_menu_dismissed(self, event: Menu.Dismissed) -> None:
        event.stop()
        if event.menu.has_focus:
            self.query_one("#scroll", VerticalScroll).focus(scroll_visible=False)
        self._active_menu = None
        await event.menu.remove()

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
            w.scroll_end(animate=True)

    # ── Scroll tracking ──

    def on_scroll(self, event) -> None:
        try:
            scroll = self.query_one("#scroll", VerticalScroll)
            at_end = scroll.scroll_y >= scroll.max_scroll_y - 1
            self._auto_follow = at_end
        except Exception:
            pass