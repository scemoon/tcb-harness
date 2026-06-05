import logging
import asyncio
import json as json_mod
import re  # re2 doesn't have MULTILINE

logger = logging.getLogger("tui.tool_call")
from typing import Iterable

from textual import on
from textual import events
from textual.app import ComposeResult
from textual import getters

from textual.content import Content
from textual.reactive import reactive, var
from textual.css.query import NoMatches
from textual import containers
from textual.widgets import Static, Markdown
from textual.widgets.markdown import MarkdownStream

from tui.app import A2TUIApp
from tui.acp import protocol
from tui.menus import MenuItem
from tui.pill import pill


_LEGACY_TOOL_CALL_RE = re.compile(
    r"\{[^{}]*tool\s*=>\s*\"[^\"]+\"[^{}]*args\s*=>",
    re.DOTALL,
)


def _looks_like_legacy_tool_call(text: str) -> bool:
    """Detect legacy `{tool => "X", args => { ... }}` text that slipped through."""
    return bool(_LEGACY_TOOL_CALL_RE.search(text))


def _scan_balanced_braces(text: str, open_pos: int) -> int | None:
    """Find the matching '}' for the '{' at open_pos, handling nesting & strings."""
    if open_pos < 0 or open_pos >= len(text) or text[open_pos] != "{":
        return None
    depth = 0
    i = open_pos
    n = len(text)
    while i < n:
        c = text[i]
        if c == "{":
            depth += 1
            i += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
            i += 1
        elif c in ('"', "'"):
            quote = c
            i += 1
            while i < n and text[i] != quote:
                if text[i] == "\\" and i + 1 < n:
                    i += 2
                else:
                    i += 1
            i += 1
        else:
            i += 1
    return None


_LANG_BY_EXT: dict[str, str] = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "jsx", ".tsx": "tsx", ".json": "json", ".yml": "yaml",
    ".yaml": "yaml", ".toml": "toml", ".md": "markdown", ".sh": "bash",
    ".html": "html", ".css": "css", ".rs": "rust", ".go": "go",
    ".java": "java", ".kt": "kotlin", ".swift": "swift", ".rb": "ruby",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".sql": "sql",
}


def _language_for_path(path: str) -> str:
    if not path:
        return ""
    dot = path.rfind(".")
    slash = max(path.rfind("/"), path.rfind("\\"))
    if dot > slash and dot >= 0:
        return _LANG_BY_EXT.get(path[dot:].lower(), "")
    return ""


def _reparse_legacy_tool_call(text: str) -> None | list[dict[str, str | dict[str, str]]] | list[dict[str, str]]:
    """Re-parse a legacy `{tool => "X", args => { ... }}` text and convert
    it into the structured content blocks the TUI's widgets expect.

    Write → path header + code fence (readable as code).
    Edit  → diff block (real before/after).
    """
    if not _looks_like_legacy_tool_call(text):
        return None

    name_match = re.search(r'tool\s*=>\s*"([^"]+)"', text)
    args_match = re.search(r'args\s*=>\s*\{', text)
    if not name_match or not args_match:
        return None
    name = name_match.group(1)
    args_outer = _scan_balanced_braces(text, args_match.end() - 1)
    if args_outer is None:
        return None
    args_body = text[args_match.end():args_outer]

    arguments: dict[str, str] = {}
    for am in re.finditer(
        r'--(\w+)\s+"((?:[^"\\]|\\.)*)"', args_body, re.DOTALL
    ):
        arguments[am.group(1)] = am.group(2)

    if name == "Write" and "path" in arguments and "content" in arguments:
        path = arguments["path"]
        lang = _language_for_path(path)
        return [{
            "type": "content",
            "content": {
                "type": "text",
                "text": f"📄 {path}\n```{lang}\n{arguments['content']}\n```",
            },
        }]

    if name == "Edit" and "path" in arguments:
        old = arguments.get("old_string", arguments.get("oldText", ""))
        new = arguments.get("new_string", arguments.get("newText", ""))
        return [{
            "type": "diff",
            "path": arguments["path"],
            "oldText": old,
            "newText": new,
        }]

    if name == "Bash":
        cmd = arguments.get("command", arguments.get("cmd", ""))
        if cmd:
            return [{
                "type": "content",
                "content": {"type": "text", "text": f"```bash\n$ {cmd}\n```"},
            }]

    if name == "Read" and "path" in arguments:
        return [{
            "type": "content",
            "content": {"type": "text", "text": f"📄 {arguments['path']}"},
        }]

    import json
    args_text = json.dumps(arguments, indent=2, ensure_ascii=False)
    return [{
        "type": "content",
        "content": {"type": "text", "text": f"```json\n{args_text}\n```"},
    }]


