import re  # re2 doesn't have MULTILINE
from typing import Iterable
from rich.text import Text

from textual import on
from textual import events
from textual.app import ComposeResult
from textual import getters

from textual.content import Content
from textual.reactive import var
from textual.css.query import NoMatches
from textual import containers
from textual.widgets import Static, Markdown

from tui.app import A2TUIApp
from tui.acp import protocol
from tui.menus import MenuItem
from tui.pill import pill


class TextContent(Static):
    DEFAULT_CSS = """
    TextContent 
    {
        height: auto;
    }
    """


class MarkdownContent(Markdown):
    pass


class ToolCallItem(containers.HorizontalGroup):
    def compose(self) -> ComposeResult:
        yield Static(classes="icon")


class ToolCallDiff(Static):
    DEFAULT_CSS = """
    ToolCallDiff {
        height: auto;
    }
    """


class ToolCallHeader(Static):
    ALLOW_SELECT = False
    DEFAULT_CSS = """
    ToolCallHeader {
        width: auto;
        max-width: 1fr;        
        &:hover {
            background: $panel;
        }
    }
    """


class ViewMore(Static):
    DEFAULT_CSS = """
    ViewMore {
        width: 1fr;
        text-align: center;
        color: $accent;
        &:hover {
            color: $text-accent;
        }
        visibility: hidden;
    }
    ViewMore.-visible {
        visibility: visible;
    }
    """


def compose_content_block(content_block: protocol.ContentBlock) -> ComposeResult:
    match content_block:
        case {"type": "text", "text": text}:
            assert isinstance(text, str)
            if "\x1b" in text:
                parsed_ansi_text = Text.from_ansi(text)
                yield TextContent(Content.from_rich_text(parsed_ansi_text))
            elif "```" in text or re.search(
                r"^#{1,6}\s.*$", text, re.MULTILINE
            ):
                yield MarkdownContent(text)
            else:
                yield TextContent(text, markup=False)


def compose_tool_content(
    tool_call_content: list[protocol.ToolCallContent],
    app: A2TUIApp | None = None,
) -> ComposeResult:
    for content in tool_call_content:
        match content:
            case {"type": "content", "content": sub_content}:
                yield from compose_content_block(sub_content)
            case {
                "type": "diff",
                "path": path,
                "oldText": old_text,
                "newText": new_text,
            }:
                from tui.widgets.diff_view import make_diff

                yield (diff_view := make_diff(path, path, old_text, new_text))

                if isinstance(app, A2TUIApp):
                    diff_view_setting = app.settings.get("diff.view", str)
                    diff_view.split = diff_view_setting == "split"
                    diff_view.auto_split = diff_view_setting == "auto"

            case {"type": "terminal", "terminalId": terminal_id}:
                pass


