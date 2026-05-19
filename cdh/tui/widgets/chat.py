from __future__ import annotations

import re
import json
from typing import Any, Optional, Union
from textual.widgets import RichLog, Static
from textual.containers import ScrollableContainer
from textual.app import ComposeResult
from rich.text import Text
from rich.syntax import Syntax
from rich.panel import Panel
from rich.markdown import Markdown as RichMarkdown
from rich.console import Group


class ContentBlock:
    TYPE_TEXT = "text"
    TYPE_THINKING = "thinking"
    TYPE_TOOL_USE = "tool_use"
    TYPE_TOOL_RESULT = "tool_result"
    TYPE_SERVER_TOOL_USE = "server_tool_use"
    TYPE_TOOL_SEARCH_RESULT = "tool_search_tool_result"
    TYPE_CODE_EXECUTION_RESULT = "code_execution_tool_result"

    def __init__(self, block: dict[str, Any]):
        self.type = block.get("type", "text")
        self.text = block.get("text", "")
        self.thinking = block.get("thinking", "")
        self.tool_use = block.get("tool_use")
        self.tool_result = block.get("tool_result")
        self.server_tool_use = block.get("server_tool_use")
        self.tool_search_result = block.get("tool_search_tool_result")
        self.code_execution_result = block.get("code_execution_result")

    @property
    def is_thinking(self) -> bool:
        return self.type == self.TYPE_THINKING

    @property
    def is_tool_use(self) -> bool:
        return self.type in (self.TYPE_TOOL_USE, self.TYPE_SERVER_TOOL_USE)

    @property
    def is_tool_result(self) -> bool:
        return self.type in (self.TYPE_TOOL_RESULT,)

    @property
    def is_text(self) -> bool:
        return self.type == self.TYPE_TEXT

    @property
    def is_tool_search_result(self) -> bool:
        return self.type == self.TYPE_TOOL_SEARCH_RESULT

    @property
    def is_code_execution_result(self) -> bool:
        return self.type == self.TYPE_CODE_EXECUTION_RESULT


# ── Stream Parser for detecting blocks from raw text ─────────────────────────

# ── Stream Parser for detecting blocks from raw text ─────────────────────────