def _dispatch_reparsed(block: protocol.ToolCallContent) -> ComposeResult:
    """Render a content block recovered from legacy text into TUI widgets.

    Content blocks holding Markdown (e.g. with ` ``` ` fences) go through
    MarkdownContent so code fences render as real highlighted code blocks.
    Plain text falls through to TextContent.
    """
    if block.get("type") == "diff":
        from tui.widgets.diff_view import make_diff
        yield make_diff(
            block.get("path", ""),
            block.get("path", ""),
            block.get("oldText") or "",
            block.get("newText") or "",
        )
    elif block.get("type") == "content":
        inner = block.get("content")
        if isinstance(inner, dict) and inner.get("type") == "text":
            text = inner.get("text", "")
            if "```" in text or re.search(r"^#{1,6}\s.*$", text, re.MULTILINE):
                yield MarkdownContent(text)
            else:
                yield TextContent(text, markup=False)


_FENCED_RE = re.compile(r"^(.*?\n)?```(\w+)?\n(.+?)\n```\s*$", re.DOTALL)


def _pretty_json(text: str) -> str:
    """Pretty-print JSON inside Markdown text, handling code fences & escapes."""
    m = _FENCED_RE.match(text.strip())
    if m:
        prefix = (m.group(1) or "").strip()
        lang = m.group(2) or ""
        inner = m.group(3)
        formatted = _pretty_json(inner)
        if formatted != inner:
            parts = [f"```{lang}\n{formatted}\n```" if prefix == "" else f"{prefix}\n```{lang}\n{formatted}\n```"]
            return "\n".join(parts)
        return text
    stripped = text.strip()
    if not (stripped.startswith("{") or stripped.startswith("[")):
        return text
    try:
        obj = json_mod.loads(stripped)
        return json_mod.dumps(obj, indent=2, ensure_ascii=False)
    except (json_mod.JSONDecodeError, ValueError):
        pass
    try:
        unescaped = stripped.encode("utf-8").decode("unicode_escape")
        obj = json_mod.loads(unescaped)
        return json_mod.dumps(obj, indent=2, ensure_ascii=False)
    except Exception:
        return text


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
        self._content_rendered = 0
        super().__init__(id=id, classes=classes)

    async def update_tool_call(self, tool_call: protocol.ToolCall) -> None:
        """Update the tool call state and mount new content blocks incrementally.

        Args:
            tool_call: New Tool call data.
        """
        self.tool_call = tool_call
        content: list[protocol.ToolCallContent] = tool_call.get("content", None) or []
        kind = tool_call.get("kind", "")

        logger.debug(
            "update_tool_call: id=%s status=%s kind=%s content_blocks=%d rendered=%d",
            tool_call.get("toolCallId", "?"),
            tool_call.get("status"),
            kind,
            len(content),
            self._content_rendered,
        )

        try:
            self.query_one(ToolCallHeader).update(self.tool_call_header_content)
        except NoMatches:
            pass
        self.set_class(tool_call.get("status") == "failed", "-failed")

        try:
            content_area = self.query_one("#tool-content", containers.VerticalGroup)
        except NoMatches:
            await self.recompose()
            self.call_after_refresh(self.update_tool_call, tool_call)
            return

        for i in range(self._content_rendered, len(content)):
            block = content[i]
            logger.debug(
                "  content[%d] block_type=%s%s",
                i, block.get("type"),
                f" text_len={len(block.get('content', {}).get('text', ''))}"
                if isinstance(block.get("content"), dict) else "",
            )
            match block:
                case {"type": "content", "content": {"type": "text", "text": text}}:
                    if text:
                        md = Markdown(_pretty_json(text), classes="tool-content-md")
                        await content_area.mount(md)
                    self.has_content = True
                case {
                    "type": "diff",
                    "path": path,
                    "oldText": old_text,
                    "newText": new_text,
                }:
                    from tui.widgets.diff_view import make_diff

                    dy = make_diff(path, path, old_text, new_text)
                    if isinstance(self.app, A2TUIApp):
                        dvs = self.app.settings.get("diff.view", str)
                        dy.split = dvs == "split"
                        dy.auto_split = dvs == "auto"
                    await content_area.mount(dy)
                    self.has_content = True
                case {"type": "terminal", "terminalId": _}:
                    pass
                case _:
                    self.has_content = True
                    try:
                        md = Markdown(str(block), classes="tool-content-md")
                        await content_area.mount(md)
                    except Exception:
                        pass

        self._content_rendered = len(content)
        self.check_expand()
        logger.debug(
            "  => has_content=%s expanded=%s rendered=%d",
            self.has_content, self.expanded, self._content_rendered,
        )

    def _stream_text_into_md(self, md: Markdown, text: str) -> None:
        """Stream text into a Markdown widget with progressive reveal effect."""
        stream = Markdown.get_stream(md)
        task = asyncio.create_task(self._do_stream(stream, text))
        task.add_done_callback(self._on_stream_done)

    @staticmethod
    async def _do_stream(stream: MarkdownStream, text: str) -> None:
        """Write text chunks to a MarkdownStream with small delays."""
        try:
            chunk_size = 5
            for i in range(0, len(text), chunk_size):
                await stream.write(text[i:i + chunk_size])
                await asyncio.sleep(0.015)
        except Exception:
            pass

    @staticmethod
    def _on_stream_done(task: asyncio.Task) -> None:
        """Suppress unhandled task exceptions."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.debug("_do_stream failed: %s", exc)

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

        kind = tool_call.get("kind", "other")
        self.set_class(True, f"-kind-{kind}")
        self.set_class(tool_call.get("status") == "failed", "-failed")
        if kind == "think":
            self.set_class(tool_call.get("status") == "pending", "-status-pending")

        self.has_content = False

        yield ToolCallHeader(self.tool_call_header_content, markup=False).with_tooltip(
            "Expand to see full title"
        )
        with containers.VerticalGroup(id="tool-content"):
            pass
        self.check_expand()

    def on_mount(self) -> None:
        self.check_expand()

    def check_expand(self) -> None:
        """Check if the tool call should auto-expand."""
        if not self.has_content:
            return
        tool_call = self.tool_call
        assert tool_call is not None
        kind = tool_call.get("kind", "")
        status = tool_call.get("status", "")
        if kind == "read":
            return
        if kind in ("think", "edit"):
            self.expanded = True
            return
        # Expand pending tool calls that have content — likely waiting for
        # permission approval (e.g. bash commands, web fetches, etc.).
        if status == "pending":
            self.expanded = True
            return
        tool_call_expand = self.app.settings.get("tools.expand", str, expand=False)
        if tool_call_expand == "always":
            self.expanded = True
        elif tool_call_expand != "never":
            if tool_call_expand == "success":
                self.expanded = status == "completed"
            elif tool_call_expand == "fail":
                self.expanded = status == "failed"
            elif tool_call_expand == "both":
                self.expanded = status in ("completed", "failed")

    def _header_path(self) -> str:
        """Extract filename from content blocks to show alongside the title."""
        tc = self.tool_call
        if tc is None:
            return ""
        for block in tc.get("content", []) or []:
            match block:
                case {"type": "diff", "path": path}:
                    return path.rsplit("/", 1)[-1]
                case {"type": "content", "content": {"type": "text", "text": text}}:
                    m = re.search(r"📄\s*(\S+)", text)
                    if m:
                        return m.group(1).rsplit("/", 1)[-1]
        return ""

    @property
    def tool_call_header_content(self) -> Content:
        tool_call = self.tool_call
        assert tool_call is not None
        kind = tool_call.get("kind", "tool")
        title = tool_call.get("title", "title")
        status = tool_call.get("status", "pending")

        expand_icon: Content = Content()
        if self.has_content:
            expand_icon = Content.from_markup(
                "[$text-secondary]▼ " if self.expanded else "[$text-secondary]▶ "
            )
        else:
            expand_icon = Content.from_markup(
                "[$text-secondary 30%]▼ "
                if self.expanded
                else "[$text-secondary 30%]▶ "
            )

        icon_map = {
            "think": "💭 ",
            "read": "📖 ",
            "edit": "✏️ ",
            "search": "🔍 ",
            "execute": "⚡ ",
            "fetch": "🌐 ",
            "delete": "🗑️ ",
            "move": "📦 ",
            "switch_mode": "🔀 ",
            "task": "📋 ",
            "task_mgmt": "📌 ",
        }
        icon = icon_map.get(kind, "🔧 ")
        fname = self._header_path()
        display = f"{title} — {fname}" if fname else title
        header = Content.assemble(expand_icon, icon, display)

        if status == "pending":
            header += Content.assemble(" ⌛")
        elif status == "in_progress":
            pass
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
        from tui.widgets.conversation import Conversation

        try:
            conversation = self.query_ancestor(Conversation)
        except NoMatches:
            pass
        else:
            self.call_after_refresh(conversation.cursor.update_follow)

    @on(events.Click, "ToolCallHeader")
    def on_click_tool_call_header(self, event: events.Click) -> None:
        event.stop()
        if self.has_content:
            self.expanded = not self.expanded
        else:
            self.app.bell()




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
