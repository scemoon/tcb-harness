from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any
from textual.widgets import Static
from textual.containers import ScrollableContainer
from textual.app import ComposeResult
from rich.text import Text
from rich.syntax import Syntax
from rich.panel import Panel
from rich.markdown import Markdown as RichMarkdown
from rich.console import Group


class StreamParser:
    THINK_START_PAT = re.compile(r"<think[^>]*>", re.IGNORECASE)
    THINK_CODE_PAT = re.compile(r"```think\b.*?\n(.*?)```", re.DOTALL | re.IGNORECASE)
    TOOL_CALL_PAT = re.compile(r'<tool_call\s+name=["\']([^"\']+)["\']\s+id=["\']([^"\']+)["\']>(.*?)</tool_call>', re.DOTALL)
    TOOL_CALL_START_PAT = re.compile(r'<tool_call\s+name=["\']([^"\']+)["\']\s+id=["\']([^"\']+)["\']>')
    TOOL_USE_PAT = re.compile(r"```tool_use\b.*?\n(.*?)```", re.DOTALL | re.IGNORECASE)
    TOOL_RESULT_PAT = re.compile(r'<tool_result\s+tool_use_id=["\']([^"\']+)["\'](?:\s+is_error=["\']([^"\']*)["\'])?>(.*?)</tool_result>', re.DOTALL)
    TOOL_RESULT_START_PAT = re.compile(r'<tool_result\s+tool_use_id=["\']([^"\']+)["\'](?:\s+is_error=["\']([^"\']*)["\'])?>')

    def __init__(self):
        self._buffer = ""
        self._in_thinking = False
        self._thinking_content = ""
        self._in_tool_call = False
        self._tool_call_name = ""
        self._tool_call_id = ""
        self._tool_call_input = ""
        self._tool_call_complete = False
        self._in_tool_result = False
        self._tool_result_id = ""
        self._tool_result_content = ""
        self._tool_result_is_error = False

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
                        "tool_use": {"name": self._tool_call_name, "id": self._tool_call_id, "input": tool_input}
                    })
                    self._tool_call_input = ""
                    self._tool_call_name = ""
                    self._tool_call_id = ""
                else:
                    combined = self._tool_call_input + self._buffer
                    end_idx = combined.find("</tool_call>")
                    if end_idx != -1:
                        self._tool_call_input = combined[:end_idx]
                        self._buffer = combined[end_idx + len("</tool_call>"):]
                        self._in_tool_call = False
                        self._tool_call_complete = True
                        try:
                            tool_input = json.loads(self._tool_call_input) if self._tool_call_input else {}
                        except json.JSONDecodeError:
                            tool_input = {"raw": self._tool_call_input}
                        blocks.append({
                            "type": "tool_use",
                            "tool_use": {"name": self._tool_call_name, "id": self._tool_call_id, "input": tool_input}
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

            if self._in_tool_result:
                end_idx = self._buffer.find("</tool_result>")
                if end_idx != -1:
                    content_before_end = self._buffer[:end_idx]
                    self._tool_result_content += content_before_end
                    self._buffer = self._buffer[end_idx + len("</tool_result>"):]
                    self._in_tool_result = False
                    blocks.append({
                        "type": "tool_result",
                        "tool_result": {
                            "tool_use_id": self._tool_result_id,
                            "content": self._tool_result_content.strip(),
                            "is_error": self._tool_result_is_error,
                        }
                    })
                    self._tool_result_id = ""
                    self._tool_result_content = ""
                    self._tool_result_is_error = False
                else:
                    self._tool_result_content += self._buffer
                    self._buffer = ""
                    break
                continue

            if self._buffer.startswith("<tool_result") and ">" not in self._buffer:
                break

            tool_result_start = self.TOOL_RESULT_START_PAT.match(self._buffer)
            if tool_result_start:
                self._tool_result_id = tool_result_start.group(1)
                self._tool_result_is_error = tool_result_start.group(2) and tool_result_start.group(2).lower() == "true"
                self._tool_result_content = ""
                self._in_tool_result = True
                self._buffer = self._buffer[tool_result_start.end():]
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
                    "tool_use": {"name": self._tool_call_name, "id": self._tool_call_id}
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
                    if len(self._buffer) > 200:
                        blocks.append({"type": "text", "text": self._buffer})
                        self._buffer = ""
                    else:
                        break
            else:
                if len(self._buffer) > 200:
                    blocks.append({"type": "text", "text": self._buffer})
                    self._buffer = ""
                else:
                    break

        return blocks

    def get_pending_text(self) -> str:
        if not self._in_thinking and not self._in_tool_call and not self._in_tool_result and self._buffer:
            return self._buffer
        return ""

    def get_pending_thinking(self) -> str:
        if self._in_thinking:
            return self._thinking_content
        return ""

    def get_pending_tool_call(self) -> dict | None:
        if self._in_tool_call:
            return {
                "name": self._tool_call_name,
                "id": self._tool_call_id,
                "input": self._tool_call_input,
                "complete": self._tool_call_complete,
            }
        return None

    def get_pending_tool_result(self) -> dict | None:
        if self._in_tool_result:
            return {
                "tool_use_id": self._tool_result_id,
                "content": self._tool_result_content,
                "is_error": self._tool_result_is_error,
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
                "tool_use": {"name": self._tool_call_name, "id": self._tool_call_id, "input": tool_input}
            })
        if self._in_tool_result and self._tool_result_content.strip():
            blocks.append({
                "type": "tool_result",
                "tool_result": {
                    "tool_use_id": self._tool_result_id,
                    "content": self._tool_result_content.strip(),
                    "is_error": self._tool_result_is_error,
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
        self._in_tool_result = False
        self._tool_result_id = ""
        self._tool_result_content = ""
        self._tool_result_is_error = False
        return blocks


def _strip_think_blocks(text: str) -> str:
    for pat in (
        re.compile(r"<think[^>]*>(.*?)</think>", re.DOTALL | re.IGNORECASE),
        re.compile(r"```think\b.*?```", re.DOTALL | re.IGNORECASE),
    ):
        text = pat.sub("", text)
    return text.strip()


def _render_markdown_rich(text: str) -> list[Any]:
    from rich.markdown import Markdown

    output: list[Any] = []
    last_end = 0
    code_block_pat = re.compile(r"```(\w*)\n?(.*?)```", re.DOTALL)

    for match in code_block_pat.finditer(text):
        before = text[last_end: match.start()]
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


def _render_blocks_to_renderables(blocks: list[dict], theme: Any) -> list[Any]:
    renderables: list[Any] = []
    for block in blocks:
        btype = block.get("type", "text")
        if btype == "thinking":
            content = block.get("thinking", "")
            if content:
                border = theme.variables.get('border', '#3b4261') if theme else '#3b4261'
                panel = Panel(
                    Text(content.strip(), style=theme.success if theme else "#9ece6a"),
                    title="\u23f3 Thinking",
                    title_align="left",
                    border_style=f"dim {border}",
                    padding=(1, 2),
                )
                renderables.append(Text(""))
                renderables.append(panel)
                renderables.append(Text(""))
        elif btype == "tool_use":
            tool_use = block.get("tool_use", {})
            tool_name = tool_use.get("name", "tool")
            tool_input = tool_use.get("input", {})
            border = theme.variables.get('border', '#3b4261') if theme else '#3b4261'
            input_str = ""
            if tool_input:
                input_str = json.dumps(tool_input, indent=2) if isinstance(tool_input, dict) else str(tool_input)
            if input_str:
                lang = "bash" if tool_name.lower() in ("bash", "exec", "shell") else "json"
                syntax = Syntax(input_str, lang, theme="monokai", word_wrap=True, padding=(0, 1))
                panel = Panel(syntax, title=f" {tool_name} ", title_align="left", border_style=f"dim {border}", padding=(0, 0))
            else:
                panel = Panel(
                    Text(f"ID: {tool_use.get('id', '')}", style=f"dim {theme.secondary}" if theme else "dim cyan"),
                    title=f" {tool_name} ", title_align="left", border_style=f"dim {border}", padding=(0, 1),
                )
            renderables.append(Text(""))
            renderables.append(panel)
        elif btype == "tool_result":
            tool_result = block.get("tool_result", {})
            content = tool_result.get("content", "")
            is_error = tool_result.get("is_error", False)
            border = theme.variables.get('border', '#3b4261') if theme else '#3b4261'
            err_color = theme.error if theme else "red"
            content_str = str(content)
            max_preview = 500
            truncated = len(content_str) > max_preview
            preview = content_str[:max_preview] if truncated else content_str
            if is_error:
                panel = Panel(Text(preview.strip(), style=err_color), title=" Error ", title_align="left", border_style=err_color, padding=(0, 1))
            else:
                syntax = None
                if preview.strip().startswith("{") or preview.strip().startswith("["):
                    try:
                        parsed = json.loads(preview)
                        formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
                        syntax = Syntax(formatted, "json", theme="monokai", word_wrap=True, padding=(0, 1))
                    except (json.JSONDecodeError, ValueError):
                        pass
                if syntax is None:
                    lines = preview.strip().split("\n")
                    if len(lines) >= 2 and any(l.startswith("#") or l.startswith("import ") or l.startswith("from ") for l in lines[:5]):
                        syntax = Syntax(preview.strip(), "python", theme="monokai", word_wrap=True, padding=(0, 1))
                    elif any(l.startswith("<") and l.endswith(">") for l in lines[:3]):
                        syntax = Syntax(preview.strip(), "html", theme="monokai", word_wrap=True, padding=(0, 1))
                if syntax:
                    panel = Panel(syntax, title=" Result ", title_align="left", border_style=f"dim {border}", padding=(0, 0))
                else:
                    panel = Panel(
                        Text(preview.strip() if preview.strip() else "(empty)", style=f"dim {theme.secondary}" if theme else "dim #7dcfff"),
                        title=" Result ", title_align="left", border_style=f"dim {border}", padding=(0, 1),
                    )
            renderables.append(Text(""))
            renderables.append(panel)
            if truncated:
                renderables.append(Text(f"  ... ({len(content_str)} chars total, showing first {max_preview})", style="dim"))
        elif btype == "text":
            text = block.get("text", "")
            if text:
                md_rendered = _render_markdown_rich(text)
                renderables.extend(md_rendered)
    return renderables


class ChatPanel(ScrollableContainer):
    """Main chat area with a single scrollable message container."""

    DEFAULT_CSS = """
    ChatPanel {
        height: 100%;
        overflow-y: auto;
        overflow-x: hidden;
    }
    ChatPanel > #welcome {
        display: none;
    }
    ChatPanel > #stream-output {
        display: none;
    }
    ChatPanel.-streaming > #stream-output {
        display: block;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._renderables: list[Any] = []
        self._streaming = False
        self._stream_parser = StreamParser()
        self._welcome_shown = False
        self._emitted_ids: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Static(id="welcome")
        yield Static(id="chat-log")

    def on_mount(self) -> None:
        app = self.app
        session = getattr(app, "_session", None)
        if session:
            messages = session.messages or []
            if not messages:
                from cdh.agent.session import AgentSession
                agent_s = AgentSession(session.id)
                if agent_s.load():
                    messages = agent_s.messages
            if not messages:
                self._show_welcome()
        else:
            self._show_welcome()

    def _hide_welcome(self) -> None:
        self._welcome_shown = False
        w = self.query_one_optional("#welcome", Static)
        if w is not None:
            w.display = False

    def _show_welcome(self) -> None:
        w = self.query_one_optional("#welcome", Static)
        if w is None:
            return
        app = self.app
        t = getattr(app, 'tui_theme', None)
        ws = str(getattr(app, 'workspace', Path.cwd()))
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
                ("Workspace", dim),
                ("\n", ""),
                (f"{ws}", secondary),
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

    def _scroll_to_bottom(self) -> None:
        self.call_after_refresh(self.scroll_end, animate=False)

    # ── Streaming ──

    def start_stream(self) -> None:
        self._emitted_ids.clear()
        self._hide_welcome()
        self._streaming = True
        self._stream_parser = StreamParser()
        self._update_stream_widget()

    def _get_stream_widget(self) -> Static:
        so = self.query_one_optional("#stream-output", Static)
        if so is None:
            so = Static(id="stream-output")
            self.mount(so)
            so.display = True
        else:
            so.display = True
        return so

    def _remove_stream_widget(self) -> None:
        so = self.query_one_optional("#stream-output", Static)
        if so is not None:
            so.display = False
            so.update("")

    def _update_stream_widget(self) -> None:
        so = self.query_one_optional("#stream-output", Static)
        if so is None:
            return
        pending_tool = self._stream_parser.get_pending_tool_call()
        pending_thinking = self._stream_parser.get_pending_thinking()
        pending_text = self._stream_parser.get_pending_text()
        pending_tool_result = self._stream_parser.get_pending_tool_result()
        t = getattr(self.app, 'tui_theme', None)

        items = []
        if pending_tool and not pending_tool.get("complete"):
            name = pending_tool.get("name", "tool")
            tid = pending_tool.get("id", "")
            items.append(Text(f"Tool: {name}  ID: {tid}", style=t.secondary if t else "#7dcfff"))
            inp = pending_tool.get("input", "")
            if inp:
                inp_str = json.dumps(inp, indent=2) if isinstance(inp, dict) else str(inp)
                items.append(Text(str(inp_str), style=f"dim {t.secondary}" if t else "dim #7dcfff"))
            items.append(Text(""))

        if pending_thinking:
            items.append(Text("\u23f3 Thinking", style=f"dim {t.success}" if t else "dim #9ece6a"))
            items.append(Text(pending_thinking, style=t.success if t else "#9ece6a"))
            items.append(Text(""))

        if pending_tool_result:
            tid = pending_tool_result.get("tool_use_id", "")
            content = pending_tool_result.get("content", "")
            is_error = pending_tool_result.get("is_error", False)
            err_color = t.error if t else "red"
            label = f"Result ID: {tid}"
            label += f" [{err_color}]ERROR[/{err_color}]" if is_error else ""
            items.append(Text(label, style=t.accent if t else "magenta"))
            if content:
                items.append(Text(str(content), style=t.secondary if t else "#7dcfff"))
            items.append(Text(""))

        if pending_text and pending_text.strip():
            try:
                items.append(RichMarkdown(pending_text, inline_code_lexer="ansi", code_theme="monokai"))
            except Exception:
                items.append(Text(pending_text))

        if items:
            so.update(Group(*items))
            self._scroll_to_bottom()
        else:
            so.update("")

    def add_stream_chunk(self, content: str) -> None:
        if not self._streaming:
            return
        blocks = self._stream_parser.feed(content)
        for block in blocks:
            self._append_block(block)
        self._update_stream_widget()
        self._scroll_to_bottom()

    def finish_stream(self) -> None:
        self._streaming = False
        remaining = self._stream_parser.flush()
        for block in remaining:
            self._append_block(block)
        self._remove_stream_widget()
        self._scroll_to_bottom()

    # ── Block appending to chat-log ──

    def _append_block(self, block: dict) -> None:
        btype = block.get("type", "text")
        if btype == "thinking":
            content = block.get("thinking", "")
            key = f"think:{content[:50]}:{len(content)}"
            if key in self._emitted_ids:
                return
            self._emitted_ids.add(key)
            if content:
                t = getattr(self.app, 'tui_theme', None)
                border = t.variables.get('border', '#3b4261') if t else '#3b4261'
                panel = Panel(
                    Text(content.strip(), style=t.success if t else "#9ece6a"),
                    title="\u23f3 Thinking",
                    title_align="left",
                    border_style=f"dim {border}",
                    padding=(1, 2),
                )
                self._renderables.append(Text(""))
                self._renderables.append(panel)
                self._renderables.append(Text(""))
                self._refresh_chat()
        elif btype == "tool_use":
            self._render_tool_use_rich(block.get("tool_use", {}))
        elif btype == "tool_result":
            self._render_tool_result_rich(block.get("tool_result", {}))
        elif btype == "text":
            text = block.get("text", "")
            if text:
                self._append_text("assistant", text)
        elif btype == "tool_use_start":
            tool_use = block.get("tool_use", {})
            t = getattr(self.app, 'tui_theme', None)
            self._renderables.append(Text(""))
            self._renderables.append(Text(
                f"Tool: {tool_use.get('name', 'tool')}  ID: {tool_use.get('id', '')}  Status: Working...",
                style=t.secondary if t else "cyan"
            ))
            self._refresh_chat()

    def _refresh_chat(self) -> None:
        log = self.query_one_optional("#chat-log", Static)
        if log is not None:
            log.update(Group(*self._renderables) if self._renderables else "")

    def _append_text(self, role: str, text: str) -> None:
        t = getattr(self.app, 'tui_theme', None)
        if role == "user":
            lines = text.split("\n")
            for i, line in enumerate(lines):
                prefix = "> " if i == 0 else "  "
                self._renderables.append(Text(prefix + line, style=f"bold {t.secondary}" if t else "bold cyan"))
            self._refresh_chat()
            return
        rendered = _render_markdown_rich(text)
        if not rendered:
            return
        for item in rendered:
            self._renderables.append(item)
        self._refresh_chat()

    def _render_tool_use_rich(self, tool_use: dict) -> None:
        tool_name = tool_use.get("name", "tool")
        tool_input = tool_use.get("input", {})
        t = getattr(self.app, 'tui_theme', None)
        border = t.variables.get('border', '#3b4261') if t else '#3b4261'
        input_str = ""
        if tool_input:
            input_str = json.dumps(tool_input, indent=2) if isinstance(tool_input, dict) else str(tool_input)
        if input_str:
            lang = "bash" if tool_name.lower() in ("bash", "exec", "shell") else "json"
            syntax = Syntax(input_str, lang, theme="monokai", word_wrap=True, padding=(0, 1))
            panel = Panel(syntax, title=f" {tool_name} ", title_align="left", border_style=f"dim {border}", padding=(0, 0))
        else:
            panel = Panel(
                Text(f"ID: {tool_use.get('id', '')}", style=f"dim {t.secondary}" if t else "dim cyan"),
                title=f" {tool_name} ", title_align="left", border_style=f"dim {border}", padding=(0, 1),
            )
        self._renderables.append(Text(""))
        self._renderables.append(panel)
        self._refresh_chat()

    def _render_tool_result_rich(self, tool_result: dict) -> None:
        content = tool_result.get("content", "")
        is_error = tool_result.get("is_error", False)
        t = getattr(self.app, 'tui_theme', None)
        border = t.variables.get('border', '#3b4261') if t else '#3b4261'
        err_color = t.error if t else "red"
        content_str = str(content)
        max_preview = 500
        truncated = len(content_str) > max_preview
        preview = content_str[:max_preview] if truncated else content_str
        if is_error:
            panel = Panel(Text(preview.strip(), style=err_color), title=" Error ", title_align="left", border_style=err_color, padding=(0, 1))
        else:
            syntax = None
            if preview.strip().startswith("{") or preview.strip().startswith("["):
                try:
                    parsed = json.loads(preview)
                    formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
                    syntax = Syntax(formatted, "json", theme="monokai", word_wrap=True, padding=(0, 1))
                except (json.JSONDecodeError, ValueError):
                    pass
            if syntax is None:
                lines = preview.strip().split("\n")
                if len(lines) >= 2 and any(l.startswith("#") or l.startswith("import ") or l.startswith("from ") for l in lines[:5]):
                    syntax = Syntax(preview.strip(), "python", theme="monokai", word_wrap=True, padding=(0, 1))
                elif any(l.startswith("<") and l.endswith(">") for l in lines[:3]):
                    syntax = Syntax(preview.strip(), "html", theme="monokai", word_wrap=True, padding=(0, 1))
            if syntax:
                panel = Panel(syntax, title=" Result ", title_align="left", border_style=f"dim {border}", padding=(0, 0))
            else:
                panel = Panel(
                    Text(preview.strip() if preview.strip() else "(empty)", style=f"dim {t.secondary}" if t else "dim #7dcfff"),
                    title=" Result ", title_align="left", border_style=f"dim {border}", padding=(0, 1),
                )
        self._renderables.append(Text(""))
        self._renderables.append(panel)
        if truncated:
            self._renderables.append(Text(f"  ... ({len(content_str)} chars total, showing first {max_preview})", style="dim"))
        self._refresh_chat()

    # ── Non-streaming messages ──

    def add_message(self, role: str, content: str) -> None:
        if self._welcome_shown:
            self._hide_welcome()
        t = getattr(self.app, 'tui_theme', None)
        if role == "user":
            lines = content.split("\n")
            for i, line in enumerate(lines):
                prefix = "> " if i == 0 else "  "
                self._renderables.append(Text(prefix + line, style=f"bold {t.secondary}" if t else "bold cyan"))
        elif role == "assistant":
            rendered = _render_markdown_rich(content)
            if rendered:
                for item in rendered:
                    self._renderables.append(item)
            else:
                self._renderables.append(Text("(empty)", style="dim"))
        elif role == "system":
            for line in content.split("\n"):
                self._renderables.append(Text(f"  {line}", style="dim"))
        elif role == "error":
            for line in content.split("\n"):
                self._renderables.append(Text(f"  \u2716 {line}", style=f"bold {t.error}" if t else "bold red"))
        else:
            for line in content.split("\n"):
                self._renderables.append(Text(f"  {line}", style=t.foreground if t else "white"))
        self._refresh_chat()
        self._scroll_to_bottom()

    def add_message_blocks(self, role: str, blocks: list[dict]) -> None:
        for block in blocks:
            self._append_block(block)
        self._scroll_to_bottom()

    def clear_chat(self) -> None:
        self._renderables = []
        self._streaming = False
        self._stream_parser = StreamParser()
        self._welcome_shown = False
        self._remove_stream_widget()
        self._refresh_chat()

    def load_messages(self, messages: list[dict]) -> None:
        self._hide_welcome()
        self.clear_chat()
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                self.add_message(role, content)
        self._scroll_to_bottom()