class StreamParser:
    THINK_START_PAT = re.compile(r"<think[^>]*>", re.IGNORECASE)
    THINK_CODE_PAT = re.compile(r"```think\b.*?\n(.*?)```", re.DOTALL | re.IGNORECASE)

    TOOL_CALL_PAT = re.compile(r'<tool_call\s+name=["\']([^"\']+)["\']\s+id=["\']([^"\']+)["\']>(.*?)</tool_call>', re.DOTALL)
    TOOL_CALL_START_PAT = re.compile(r'<tool_call\s+name=["\']([^"\']+)["\']\s+id=["\']([^"\']+)["\']>')
    TOOL_USE_PAT = re.compile(r"```tool_use\b.*?\n(.*?)```", re.DOTALL | re.IGNORECASE)

    def __init__(self):
        self._buffer = ""
        self._in_thinking = False
        self._thinking_content = ""
        self._in_tool_call = False
        self._tool_call_name = ""
        self._tool_call_id = ""
        self._tool_call_input = ""
        self._tool_call_complete = False

    def feed(self, text: str) -> list[dict]:
        self._buffer += text
        blocks = []

        while self._buffer:
            if self._in_thinking:
                end_idx = self._buffer.find("</think>")
                if end_idx != -1:
                    content_before_end = self._buffer[:end_idx]
                    self._thinking_content += content_before_end
                    self._buffer = self._buffer[end_idx + len("</think>"):]
                    self._in_thinking = False
                    if self._thinking_content.strip():
                        blocks.append({"type": "thinking", "thinking": self._thinking_content.strip()})
                    self._thinking_content = ""
                else:
                    if self._buffer != ">":
                        self._thinking_content += self._buffer
                    self._buffer = ""
                    break

            if self._in_tool_call:
                end_idx = self._buffer.find("</tool_call>")
                if end_idx != -1:
                    input_before_end = self._buffer[:end_idx]
                    self._tool_call_input += input_before_end
                    self._buffer = self._buffer[end_idx + len("</tool_call>"):]
                    self._in_tool_call = False
                    self._tool_call_complete = True
                    try:
                        tool_input = json.loads(self._tool_call_input) if self._tool_call_input else {}
                    except json.JSONDecodeError:
                        tool_input = {"raw": self._tool_call_input}
                    blocks.append({
                        "type": "tool_use",
                        "tool_use": {
                            "name": self._tool_call_name,
                            "id": self._tool_call_id,
                            "input": tool_input
                        }
                    })
                    self._tool_call_input = ""
                    self._tool_call_name = ""
                    self._tool_call_id = ""
                else:
                    self._tool_call_input += self._buffer
                    self._buffer = ""
                    break
                continue

            if self._buffer.startswith("<think") and ">" not in self._buffer:
                break

            if self._buffer.startswith("<think>"):
                self._in_thinking = True
                self._thinking_content = ""
                self._buffer = self._buffer[len("<think>"):]
                continue

            think_code_match = self.THINK_CODE_PAT.match(self._buffer)
            if think_code_match:
                blocks.append({"type": "thinking", "thinking": think_code_match.group(1).strip()})
                self._buffer = self._buffer[think_code_match.end():]
                continue

            tool_match = self.TOOL_USE_PAT.match(self._buffer)
            if tool_match:
                try:
                    tool_data = json.loads(tool_match.group(1))
                    blocks.append({"type": "tool_use", "tool_use": tool_data})
                except json.JSONDecodeError:
                    blocks.append({"type": "text", "text": tool_match.group(0)})
                self._buffer = self._buffer[tool_match.end():]
                continue

            tool_call_start = self.TOOL_CALL_START_PAT.match(self._buffer)
            if tool_call_start:
                self._tool_call_name = tool_call_start.group(1)
                self._tool_call_id = tool_call_start.group(2)
                self._tool_call_input = ""
                self._tool_call_complete = False
                self._in_tool_call = True
                self._buffer = self._buffer[tool_call_start.end():]
                blocks.append({
                    "type": "tool_use_start",
                    "tool_use": {
                        "name": self._tool_call_name,
                        "id": self._tool_call_id,
                    }
                })
                continue

            text_end = len(self._buffer)
            next_think = self.THINK_START_PAT.search(self._buffer)
            next_tool = self.TOOL_USE_PAT.search(self._buffer)
            next_tool_call = self.TOOL_CALL_PAT.search(self._buffer)
            next_tool_call_start = self.TOOL_CALL_START_PAT.search(self._buffer)

            earliest = text_end
            for m in [next_think, next_tool, next_tool_call, next_tool_call_start]:
                if m and m.start() < earliest:
                    earliest = m.start()

            if earliest > 0:
                if earliest < text_end:
                    blocks.append({"type": "text", "text": self._buffer[:earliest]})
                    self._buffer = self._buffer[earliest:]
                else:
                    if len(self._buffer) > 10000:
                        blocks.append({"type": "text", "text": self._buffer})
                        self._buffer = ""
                    else:
                        break
            else:
                if len(self._buffer) > 10000:
                    blocks.append({"type": "text", "text": self._buffer})
                    self._buffer = ""
                else:
                    break

        return blocks

    def get_pending_text(self) -> str:
        """Return unparsed buffer text (no tag in progress)."""
        if not self._in_thinking and not self._in_tool_call and self._buffer:
            return self._buffer
        return ""

    def get_pending_thinking(self) -> str:
        """Return the current in-progress thinking content, even if not yet closed."""
        if self._in_thinking:
            return self._thinking_content
        return ""

    def get_pending_tool_call(self) -> dict:
        """Return the current in-progress tool_call block, even if not yet closed."""
        if self._in_tool_call:
            return {
                "name": self._tool_call_name,
                "id": self._tool_call_id,
                "input": self._tool_call_input,
                "complete": self._tool_call_complete,
            }
        return None

    def flush(self) -> list[dict]:
        blocks = []
        if self._in_thinking and self._thinking_content.strip():
            blocks.append({"type": "thinking", "thinking": self._thinking_content.strip()})
        if self._in_tool_call:
            try:
                tool_input = json.loads(self._tool_call_input) if self._tool_call_input else {}
            except json.JSONDecodeError:
                tool_input = {"raw": self._tool_call_input}
            blocks.append({
                "type": "tool_use",
                "tool_use": {
                    "name": self._tool_call_name,
                    "id": self._tool_call_id,
                    "input": tool_input
                }
            })
        if self._buffer.strip():
            blocks.append({"type": "text", "text": self._buffer})
        self._buffer = ""
        self._in_thinking = False
        self._thinking_content = ""
        self._in_tool_call = False
        self._tool_call_name = ""
        self._tool_call_id = ""
        self._tool_call_input = ""
        self._tool_call_complete = False
        return blocks