class ToolCall(containers.VerticalGroup):
    DEFAULT_CLASSES = "block"

    app = getters.app(A2TUIApp)
    has_content: var[bool] = var(False, toggle_class="-has-content")
    expanded: var[bool] = var(False, toggle_class="-expanded")
    tool_call: var[protocol.ToolCall | None] = var(None)

    def __init__(
        self,
        tool_call: protocol.ToolCall,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self.set_reactive(ToolCall.tool_call, tool_call)
        super().__init__(id=id, classes=classes)

    async def update_tool_call(self, tool_call: protocol.ToolCall) -> None:
        self.tool_call = tool_call
        await self.recompose()

    def get_block_menu(self) -> Iterable[MenuItem]:
        if self.expanded:
            yield MenuItem("Collapse", "block.collapse", "x")
        else:
            yield MenuItem("Expand", "block.expand", "x")

    def action_collapse(self) -> None:
        self.expanded = False

    def action_expand(self) -> None:
        self.expanded = True

    def get_block_content(self, destination: str) -> str | None:
        return None

    def can_expand(self) -> bool:
        return self.has_content

    def expand_block(self) -> None:
        self.expanded = True

    def collapse_block(self) -> None:
        self.expanded = False

    def is_block_expanded(self) -> bool:
        return self.expanded

    def compose(self) -> ComposeResult:
        tool_call = self.tool_call
        assert tool_call is not None
        content: list[protocol.ToolCallContent] = tool_call.get("content", None) or []

        self.set_class(tool_call.get("status") == "failed", "-failed")

        self.has_content = False
        content_update = list(self._compose_content(content))

        yield ToolCallHeader(self.tool_call_header_content, markup=False).with_tooltip(
            "Expand to see full title"
        ) if self.has_content else ToolCallHeader(self.tool_call_header_content, markup=False)
        with containers.VerticalScroll(id="tool-content"):
            yield from content_update
        yield ViewMore(Content.from_markup("[$accent]▼ View more ▼"), id="view-more")
        self.check_expand()

    def on_mount(self) -> None:
        self.check_expand()

    def check_expand(self) -> None:
        if not self.has_content:
            return
        tool_call = self.tool_call
        assert tool_call is not None
        if tool_call.get("kind", "") == "read":
            return
        tool_call_expand = self.app.settings.get("tools.expand", str, expand=False)
        status = tool_call.get("status")
        if tool_call_expand == "always":
            self.expanded = True
        elif tool_call_expand != "never" and status is not None:
            if tool_call_expand == "success":
                self.expanded = status == "completed"
            elif tool_call_expand == "fail":
                self.expanded = status == "failed"
            elif tool_call_expand == "both":
                self.expanded = status in ("completed", "failed")

    _TOOL_ICONS: dict[str, str] = {
        "Task": "🧠",
        "Agent": "🧠",
        "TaskCreate": "📋",
        "TaskGet": "📋",
        "TaskList": "📋",
        "TaskUpdate": "📋",
        "TaskOutput": "📋",
        "TaskStop": "📋",
        "TodoCreate": "📋",
        "TodoList": "📋",
        "TodoComplete": "📋",
    }

    @property
    def tool_call_header_content(self) -> Content:
        tool_call = self.tool_call
        assert tool_call is not None
        _kind = tool_call.get("kind", "tool")
        title = tool_call.get("title", "title")
        status = tool_call.get("status", "pending")

        tool_name = title.split(":")[0] if ":" in title else title
        icon = self._TOOL_ICONS.get(tool_name, "🔧")

        expand_icon: Content = Content()
        if self.has_content:
            expand_icon = Content.from_markup(
                "[$text-secondary]▼ " if self.expanded else "[$text-secondary]▶ "
            )

        header = Content.assemble(expand_icon, f"{icon} ", title)

        if status == "pending":
            header += Content.assemble(" ⌛")
        elif status == "in_progress":
            header += Content.from_markup(" [$text-warning]🔄")
        elif status == "failed":
            header += Content.assemble(" ", pill("failed", "$error-muted", "$error"))
        elif status == "completed":
            header += Content.from_markup(" [$success]✔")
        return header

    def watch_expanded(self) -> None:
        try:
            self.query_one(ToolCallHeader).update(self.tool_call_header_content)
        except NoMatches:
            pass

        try:
            tool_content = self.query_one("#tool-content")
        except NoMatches:
            pass
        else:
            max_height_pct = self.app.settings.get("tools.max_height", int)
            if self.expanded and max_height_pct and max_height_pct > 0:
                tool_content.styles.max_height = f"{max_height_pct}vh"
            else:
                tool_content.styles.max_height = None

            self.call_after_refresh(self._check_content_overflow)

        from tui.widgets.conversation import Conversation

        try:
            conversation = self.query_ancestor(Conversation)
        except NoMatches:
            pass
        else:
            self.call_after_refresh(conversation.cursor.update_follow)

    def _check_content_overflow(self) -> None:
        try:
            tool_content = self.query_one("#tool-content")
            view_more = self.query_one("#view-more", ViewMore)
        except NoMatches:
            return
        if not self.expanded or not isinstance(tool_content, containers.VerticalScroll):
            view_more.remove_class("-visible")
            return
        overflowing = tool_content.max_scroll_y > 0
        view_more.set_class(overflowing, "-visible")

    @on(events.Click, "ToolCallHeader")
    def on_click_tool_call_header(self, event: events.Click) -> None:
        event.stop()
        if self.has_content:
            self.expanded = not self.expanded

    @on(events.Click, "ViewMore")
    def on_click_view_more(self, event: events.Click) -> None:
        event.stop()
        from tui.screens.tool_content_screen import ToolContentScreen

        assert self.tool_call is not None
        self.app.push_screen(ToolContentScreen(self.tool_call))

    def _compose_content(
        self, tool_call_content: list[protocol.ToolCallContent]
    ) -> ComposeResult:
        found = False
        for widget in compose_tool_content(tool_call_content, self.app):
            yield widget
            found = True
        if found:
            self.has_content = True


if __name__ == "__main__":
    from textual.app import App, ComposeResult

    TOOL_CALL_READ: protocol.ToolCall = {
        "sessionUpdate": "tool_call",
        "toolCallId": "write_file-1759480341499",
        "status": "completed",
        "title": "Foo",
        "content": [
            {
                "type": "diff",
                "path": "fib.py",
                "oldText": "",
                "newText": 'def fibonacci(n):\n    """Generates the Fibonacci sequence up to n terms."""\n    a, b = 0, 1\n    for _ in range(n):\n        yield a\n        a, b = b, a + b\n\nif __name__ == "__main__":\n    for number in fibonacci(10):\n        print(number)\n',
            }
        ],
    }

    TOOL_CALL_CONTENT: protocol.ToolCall = {
        "sessionUpdate": "tool_call",
        "toolCallId": "run_shell_command-1759480356886",
        "status": "completed",
        "title": "Bar",
        "content": [
            {
                "type": "content",
                "content": {
                    "type": "text",
                    "text": "0\n1\n1\n2\n3\n5\n8\n13\n21\n34",
                },
            }
        ],
    }

    TOOL_CALL_EMPTY: protocol.ToolCall = {
        "sessionUpdate": "tool_call",
        "toolCallId": "run_shell_command-1759480356886",
        "status": "completed",
        "title": "Bar",
        "content": [],
    }

    class ToolApp(App):
        def on_mount(self) -> None:
            self.theme = "dracula"

        def compose(self) -> ComposeResult:
            yield ToolCall(TOOL_CALL_READ)
            yield ToolCall(TOOL_CALL_CONTENT)
            yield ToolCall(TOOL_CALL_EMPTY)

    ToolApp().run()