# ── Markdown parsing with Rich ───────────────────────────────────────────────

def _strip_think_blocks(text: str) -> str:
    for pat in (
        re.compile(r"<think[^>]*>(.*?)</think>", re.DOTALL | re.IGNORECASE),
        re.compile(r"```think\b.*?```", re.DOTALL | re.IGNORECASE),
    ):
        text = pat.sub("", text)
    return text.strip()


def _render_markdown_rich(text: str) -> list[Any]:
    from rich.markdown import Markdown
    from rich.console import Console

    output: list[Any] = []
    last_end = 0
    code_block_pat = re.compile(r"```(\w*)\n?(.*?)```", re.DOTALL)

    for match in code_block_pat.finditer(text):
        before = text[last_end : match.start()]
        if before.strip():
            stripped = _strip_think_blocks(before)
            if stripped.strip():
                md = Markdown(stripped, inline_code_lexer="ansi", code_theme="monokai")
                output.append(md)
        lang = match.group(1) or "ansi"
        code = match.group(2)
        syntax = Syntax(code, lang if lang else "ansi", theme="monokai", word_wrap=True)
        output.append(syntax)
        last_end = match.end()

    remaining = text[last_end:]
    if remaining.strip():
        stripped = _strip_think_blocks(remaining)
        if stripped.strip():
            md = Markdown(stripped, inline_code_lexer="ansi", code_theme="monokai")
            output.append(md)

    return output


class ChatPanel(ScrollableContainer):
    """Main chat area — shows user/assistant/system messages with live streaming."""

    DEFAULT_CSS = """
    ChatPanel {
        height: 100%;
        overflow-y: auto;
        scrollbar-size: 0 0;
        scrollbar-gutter: auto;
        padding: 0 0 0 0;
    }
    ChatPanel > #welcome {
        height: 100%;
        width: 100%;
        content-align: center middle;
    }
    ChatPanel > #chat-log {
        height: 1fr;
        padding: 0;
        scrollbar-size: 0 0;
        border: none;
    }
    ChatPanel > #stream-output {
        height: auto;
        display: none;
        padding: 0;
        margin: 0;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._streaming = False
        self._stream_buffer: list[str] = []
        self._char_buffer: list[str] = []
        self._stream_parser = StreamParser()
        self._stream_timer = None
        self._welcome_shown = False

    def compose(self) -> ComposeResult:
        yield Static(id="welcome")
        yield Static(id="stream-output")
        yield RichLog(id="chat-log", highlight=True, markup=True, max_lines=10000)

    def on_mount(self) -> None:
        self._show_welcome()

    def _hide_welcome(self) -> None:
        if self._welcome_shown:
            self._welcome_shown = False
            w = self.query_one_optional("#welcome", Static)
            if w is not None:
                w.display = False

    def _show_welcome(self) -> None:
        import os
        w = self.query_one_optional("#welcome", Static)
        if w is None:
            return
        app = self.app
        t = getattr(app, 'tui_theme', None)
        cwd = os.getcwd()
        model = getattr(app, "current_model", "unknown") if hasattr(app, "current_model") else "unknown"
        provider = getattr(app, "current_provider", "unknown") if hasattr(app, "current_provider") else "unknown"

        primary = t.primary if t else "#7aa2f7"
        dim = t.variables.get('text_dim', '#565f89') if t else "#565f89"
        secondary = t.secondary if t else "#7dcfff"
        success = t.success if t else "#9ece6a"
        border = t.variables.get('text_dim', '#3b4261') if t else "#3b4261"

        w.update(
            Text.assemble(
                ("\n", ""),
                ("\u2601  Cloud Dev Harness", f"bold {primary}"),
                ("\n\n", ""),
                ("Working Directory", dim),
                ("\n", ""),
                (f"{cwd}", secondary),
                ("\n\n", ""),
                ("Provider", dim),
                ("         Model", dim),
                ("\n", ""),
                (f"{provider}", success),
                ("         ", ""),
                (f"{model}", success),
                ("\n\n\n", ""),
                ("Type @filepath to read a file, or /command for commands", dim),
                ("\n", ""),
                ("Ctrl+F Focus  \u2502  Tab Mode  \u2502  Ctrl+P Menu  \u2502  Ctrl+Q Quit", border),
                ("\n", ""),
            )
        )
        w.display = True
        self._welcome_shown = True

    # ── Streaming ──

    def start_stream(self) -> None:
        self._hide_welcome()
        self._streaming = True
        self._stream_buffer = []
        self._char_buffer = []
        self._stream_parser = StreamParser()
        self._stream_timer = self.set_interval(0.03, self._tick_stream)
        w = self.query_one("#stream-output", Static)
        w.display = False
        w.update("")

    def add_stream_chunk(self, content: str) -> None:
        self._char_buffer.append(content)

    def _tick_stream(self) -> None:
        if not self._char_buffer:
            return
        text = "".join(self._char_buffer)
        word, remainder = self._extract_word(text)
        if word:
            self._stream_buffer.append(word)
            self._char_buffer = [remainder] if remainder else []
            self.flush_stream()

    @staticmethod
    def _extract_word(text: str) -> tuple[str, str]:
        if not text:
            return ("", "")
        for tag in ("<think>", "</think>", "</tool_call>"):
            if text.startswith(tag):
                return (tag, text[len(tag):])
        for prefix in ("<think", "<tool_call"):
            if text.startswith(prefix):
                end = text.find(">", len(prefix))
                if end != -1:
                    return (text[:end+1], text[end+1:])
        if text.startswith("```"):
            end = text.find("```", 3)
            if end != -1:
                return (text[:end+3], text[end+3:])
            return (text, "")
        if text[0] == '\n':
            return ('\n', text[1:])
        ws_end = 0
        while ws_end < len(text) and text[ws_end] in (' ', '\t'):
            ws_end += 1
        ws = text[:ws_end]
        text = text[ws_end:]
        if not text:
            return (ws, "")
        idx = len(text)
        for sep in (' ', '\n', '\t'):
            pos = text.find(sep)
            if pos != -1 and pos < idx:
                idx = pos
        return (ws + text[:idx], text[idx:])

    def flush_stream(self) -> None:
        log = self.query_one_optional("#chat-log", RichLog)
        stream = self.query_one_optional("#stream-output", Static)
        if log is None or stream is None:
            return

        t = getattr(self.app, 'tui_theme', None)

        # Process buffered chunks
        if self._stream_buffer:
            text = "".join(self._stream_buffer)
            self._stream_buffer = []
            blocks = self._stream_parser.feed(text)
            for block in blocks:
                self._render_block(log, "assistant", block)

        # Build streaming content from all pending sources
        pending_tool = self._stream_parser.get_pending_tool_call()
        pending_thinking = self._stream_parser.get_pending_thinking()
        pending_text = self._stream_parser.get_pending_text()

        has_pending = bool(
            (pending_tool and not pending_tool.get("complete"))
            or pending_thinking
            or pending_text
        )

        if not has_pending:
            stream.display = False
            return

        stream.display = True
        self.scroll_end(animate=False)
        items = []

        if pending_tool and not pending_tool.get("complete"):
            name = pending_tool.get("name", "tool")
            tid = pending_tool.get("id", "")
            inp = pending_tool.get("input", "")
            secondary = t.secondary if t else "#7dcfff"
            success = t.success if t else "#9ece6a"
            items.append(Text(f"Tool: {name}  ID: {tid}", style=secondary))
            if inp:
                items.append(Text(inp, style=f"dim {secondary}"))
            items.append(Text(""))

        if pending_thinking:
            items.append(Text("\u23f3 Thinking", style=f"dim {success}"))
            items.append(Text(pending_thinking, style=success))
            items.append(Text(""))

        if pending_text:
            items.append(RichMarkdown(pending_text, inline_code_lexer="ansi", code_theme="monokai"))

        stream.update(Group(*items) if items else "")

    def finish_stream(self) -> None:
        if self._stream_timer is not None:
            self._stream_timer.stop()
            self._stream_timer = None
        if self._char_buffer:
            self._stream_buffer.append("".join(self._char_buffer))
            self._char_buffer = []
            self.flush_stream()
        log = self.query_one_optional("#chat-log", RichLog)
        remaining = self._stream_parser.flush() if log else []
        if log and remaining:
            for block in remaining:
                self._render_block(log, "assistant", block)

        stream = self.query_one_optional("#stream-output", Static)
        if stream is not None:
            stream.display = False
            stream.update("")
        self._streaming = False
        self._stream_buffer = []

    # ── Block rendering ──

    def _render_block(self, log: RichLog, role: str, block: dict) -> None:
        btype = block.get("type", "text")
        if btype == "thinking":
            thinking = block.get("thinking", "")
            if thinking:
                self._render_thinking_rich(log, thinking)
        elif btype == "tool_use_start":
            tool_use = block.get("tool_use", {})
            self._render_tool_use_start_rich(log, tool_use.get("name", "tool"), tool_use.get("id", ""))
        elif btype == "tool_use":
            self._render_tool_use_rich(log, block.get("tool_use", {}))
        elif btype == "tool_result":
            self._render_tool_result_rich(log, block.get("tool_result", {}))
        elif btype == "code_execution":
            self._render_code_execution_rich(log, block.get("code_execution", {}))
        elif btype == "search_result":
            self._render_search_result_rich(log, block.get("search_result", {}))
        elif btype == "text":
            text = block.get("text", "")
            if text:
                self._render_text_rich(log, role, text)
        else:
            text = block.get("text", "") or str(block)
            if text:
                self._render_text_rich(log, role, text)

    def _render_thinking_rich(self, log: RichLog, thinking: str) -> None:
        log.write(Text(""))
        t = getattr(self.app, 'tui_theme', None)
        border = t.variables.get('border', '#3b4261') if t else '#3b4261'
        panel = Panel(
            Text(thinking.strip(), style=t.success if t else "#9ece6a"),
            title="\u23f3 Thinking",
            title_align="left",
            border_style=f"dim {border}",
            padding=(1, 2),
            width=None,
        )
        log.write(panel)
        log.write(Text(""))

    def _render_tool_use_start_rich(self, log: RichLog, tool_name: str, tool_id: str) -> None:
        log.write(Text(""))
        t = getattr(self.app, 'tui_theme', None)
        log.write(Text(f"Tool: {tool_name}  ID: {tool_id}  Status: Working...", style=t.secondary if t else "cyan"))

    def _render_tool_use_rich(self, log: RichLog, tool_use: dict) -> None:
        tool_name = tool_use.get("name", "tool")
        tool_id = tool_use.get("id", "")
        tool_input = tool_use.get("input", {})
        log.write(Text(""))
        t = getattr(self.app, 'tui_theme', None)
        log.write(Text(f"Tool: {tool_name}  ID: {tool_id}", style=t.secondary if t else "cyan"))
        if tool_input:
            input_str = json.dumps(tool_input, indent=2) if isinstance(tool_input, dict) else str(tool_input)
            log.write(Text(f"  {input_str}", style=f"dim {t.secondary}" if t else "dim cyan"))

    def _render_text_rich(self, log: RichLog, role: str, text: str) -> None:
        t = getattr(self.app, 'tui_theme', None)
        if role == "user":
            lines = text.split("\n")
            for i, line in enumerate(lines):
                prefix = "> " if i == 0 else "  "
                log.write(Text(prefix + line, style=f"bold {t.secondary}" if t else "bold cyan"))
            return
        rendered = _render_markdown_rich(text)
        if not rendered:
            return
        for item in rendered:
            log.write(item)

    # ── Non-streaming messages ──

    def add_message(self, role: str, content: str) -> None:
        if self._welcome_shown:
            self._hide_welcome()
        log = self.query_one_optional("#chat-log", RichLog)
        if log is None:
            return
        t = getattr(self.app, 'tui_theme', None)
        if role == "user":
            lines = content.split("\n")
            for i, line in enumerate(lines):
                prefix = "> " if i == 0 else "  "
                log.write(Text(prefix + line, style=f"bold {t.secondary}" if t else "bold cyan"))
        elif role == "assistant":
            rendered = _render_markdown_rich(content)
            if rendered:
                for item in rendered:
                    log.write(item)
            else:
                log.write(Text("(empty)", style="dim"))
        elif role == "system":
            for line in content.split("\n"):
                log.write(Text(f"  {line}", style="dim"))
        elif role == "error":
            for line in content.split("\n"):
                log.write(Text(f"  \u2716 {line}", style=f"bold {t.error}" if t else "bold red"))
        else:
            for line in content.split("\n"):
                log.write(Text(f"  {line}", style=t.foreground if t else "white"))

    def add_message_blocks(self, role: str, blocks: list[dict]) -> None:
        log = self.query_one_optional("#chat-log", RichLog)
        if log is None:
            return
        for block in blocks:
            self._render_block(log, role, block)

    def _render_tool_result_rich(self, log: RichLog, tool_result: dict) -> None:
        tool_use_id = tool_result.get("tool_use_id", "")
        content = tool_result.get("content", "")
        is_error = tool_result.get("is_error", False)
        t = getattr(self.app, 'tui_theme', None)
        err_color = t.error if t else "red"
        err_label = f" [{err_color}]ERROR[/{err_color}]" if is_error else ""
        log.write(Text(""))
        log.write(Text(f"Result  ID: {tool_use_id}{err_label}", style=t.accent if t else "magenta"))
        content_str = str(content)
        if content_str:
            log.write(Text(f"  {content_str}", style=t.secondary if t else "#7dcfff"))

    def _render_code_execution_rich(self, log: RichLog, code_result: dict) -> None:
        tool_use_id = code_result.get("tool_use_id", "")
        content = code_result.get("content", {})
        t = getattr(self.app, 'tui_theme', None)
        log.write(Text(""))
        log.write(Text(f"Code Execution  ID: {tool_use_id}", style=t.success if t else "green"))
        content_str = json.dumps(content, indent=2) if isinstance(content, dict) else str(content)
        log.write(Text(f"  {content_str}", style=t.success if t else "#9ece6a"))

    def _render_search_result_rich(self, log: RichLog, search_result: dict) -> None:
        tool_use_id = search_result.get("tool_use_id", "")
        content = search_result.get("content", {})
        t = getattr(self.app, 'tui_theme', None)
        log.write(Text(""))
        log.write(Text(f"Search Result  ID: {tool_use_id}", style=t.warning if t else "yellow"))
        content_str = json.dumps(content, indent=2) if isinstance(content, dict) else str(content)
        log.write(Text(f"  {content_str}", style=t.warning if t else "#e0af68"))
