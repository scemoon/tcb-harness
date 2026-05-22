"""Chat panel with professional message rendering.

Inspired by DeepSeek-TUI layout:
- Collapsible thinking blocks with `[Thinking]` toggle
- Tool calls with status lifecycle (⏳ executing / ✓ done / ✗ failed)
- Typed tool results: file read/write/edit, bash output, web results
- Sub-agent lifecycle with streaming progress
- Diff display for file edits
- Terminal-style output for bash commands
"""

from __future__ import annotations

import re
import json
import difflib
from pathlib import Path
from typing import Any, Optional

from textual.widgets import Static
from textual.containers import ScrollableContainer
from textual.app import ComposeResult
from rich.text import Text
from rich.syntax import Syntax
from rich.panel import Panel
from rich.markdown import Markdown as RichMarkdown
from rich.markdown import Markdown
from rich.console import Group
from rich.padding import Padding

from cdh.models.messages import (
    ThinkBlock, ToolCall, ToolResult, SubAgentBlock, TextBlock,
    ToolCategory, LifecycleStatus, BlockType, block_from_dict,
    get_tool_category, StreamEvent,
)


# ── Status icons ──

STATUS_ICONS = {
    LifecycleStatus.PENDING:   "○",
    LifecycleStatus.RUNNING:   "◐",
    LifecycleStatus.COMPLETE:  "◉",
    LifecycleStatus.FAILED:    "✗",
    LifecycleStatus.CANCELLED: "⊘",
}

TOOL_ICONS = {
    ToolCategory.FILE_READ:    "📄",
    ToolCategory.FILE_WRITE:   "✎",
    ToolCategory.FILE_EDIT:    "✐",
    ToolCategory.FILE_LIST:    "📁",
    ToolCategory.FILE_GLOB:    "🔍",
    ToolCategory.FILE_GREP:    "🔎",
    ToolCategory.BASH:          "⚡",
    ToolCategory.WEB_FETCH:     "🌐",
    ToolCategory.WEB_SEARCH:    "🔎",
    ToolCategory.TASK:          "🤖",
    ToolCategory.TASK_MGMT:     "📋",
    ToolCategory.INTERACTION:   "💬",
    ToolCategory.UNKNOWN:       "🔧",
}

CATEGORY_LABELS = {
    ToolCategory.FILE_READ:    "Read",
    ToolCategory.FILE_WRITE:   "Write",
    ToolCategory.FILE_EDIT:    "Edit",
    ToolCategory.FILE_LIST:    "List",
    ToolCategory.FILE_GLOB:    "Glob",
    ToolCategory.FILE_GREP:    "Grep",
    ToolCategory.BASH:          "Bash",
    ToolCategory.WEB_FETCH:     "WebFetch",
    ToolCategory.WEB_SEARCH:    "WebSearch",
    ToolCategory.TASK:          "SubAgent",
    ToolCategory.TASK_MGMT:     "TaskMgmt",
    ToolCategory.INTERACTION:   "AskUser",
    ToolCategory.UNKNOWN:       "Tool",
}


# ── StreamParser ──

class StreamParser:
    """Evolved stream parser that produces typed blocks.

    Handles:
    - <think>...</think> → ThinkBlock
    - <tool_call name="X" id="Y">...</tool_call> → ToolCall
    - <tool_result tool_use_id="X">...</tool_result> → ToolResult
    - <ask_user tool_use_id="X" action="Y">...</ask_user> → AskUserBlock
    - ```think ... ``` → ThinkBlock
    - ```tool_use ... ``` → ToolCall
    """

    THINK_START_PAT = re.compile(r"<think[^>]*>", re.IGNORECASE)
    THINK_CODE_PAT = re.compile(r"```think\b.*?\n(.*?)```", re.DOTALL | re.IGNORECASE)
    TOOL_CALL_PAT = re.compile(r'<tool_call\s+name=["\']([^"\']+)["\']\s+id=["\']([^"\']+)["\']>(.*?)</tool_call>', re.DOTALL)
    TOOL_CALL_START_PAT = re.compile(r'<tool_call\s+name=["\']([^"\']+)["\']\s+id=["\']([^"\']+)["\']>')
    TOOL_USE_PAT = re.compile(r"```tool_use\b.*?\n(.*?)```", re.DOTALL | re.IGNORECASE)
    TOOL_RESULT_PAT = re.compile(r'<tool_result\s+tool_use_id=["\']([^"\']+)["\'](?:\s+is_error=["\']([^"\']*)["\'])?(?:\s+category=["\']([^"\']*)["\'])?>(.*?)</tool_result>', re.DOTALL)
    TOOL_RESULT_START_PAT = re.compile(r'<tool_result\s+tool_use_id=["\']([^"\']+)["\'](?:\s+is_error=["\']([^"\']*)["\'])?(?:\s+category=["\']([^"\']*)["\'])?>')
    ASK_USER_PAT = re.compile(r'<ask_user\s+tool_use_id=["\']([^"\']+)["\']\s+action=["\']([^"\']*)["\'](?:\s+category=["\']([^"\']*)["\'])?>(.*?)</ask_user>', re.DOTALL)
    ASK_USER_START_PAT = re.compile(r'<ask_user\s+tool_use_id=["\']([^"\']+)["\']\s+action=["\']([^"\']*)["\'](?:\s+category=["\']([^"\']*)["\'])?>')

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
        self._tool_result_category = "unknown"
        self._in_ask_user = False
        self._ask_user_id = ""
        self._ask_user_action = ""
        self._ask_user_category = "interaction"
        self._ask_user_content = ""

    def feed(self, text: str) -> list:
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
                        blocks.append(ThinkBlock(content=self._thinking_content.strip()).to_dict())
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
                    blocks.append(ToolCall(
                        id=self._tool_call_id,
                        name=self._tool_call_name,
                        arguments=tool_input,
                        status=LifecycleStatus.COMPLETE,
                        category=get_tool_category(self._tool_call_name),
                    ).to_dict())
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
                        blocks.append(ToolCall(
                            id=self._tool_call_id,
                            name=self._tool_call_name,
                            arguments=tool_input,
                            status=LifecycleStatus.COMPLETE,
                            category=get_tool_category(self._tool_call_name),
                        ).to_dict())
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
                blocks.append(ThinkBlock(content=think_code_match.group(1).strip()).to_dict())
                self._buffer = self._buffer[think_code_match.end():]
                continue

            tool_match = self.TOOL_USE_PAT.match(self._buffer)
            if tool_match:
                try:
                    tool_data = json.loads(tool_match.group(1))
                    blocks.append(ToolCall(
                        name=tool_data.get("name", "tool"),
                        arguments=tool_data.get("input", {}),
                        status=LifecycleStatus.COMPLETE,
                        category=get_tool_category(tool_data.get("name", "")),
                    ).to_dict())
                except json.JSONDecodeError:
                    blocks.append(TextBlock(content=tool_match.group(0)).to_dict())
                self._buffer = self._buffer[tool_match.end():]
                continue

            if self._in_tool_result:
                end_idx = self._buffer.find("</tool_result>")
                if end_idx != -1:
                    content_before_end = self._buffer[:end_idx]
                    self._tool_result_content += content_before_end
                    self._buffer = self._buffer[end_idx + len("</tool_result>"):]
                    self._in_tool_result = False
                    try:
                        cat = ToolCategory(self._tool_result_category)
                    except ValueError:
                        cat = ToolCategory.UNKNOWN
                    blocks.append(ToolResult(
                        tool_use_id=self._tool_result_id,
                        content=self._tool_result_content.strip(),
                        is_error=self._tool_result_is_error,
                        category=cat,
                    ).to_dict())
                    self._tool_result_id = ""
                    self._tool_result_content = ""
                    self._tool_result_is_error = False
                    self._tool_result_category = "unknown"
                else:
                    self._tool_result_content += self._buffer
                    self._buffer = ""
                    break
                continue

            if self._buffer.startswith("<tool_result") and ">" not in self._buffer:
                break

            # ── ask_user block handling (approval requests) ──
            if self._in_ask_user:
                end_idx = self._buffer.find("</ask_user>")
                if end_idx != -1:
                    self._ask_user_content += self._buffer[:end_idx]
                    self._buffer = self._buffer[end_idx + len("</ask_user>"):]
                    self._in_ask_user = False
                    # Parse the JSON content
                    try:
                        ask_data = json.loads(self._ask_user_content.strip())
                    except (json.JSONDecodeError, ValueError):
                        ask_data = {"question": self._ask_user_content.strip()}
                    blocks.append({
                        "type": "ask_user",
                        "ask_user": {
                            "tool_use_id": self._ask_user_id,
                            "action": self._ask_user_action,
                            "category": self._ask_user_category,
                            "question": ask_data.get("question", ""),
                            "context": ask_data.get("context", ""),
                            "action_type": ask_data.get("action_type", ""),
                            "path": ask_data.get("path", ""),
                            "command": ask_data.get("command", ""),
                        }
                    })
                    self._ask_user_id = ""
                    self._ask_user_action = ""
                    self._ask_user_category = "interaction"
                    self._ask_user_content = ""
                else:
                    self._ask_user_content += self._buffer
                    self._buffer = ""
                    break
                continue

            if self._buffer.startswith("<ask_user") and ">" not in self._buffer:
                break

            ask_user_start = self.ASK_USER_START_PAT.match(self._buffer)
            if ask_user_start:
                self._ask_user_id = ask_user_start.group(1)
                self._ask_user_action = ask_user_start.group(2) or ""
                self._ask_user_category = ask_user_start.group(3) or "interaction"
                self._ask_user_content = ""
                self._in_ask_user = True
                self._buffer = self._buffer[ask_user_start.end():]
                continue

            tool_result_start = self.TOOL_RESULT_START_PAT.match(self._buffer)
            if tool_result_start:
                self._tool_result_id = tool_result_start.group(1)
                self._tool_result_is_error = tool_result_start.group(2) and tool_result_start.group(2).lower() == "true"
                self._tool_result_category = tool_result_start.group(3) or "unknown"
                self._tool_result_content = ""
                self._in_tool_result = True
                self._buffer = self._buffer[tool_result_start.end():]
                continue

            # Guard against partial <tool_call tag without closing >
            if self._buffer.startswith("<tool_call") and ">" not in self._buffer:
                break

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
                        "category": get_tool_category(self._tool_call_name).value,
                    }
                })
                continue

            text_end = len(self._buffer)
            next_think = self.THINK_START_PAT.search(self._buffer)
            next_tool = self.TOOL_USE_PAT.search(self._buffer)
            next_tool_call = self.TOOL_CALL_PAT.search(self._buffer)
            next_tool_call_start = self.TOOL_CALL_START_PAT.search(self._buffer)
            next_ask_user = self.ASK_USER_START_PAT.search(self._buffer)

            earliest = text_end
            for m in [next_think, next_tool, next_tool_call, next_tool_call_start, next_ask_user]:
                if m and m.start() < earliest:
                    earliest = m.start()

            if earliest > 0:
                if earliest < text_end:
                    blocks.append({"type": "text", "text": self._buffer[:earliest]})
                    self._buffer = self._buffer[earliest:]
                else:
                    # Quick flush: yield text promptly for smooth streaming (ai-sdk-python style)
                    if len(self._buffer) > 10:
                        blocks.append({"type": "text", "text": self._buffer})
                        self._buffer = ""
                    else:
                        break
            else:
                if len(self._buffer) > 10:
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
                "category": get_tool_category(self._tool_call_name).value,
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

    def flush(self) -> list:
        blocks = []
        if self._in_thinking and self._thinking_content.strip():
            blocks.append(ThinkBlock(content=self._thinking_content.strip()).to_dict())
        if self._in_tool_call:
            try:
                tool_input = json.loads(self._tool_call_input) if self._tool_call_input else {}
            except json.JSONDecodeError:
                tool_input = {"raw": self._tool_call_input}
            blocks.append(ToolCall(
                id=self._tool_call_id,
                name=self._tool_call_name,
                arguments=tool_input,
                status=LifecycleStatus.COMPLETE,
                category=get_tool_category(self._tool_call_name),
            ).to_dict())
        if self._in_tool_result and self._tool_result_content.strip():
            try:
                cat = ToolCategory(self._tool_result_category)
            except ValueError:
                cat = ToolCategory.UNKNOWN
            blocks.append(ToolResult(
                tool_use_id=self._tool_result_id,
                content=self._tool_result_content.strip(),
                is_error=self._tool_result_is_error,
                category=cat,
            ).to_dict())
        if self._buffer.strip():
            blocks.append({"type": "text", "text": self._buffer})
        self._reset_state()
        return blocks

    def _reset_state(self) -> None:
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


# ── Utility functions moved from old chat.py ──

def _strip_think_blocks(text: str) -> str:
    for pat in (
        re.compile(r"<think[^>]*>(.*?)</think>", re.DOTALL | re.IGNORECASE),
        re.compile(r"```think\b.*?```", re.DOTALL | re.IGNORECASE),
    ):
        text = pat.sub("", text)
    return text.strip()


def _render_markdown_rich(text: str) -> list[Any]:
    """Render markdown with proper code block handling."""
    output: list[Any] = []
    last_end = 0
    code_block_pat = re.compile(r"```(\w*)\n?(.*?)```", re.DOTALL)

    for match in code_block_pat.finditer(text):
        before = text[last_end: match.start()]
        if before.strip():
            stripped = _strip_think_blocks(before)
            if stripped.strip():
                md = Markdown(stripped, inline_code_lexer="ansi", code_theme="monokai")
                output.append(Padding(md, (0, 2)))
        lang = match.group(1) or "ansi"
        code = match.group(2)
        syntax = Syntax(code, lang if lang else "ansi", theme="monokai", word_wrap=True, padding=(1, 2))
        output.append(Padding(syntax, (0, 2)))
        last_end = match.end()

    remaining = text[last_end:]
    if remaining.strip():
        stripped = _strip_think_blocks(remaining)
        if stripped.strip():
            md = Markdown(stripped, inline_code_lexer="ansi", code_theme="monokai")
            output.append(Padding(md, (0, 2)))

    return output


def _detect_language_from_path(path: str) -> str:
    """Detect language from file extension for syntax highlighting."""
    ext_map = {
        ".py": "python", ".pyi": "python",
        ".js": "javascript", ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript",
        ".json": "json", ".yaml": "yaml", ".yml": "yaml",
        ".html": "html", ".css": "css", ".scss": "scss",
        ".rs": "rust", ".go": "go", ".java": "java",
        ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
        ".sh": "bash", ".bash": "bash", ".zsh": "bash",
        ".md": "markdown", ".toml": "toml", ".ini": "ini",
        ".sql": "sql", ".dockerfile": "dockerfile", ".makefile": "makefile",
        ".xml": "xml", ".svg": "xml",
        ".rb": "ruby", ".php": "php", ".swift": "swift", ".kt": "kotlin",
        ".lua": "lua", ".vim": "vim",
    }
    suffix = Path(path).suffix.lower()
    if suffix in ext_map:
        return ext_map[suffix]
    basename = Path(path).name.lower()
    if basename in ext_map:
        return ext_map[basename]
    if basename == "dockerfile":
        return "dockerfile"
    return "text"


def _detect_language_from_content(lines: list[str]) -> str:
    """Detect language from content heuristics."""
    if any(l.startswith(("import ", "from ", "def ", "class ", "@", "#!")) for l in lines[:15]):
        return "python"
    if any(l.startswith(("const ", "function ", "import ", "export ", "let ", "var ", "interface ")) for l in lines[:10]):
        return "typescript"
    if any(("<" in l and ">" in l) or "<!DOCTYPE" in l.upper() for l in lines[:5]):
        return "html"
    if any(l.startswith(("package ", "import (", "func ")) for l in lines[:10]):
        return "go"
    if any(l.startswith(("use ", "fn ", "pub ", "mod ")) for l in lines[:10]):
        return "rust"
    return "text"


def _generate_diff(old: str, new: str, filepath: str = "") -> list[str]:
    """Generate a unified diff for file edit display."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{filepath}" if filepath else "a/original",
        tofile=f"b/{filepath}" if filepath else "b/modified",
    ))
    return diff


def _diff_summary(diff_lines: list[str], filepath: str = "") -> str:
    """deepseek-tui style: 'summary: 1 file, +5 -3, 2 hunks'"""
    added = 0
    deleted = 0
    hunks = 0
    for line in diff_lines:
        if line.startswith("@@"):
            hunks += 1
        elif line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            deleted += 1
    if hunks == 0:
        return ""
    return f"summary: 1 file, +{added} -{deleted}, {hunks} hunk{'s' if hunks != 1 else ''}"


# ── Bash command patterns: detect file ops via cat/heredoc ──

# cat > path <<'EOF'\n...\nEOF  -- write/create
# cat >> path <<'EOF'\n...\nEOF  -- append
# cat path  -- read
_CAT_WRITE_PAT = re.compile(
    r"cat\s+(?P<redirect>>>?)\s*(?P<path>\S+)\s+<<\s*'?(?P<tag>EOF|NONCE)'?\s*\n\s*(?P<content>.*?)\n\s*'?(?P=tag)'?\s*$",
    re.DOTALL,
)
# cat path (read)
_CAT_READ_PAT = re.compile(r"^cat\s+(?P<path>\S+)\s*$")
# echo / printf write (not implemented in renderer, reserved for future)
_CAT_ECHO_PAT = re.compile(
    r"(?:echo|printf)\s+(?:(?P<quote>['\"])?(?P<content>.*?)(?P=quote)|.*?)\s*(?:>>?>?)\s*(?P<path>\S+)",
    re.DOTALL,
)


def _parse_cat_heredoc(cmd: str) -> dict | None:
    """Detect file operations hidden in Bash commands.

    Returns None if not a recognizable file op; otherwise returns:
    {
        "type": "write" | "append" | "read",
        "path": str,
        "content": str | None,
    }
    """
    if not cmd:
        return None

    # Write/append:  cat > file <<'EOF'  ... content ...  EOF
    m = _CAT_WRITE_PAT.match(cmd.strip())
    if m:
        redirect = m.group("redirect")
        return {
            "type": "append" if redirect == ">>" else "write",
            "path": m.group("path").strip(),
            "content": m.group("content").strip(),
        }

    # Read:  cat path
    m = _CAT_READ_PAT.match(cmd.strip())
    if m:
        p = m.group("path").strip()
        # Filter out paths that are obviously not file reads (e.g. *.py, /dev/null)
        if not any(c in p for c in ("*", "?", "/dev/")):
            return {"type": "read", "path": p, "content": None}

    return None


# ── ChatPanel ──

class ChatPanel(ScrollableContainer):
    """Main chat area with professional message rendering."""

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
        # Track tool calls for result pairing: tool_id -> {name, arguments, category}
        self._tool_call_data: dict[str, dict] = {}
        # Collapsed thinking blocks
        self._collapsed_thinking: set[str] = set()
        self._collapsed_tools: set[str] = set()
        # Track whether we've shown the assistant label in the current stream
        self._assistant_label_shown: bool = False
        # OpenCode-style: accumulate raw text during streaming, render once at end
        self._stream_raw_text: str = ""
        # Claude Code-style incremental segment freezing (shouldRenderStatically)
        self._frozen_up_to: int = 0   # Index in _renderables frozen so far
        self._seg_counter: int = 0    # Widget ID counter for frozen segments

    def compose(self) -> ComposeResult:
        yield Static(id="welcome")
        yield Static(id="chat-log")

    # ── Helpers ──

    def _theme(self):
        return getattr(self.app, 'tui_theme', None)

    def _get_color(self, key: str, default: str) -> str:
        t = self._theme()
        if t:
            mapped = {
                "primary": t.primary,
                "secondary": t.secondary,
                "success": t.success,
                "warning": t.warning,
                "error": t.error,
                "accent": t.accent,
                "foreground": t.foreground,
                "border": t.variables.get('border', '#3b4261'),
                "dim": t.variables.get('text_dim', '#565f89'),
                "bright": t.variables.get('text_bright', '#a9b1d6'),
            }
            return mapped.get(key, default)
        return default

    def _make_panel(self, content: Any, title: str, border_style: str = None,
                     padding: tuple = (1, 2), title_align: str = "left",
                     is_error: bool = False) -> Panel:
        """Create a consistent Panel with theme-aware styling.

        All tool panels should use this factory to ensure uniform look.
        """
        border = self._get_color('border', '#3b4261')
        if border_style is None:
            border_style = self._get_color('error', '#f7768e') if is_error else f"dim {border}"
        # Normalize title: ensure single leading space pattern: "· Title "
        if title and not title.startswith(" "):
            title = f" {title} "
        elif title and not title.endswith(" "):
            title = f"{title} "
        return Panel(
            content,
            title=title,
            title_align=title_align,
            border_style=border_style,
            padding=padding,
        )

    def _size_label(self, text: str, kb_limit: int = 0) -> str:
        """Generate a human-readable size label: e.g. '(2.4 KB · 85 lines)'."""
        lines = text.split("\n")
        line_count = len(lines)
        char_count = len(text)
        if char_count >= 1024:
            size_str = f"{char_count / 1024:.1f} KB"
        else:
            size_str = f"{char_count} B"
        label = f"{size_str} · {line_count} lines"
        if kb_limit > 0 and char_count > kb_limit * 1024:
            label = f"{label} (truncated)"
        return label

    # ── Mount & Welcome ──

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
        ws = str(getattr(app, 'workspace', Path.cwd()))
        model = getattr(app, "current_model", "unknown") if hasattr(app, "current_model") else "unknown"
        provider = getattr(app, "current_provider", "unknown") if hasattr(app, "current_provider") else "unknown"

        primary = self._get_color('primary', '#7aa2f7')
        dim = self._get_color('dim', '#565f89')
        secondary = self._get_color('secondary', '#7dcfff')
        success = self._get_color('success', '#9ece6a')
        border = self._get_color('border', '#3b4261')
        fg = self._get_color('foreground', '#c0caf5')

        greeting = Text.assemble(
            ("\n\n", ""),
            ("           ☁  Cloud Dev Harness\n", f"bold {primary}"),
            ("\n", ""),
            ("  Workspace  ", f"dim {dim}"),
            (f"{ws}\n", f"dim {secondary}"),
            ("\n", ""),
            ("  Provider   ", f"dim {dim}"),
            (f"{provider}", success),
            ("\n", ""),
            ("  Model      ", f"dim {dim}"),
            (f"{model}", f"dim {fg}"),
            ("\n\n\n", ""),
            ("  Tips:\n", f"bold {dim}"),
            ("    @filepath    Read a file\n", f"dim {dim}"),
            ("    /command      Run a slash command\n", f"dim {dim}"),
            ("    Ctrl+F        Focus chat input\n", f"dim {dim}"),
            ("    Ctrl+P        Command palette\n", f"dim {dim}"),
            ("    Tab           Switch mode\n", f"dim {dim}"),
            ("    Ctrl+Q        Quit\n", f"dim {dim}"),
        )
        w.update(greeting)
        w.display = True
        self._welcome_shown = True

    def _scroll_to_bottom(self) -> None:
        self.call_after_refresh(self.scroll_end, animate=False)

    def _get_stream_widget(self) -> Static:
        so = self.query_one_optional("#stream-output", Static)
        if so is None:
            so = Static(id="stream-output")
            self.mount(so)
        return so

    def _remove_stream_widget(self) -> None:
        so = self.query_one_optional("#stream-output", Static)
        if so is not None:
            so.display = False
            so.update("")

    # ── Streaming ──

    def start_stream(self) -> None:
        self._emitted_ids.clear()
        self._hide_welcome()
        self._streaming = True
        self._stream_parser = StreamParser()
        self._assistant_label_shown = False
        self._stream_raw_text = ""
        self._update_stream_widget()

    def _update_stream_widget(self) -> None:
        so = self.query_one_optional("#stream-output", Static)
        if so is None:
            return
        pending_tool = self._stream_parser.get_pending_tool_call()
        pending_thinking = self._stream_parser.get_pending_thinking()
        pending_text = self._stream_parser.get_pending_text()
        pending_tool_result = self._stream_parser.get_pending_tool_result()

        items = []

        # Streaming indicator header
        sec_color = self._get_color('secondary', '#7dcfff')
        dim = self._get_color('dim', '#565f89')
        border = self._get_color('border', '#3b4261')
        items.append(Text(" ◆ Assistant  ◐ streaming...", style=f"dim {sec_color}"))
        items.append(Text(""))

        # Pending tool call — show skeleton
        if pending_tool and not pending_tool.get("complete"):
            name = pending_tool.get("name", "tool")
            cat = pending_tool.get("category", "unknown")
            try:
                cat_icon = TOOL_ICONS[ToolCategory(cat)]
            except (KeyError, ValueError):
                cat_icon = "🔧"
            items.append(Text(f"  {cat_icon} {name}  ◐ running...", style=f"dim {sec_color}"))
            inp = pending_tool.get("input", "")
            if inp:
                inp_str = json.dumps(inp, indent=2) if isinstance(inp, dict) else str(inp)
                items.append(Text(inp_str[:300], style=f"dim {sec_color}"))
            items.append(Text(""))

        # Pending thinking
        if pending_thinking:
            success = self._get_color('success', '#9ece6a')
            items.append(Text("  💭 Thinking...", style=f"dim {success}"))
            items.append(Text(pending_thinking[:500], style=success))
            items.append(Text(""))

        # Pending tool result
        if pending_tool_result:
            tid = pending_tool_result.get("tool_use_id", "")
            content = pending_tool_result.get("content", "")
            is_error = pending_tool_result.get("is_error", False)
            err_color = self._get_color('error', '#f7768e')
            label_style = f"dim {err_color}" if is_error else f"dim {border}"
            status_icon = "✗" if is_error else "↓"
            items.append(Text(f"  {status_icon} Result [{tid[:8]}]", style=label_style))
            if content:
                items.append(Text(str(content)[:500], style=dim))
            items.append(Text(""))

        # Pending text — read from StreamParser first (legacy), fall back to
        # StreamEvent accumulator (native function-calling path).
        pending_text = self._stream_parser.get_pending_text()
        if not pending_text:
            pending_text = self._stream_raw_text
        # Use plain Text for live preview (ai-sdk-python style).
        # RichMarkdown is slow to parse; full rendering happens at finish_stream().
        if pending_text and pending_text.strip():
            items.append(Text(pending_text[:500]))

        if items:
            so.update(Group(*items))
            self._scroll_to_bottom()
        else:
            so.update("")

    def add_stream_chunk(self, content: "str | StreamEvent") -> None:
        if not self._streaming:
            return
        if isinstance(content, StreamEvent):
            # Direct typed event — no StreamParser needed (ai-sdk-python style)
            block = content.to_block_dict()
            if block.get("text") or block.get("type") != "text":
                self._append_block(block)
            self._update_stream_widget()
            self._scroll_to_bottom()
            return

        # Legacy string mode — feed through StreamParser
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
        # OpenCode-style: render accumulated raw text ONCE at stream end.
        # No per-chunk Markdown parsing or _renderables growth during streaming.
        if self._stream_raw_text:
            rendered = _render_markdown_rich(self._stream_raw_text)
            if rendered:
                for item in rendered:
                    self._renderables.append(item)
            else:
                dim = self._get_color('dim', '#565f89')
                self._renderables.append(Text(" (empty) ", style=f"dim {dim}"))
        # Force final chat-log refresh
        self._refresh_chat()
        self._remove_stream_widget()
        self._scroll_to_bottom()

    # ── Block rendering ──

    def _append_block(self, block: dict) -> None:
        btype = block.get("type", "text")
        
        if btype == "thinking":
            content = block.get("thinking", "")
            key = f"think:{content[:50]}:{len(content)}"
            if key in self._emitted_ids:
                return
            self._emitted_ids.add(key)
            if content:
                self._render_thinking(content)
                
        elif btype == "tool_use" or btype == "tool_call":
            self._render_tool_call(block)
            
        elif btype == "tool_result":
            self._render_tool_result(block)
            
        elif btype == "ask_user":
            self._render_ask_user(block)
            
        elif btype == "text":
            text = block.get("text", "")
            if text:
                self._append_text("assistant", text)
                
        elif btype == "tool_use_start":
            self._render_tool_start(block)

    def _refresh_chat(self) -> None:
        log = self.query_one_optional("#chat-log", Static)
        if log is not None:
            log.update(Group(*self._renderables) if self._renderables else "")

    # ── Role labels & separators ──

    def _render_role_label(self, role: str, label: str) -> None:
        """Render a professional role label like deepseek-tui."""
        t = self._theme()
        border = self._get_color('border', '#3b4261')
        dim = self._get_color('dim', '#565f89')
        
        if role == "user":
            color = self._get_color('primary', '#7aa2f7')
            icon = "❯"
        elif role == "assistant":
            color = self._get_color('secondary', '#7dcfff')
            icon = "◆"
        elif role == "system":
            color = dim
            icon = "☲"
        elif role == "error":
            color = self._get_color('error', '#f7768e')
            icon = "✗"
        else:
            color = dim
            icon = "·"
        
        # Thin separator line before each turn (except first)
        if len(self._renderables) > 0:
            sep = Text("─" * 40, style=f"dim {border}")
            self._renderables.append(sep)
        
        # Role label
        role_text = Text(f" {icon} {label} ", style=f"bold {color}")
        self._renderables.append(role_text)

    def _render_turn_separator(self) -> None:
        """Subtle visual separator between message turns."""
        border = self._get_color('border', '#3b4261')
        self._renderables.append(Text(""))
        self._renderables.append(Text("─" * 50, style=f"dim {border}"))

    # ── Text blocks ──

    def _append_text(self, role: str, text: str) -> None:
        sec_color = self._get_color('secondary', '#7dcfff')
        
        if role == "user":
            self._render_role_label(role, "You")
            lines = text.split("\n")
            for line in lines:
                self._renderables.append(Text(f"  {line}", style=f"bold {sec_color}"))
            self._refresh_chat()
            return
        
        # Assistant message — show label only once per turn
        if not self._assistant_label_shown:
            self._render_role_label(role, "Assistant")
            self._assistant_label_shown = True
        
        if self._streaming:
            # OpenCode-style: accumulate raw text ONLY during streaming.
            # No RichMarkdown parsing, no _renderables growth per chunk.
            # Live preview is handled by _update_stream_widget().
            self._stream_raw_text += text
            return
        
        # Non-streaming: render Markdown once and append to chat log
        rendered = _render_markdown_rich(text)
        if rendered:
            for item in rendered:
                self._renderables.append(item)
        else:
            self._renderables.append(Text(" (empty) ", style=f"dim {self._get_color('dim', '#565f89')}"))
        self._refresh_chat()

    # ── Thinking blocks (collapsible) ──

    def _render_thinking(self, content: str) -> None:
        """Render a collapsible thinking block — deepseek-tui style."""
        success = self._get_color('success', '#9ece6a')
        dim = self._get_color('dim', '#565f89')
        
        key = f"thinking_{hash(content)}"
        is_collapsed = key in self._collapsed_thinking
        char_count = len(content.strip())
        
        # Show assistant label if not shown yet
        if not self._assistant_label_shown:
            self._render_role_label("assistant", "Assistant")
            self._assistant_label_shown = True
        
        if is_collapsed:
            label = f" 💭 Thinking  ▶  ({char_count:,} chars)"
            panel = self._make_panel(
                Text(label, style=f"dim {dim}"),
                label,
                border_style=f"dim {dim}",
            )
        else:
            label = f" 💭 Thinking — {char_count:,} chars "
            thinking_text = content.strip()
            if len(thinking_text) > 3000:
                thinking_text = thinking_text[:3000] + f"\n\n... ({char_count - 3000:,} more chars)"
            panel = self._make_panel(
                Text(thinking_text, style=f"dim {success}"),
                label,
                border_style=f"dim {success}",
            )
        
        self._renderables.append(Text(""))
        self._renderables.append(panel)
        self._refresh_chat()

    # ── Tool call rendering ──

    def _render_tool_start(self, block: dict) -> None:
        """Show a pending tool call — compact inline style."""
        tu = block.get("tool_use", {})
        name = tu.get("name", "tool")
        tid = tu.get("id", "")
        cat_str = tu.get("category", "unknown")
        
        try:
            cat = ToolCategory(cat_str)
        except ValueError:
            cat = ToolCategory.UNKNOWN
        
        icon = TOOL_ICONS.get(cat, "🔧")
        label = CATEGORY_LABELS.get(cat, name)
        sec_color = self._get_color('secondary', '#7dcfff')
        border = self._get_color('border', '#3b4261')
        
        # Show assistant label if not shown yet
        if not self._assistant_label_shown:
            self._render_role_label("assistant", "Assistant")
            self._assistant_label_shown = True
        
        status_line = Text.assemble(
            (" ┌", f"dim {border}"),
            (f" {icon} {label} ", f"bold {sec_color}"),
            ("◐ running...", f"dim {sec_color}"),
            (f"  ── {name}", f"dim {self._get_color('dim', '#565f89')}"),
        )
        self._renderables.append(Text(""))
        self._renderables.append(status_line)
        self._refresh_chat()

    def _render_tool_call(self, block: dict) -> None:
        """Render a completed tool call — compact deepseek-tui style."""
        tu = block.get("tool_use", {})
        name = tu.get("name", "tool")
        tid = tu.get("id", "")
        arguments = tu.get("input", {})
        status_str = tu.get("status", "running")
        cat_str = tu.get("category", "unknown")
        elapsed = tu.get("elapsed", 0.0)  # seconds
        
        try:
            status = LifecycleStatus(status_str)
        except ValueError:
            status = LifecycleStatus.COMPLETE
        try:
            cat = ToolCategory(cat_str)
        except ValueError:
            cat = get_tool_category(name)
        
        # Store tool call data for result pairing
        if tid:
            self._tool_call_data[tid] = {
                "name": name,
                "arguments": arguments,
                "category": cat,
            }
        
        icon = TOOL_ICONS.get(cat, "🔧")
        label = CATEGORY_LABELS.get(cat, name)
        sec_color = self._get_color('secondary', '#7dcfff')
        border = self._get_color('border', '#3b4261')
        success_col = self._get_color('success', '#9ece6a')
        dim = self._get_color('dim', '#565f89')
        
        # Show assistant label if not shown yet
        if not self._assistant_label_shown:
            self._render_role_label("assistant", "Assistant")
            self._assistant_label_shown = True
        
        # Status-based styling
        if status == LifecycleStatus.COMPLETE:
            status_icon = "✓"
            status_style = success_col
        elif status == LifecycleStatus.FAILED:
            status_icon = "✗"
            status_style = self._get_color('error', '#f7768e')
        elif status == LifecycleStatus.RUNNING:
            status_icon = "◐"
            status_style = sec_color
        elif status == LifecycleStatus.CANCELLED:
            status_icon = "⊘"
            status_style = dim
        else:
            status_icon = "○"
            status_style = dim
        
        # Compact header line with elapsed time
        elapsed_str = ""
        if elapsed > 0 and status in (LifecycleStatus.COMPLETE, LifecycleStatus.FAILED):
            if elapsed < 1.0:
                elapsed_str = f"  ({elapsed*1000:.0f}ms)"
            elif elapsed < 60:
                elapsed_str = f"  ({elapsed:.1f}s)"
            else:
                elapsed_str = f"  ({elapsed/60:.1f}m)"
        
        header = Text.assemble(
            (" ┌", f"dim {border}"),
            (f" {icon} {label} ", f"bold {sec_color}"),
            (f"{status_icon} done" if status == LifecycleStatus.COMPLETE else f"{status_icon} {status_str}", f"dim {status_style}"),
            (elapsed_str, f"dim {dim}"),
            (f"  ──  {name}", f"dim {dim}"),
        )
        self._renderables.append(Text(""))
        self._renderables.append(header)
        
        # Show arguments with syntax highlighting — unified panel style
        args_changed = False
        if arguments:
            # For file tools, show path prominently
            if cat in (ToolCategory.FILE_READ, ToolCategory.FILE_WRITE, ToolCategory.FILE_EDIT):
                path = arguments.get("path", "")
                if path:
                    self._renderables.append(Text(f"  │ 📍 {path}", style=f"dim {sec_color}"))
                # For File Read, show offset/limit if present
                if cat == ToolCategory.FILE_READ:
                    offset = arguments.get("offset", 0)
                    limit = arguments.get("limit", 0)
                    if offset or limit:
                        range_info = f"L{offset}" if not limit else f"L{offset}-L{offset + limit}"
                        self._renderables.append(Text(f"  │    {range_info}", style=f"dim {dim}"))
                # For Edit / Insert, show inline diff or insert preview
                if name == "Edit":
                    self._render_file_edit_diff(arguments, path)
                    args_changed = True
                elif name == "Insert":
                    line = arguments.get("line", 0)
                    text = arguments.get("text", "")
                    self._renderables.append(Text(f"  │ ↔ Insert at line {line}:", style=f"dim {sec_color}"))
                    self._renderables.append(Text(f"  │    {text[:200]}", style=f"dim {dim}"))
                    args_changed = True
                elif name == "UndoEdit":
                    self._renderables.append(Text(f"  │ ↩ Undo last edit → {path}", style=f"dim {sec_color}"))
                    args_changed = True
                # For Write, show content preview
                if cat == ToolCategory.FILE_WRITE:
                    content = arguments.get("content", "")
                    if content:
                        lines = content.split("\n")
                        line_count = len(lines)
                        size_label = self._size_label(content)
                        preview_content = content[:2000]
                        if len(content) > 2000:
                            preview_content += f"\n\n... ({len(content):,} total chars)"
                        lang = _detect_language_from_path(path)
                        syntax = Syntax(preview_content, lang, theme="monokai", word_wrap=True,
                                      line_numbers=True, padding=(1, 2))
                        panel = self._make_panel(
                            syntax,
                            f" ✎ Content ({size_label} · {lang})",
                        )
                        self._renderables.append(panel)
                        args_changed = True
            
            # For Bash, show command — detect cat/heredoc file ops for nicer rendering
            if cat == ToolCategory.BASH:
                cmd = arguments.get("command", "")
                if cmd:
                    file_op = _parse_cat_heredoc(cmd)
                    if file_op:
                        self._render_bash_file_op(file_op, cmd)
                    else:
                        syntax = Syntax(cmd, "bash", theme="monokai", word_wrap=True, padding=(1, 2))
                        panel = self._make_panel(syntax, " $ Command")
                        self._renderables.append(panel)
                    args_changed = True
            
            # For task/todo management, show structured info
            if cat == ToolCategory.TASK_MGMT:
                self._render_task_mgmt_args(name, arguments)
                args_changed = True
            
            # Default: show all args as JSON
            if not args_changed:
                args_str = json.dumps(arguments, indent=2, ensure_ascii=False) if isinstance(arguments, dict) else str(arguments)
                lang = "bash" if cat == ToolCategory.BASH else "json"
                syntax = Syntax(args_str[:2000], lang, theme="monokai", word_wrap=True, padding=(1, 2))
                panel = self._make_panel(syntax, " Args")
                self._renderables.append(panel)
        
        self._refresh_chat()
    
    def _render_bash_file_op(self, file_op: dict, raw_cmd: str) -> None:
        """Render a Bash cat/heredoc command as a proper file operation.

        Transforms ugly `cat > path <<'EOF'` into clean file-read/write panels
        with syntax highlighting and size labeling.
        """
        dim = self._get_color('dim', '#565f89')
        sec_color = self._get_color('secondary', '#7dcfff')
        success_col = self._get_color('success', '#9ece6a')
        border = self._get_color('border', '#3b4261')
        
        op_type = file_op.get("type", "write")
        filepath = file_op.get("path", "")
        content = file_op.get("content", "")
        
        # ---- Compact header showing what's happening ----
        if op_type == "read":
            icon = "📄"
            label = "Cat Read"
            self._renderables.append(Text(
                f"  │ {icon} {label}  {filepath}",
                style=f"bold {sec_color}",
            ))
        elif op_type == "write":
            icon = "✎"
            label = "Cat Write"
            self._renderables.append(Text(
                f"  │ {icon} {label}  {filepath}  (via heredoc)",
                style=f"bold {sec_color}",
            ))
        elif op_type == "append":
            icon = "✎"
            label = "Cat Append"
            self._renderables.append(Text(
                f"  │ {icon} {label}  {filepath}  (via heredoc)",
                style=f"bold {sec_color}",
            ))
        
        # ---- Show the raw command in a compact dim line ----
        cmd_preview = raw_cmd.strip()
        if len(cmd_preview) > 120:
            cmd_preview = cmd_preview[:117] + "..."
        self._renderables.append(Text(
            f"  │ $ {cmd_preview}",
            style=f"dim {dim}",
        ))
        
        # ---- Show content preview for write/append ----
        if content and op_type in ("write", "append"):
            lang = _detect_language_from_path(filepath)
            size_label = self._size_label(content)
            display = content[:2000]
            if len(content) > 2000:
                display += f"\n\n... ({len(content):,} total chars)"
            
            syntax = Syntax(display, lang, theme="monokai", word_wrap=True,
                          line_numbers=True, padding=(1, 2))
            panel = self._make_panel(
                syntax,
                f" ✎ Content ({size_label} · {lang})",
            )
            self._renderables.append(panel)
    
    def _render_task_mgmt_args(self, name: str, arguments: dict) -> None:
        """Render task/todo management operations with clean structured display."""
        dim = self._get_color('dim', '#565f89')
        sec_color = self._get_color('secondary', '#7dcfff')
        success = self._get_color('success', '#9ece6a')
        warning = self._get_color('warning', '#e0af68')
        
        if name == "TaskCreate":
            title = arguments.get("title", "")
            desc = arguments.get("description", "")
            self._renderables.append(Text(
                f"  │ 📝 New Task: {title}",
                style=f"bold {sec_color}",
            ))
            if desc:
                self._renderables.append(Text(
                    f"  │    {desc[:200]}",
                    style=f"dim {dim}",
                ))
        elif name == "TaskUpdate":
            tid = arguments.get("id", "?")
            status = arguments.get("status", "")
            status_icon = {"todo": "○", "doing": "◐", "done": "✓"}.get(status, "○")
            status_style = {
                "todo": dim,
                "doing": f"bold {warning}",
                "done": f"bold {success}",
            }.get(status, dim)
            self._renderables.append(Text(
                f"  │ 🔄 Task #{tid} → {status_icon} {status}",
                style=f"bold {sec_color}",
            ))
        elif name == "TaskList":
            self._renderables.append(Text(
                f"  │ 📋 Listing all tasks...",
                style=f"bold {sec_color}",
            ))
        elif name == "TodoCreate":
            text = arguments.get("text", "")
            self._renderables.append(Text(
                f"  │ ✅ New Todo: {text[:150]}",
                style=f"bold {sec_color}",
            ))
        elif name == "TodoComplete":
            tid = arguments.get("id", "?")
            self._renderables.append(Text(
                f"  │ ✅ Todo #{tid} completed",
                style=f"bold {success}",
            ))
        elif name == "TodoList":
            self._renderables.append(Text(
                f"  │ 📋 Listing all todos...",
                style=f"bold {sec_color}",
            ))
    
    def _render_ask_user(self, block: dict) -> None:
        """Render an AskUser / approval request block — DeepSeek-TUI style interactive prompt."""
        au = block.get("ask_user", {})
        question = au.get("question", "")
        context = au.get("context", "")
        action_type = au.get("action_type", "")
        path = au.get("path", "")
        
        dim = self._get_color('dim', '#565f89')
        sec_color = self._get_color('secondary', '#7dcfff')
        success_col = self._get_color('success', '#9ece6a')
        warning_col = self._get_color('warning', '#e0af68')
        border = self._get_color('border', '#3b4261')
        
        self._renderables.append(Text(""))
        
        # Header with icon
        self._renderables.append(Text.assemble(
            (" ┌", f"dim {border}"),
            (" 💬 Ask User ", f"bold {warning_col}"),
            (f"──  {action_type or 'question'}", f"dim {dim}"),
        ))
        
        # Question
        self._renderables.append(Text(
            f"  │ {question}",
            style=f"bold {sec_color}",
        ))
        
        # Context / details
        if context:
            try:
                ctx_data = json.loads(context) if isinstance(context, str) else context
            except (json.JSONDecodeError, ValueError):
                ctx_data = context
            if isinstance(ctx_data, dict):
                lines = []
                if path:
                    lines.append(f"File: {path}")
                for k, v in ctx_data.items():
                    if k not in ("requires_approval", "success", "question"):
                        v_str = str(v)[:200]
                        lines.append(f"{k}: {v_str}")
                ctx_text = "\n".join(lines)
            else:
                ctx_text = str(ctx_data)[:500]
            
            if ctx_text:
                self._renderables.append(Text(
                    f"  │ {ctx_text}",
                    style=f"dim {dim}",
                ))
        
        # Action hint
        self._renderables.append(Text(
            f"  │ Type /approve to allow or /deny to reject",
            style=f"dim {dim}",
        ))
        self._refresh_chat()
    
    def _render_file_edit_diff(self, arguments: dict, path: str) -> None:
        """Render a professional diff view — deepseek-tui style with summary line."""
        old_str = arguments.get("old_string", "")
        new_str = arguments.get("new_string", "")
        
        if not old_str and not new_str:
            return
        
        diff_lines = _generate_diff(old_str, new_str, path)
        if not diff_lines:
            return
        
        self._render_diff_block(diff_lines, path, " ✐ Diff")
        
    def _render_diff_block(self, diff_lines: list[str], filepath: str, label: str) -> None:
        """Render a diff block in deepseek-tui style: summary → file label → colored diff."""
        dim = self._get_color('dim', '#565f89')
        sec_color = self._get_color('secondary', '#7dcfff')
        
        # Summary line: "summary: 1 file, +5 -3, 2 hunks"
        summary = _diff_summary(diff_lines, filepath)
        
        # File line: "📂 path/to/file  +N -M"
        added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
        deleted = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
        
        # Render the summary header bar
        self._renderables.append(Text(""))
        if summary:
            self._renderables.append(Text(
                f"  {summary}",
                style=f"bold {sec_color}"
            ))
        self._renderables.append(Text(
            f"  {label}  {filepath or 'file'}  +{added} -{deleted}",
            style=f"dim {dim}"
        ))
        
        # The diff content
        diff_text = "".join(diff_lines)
        max_len = 3000
        truncated = len(diff_text) > max_len
        if truncated:
            diff_text = diff_text[:max_len] + f"\n... ({len(diff_text):,} more chars)"
        
        syntax = Syntax(diff_text, "diff", theme="monokai", word_wrap=True, padding=(1, 2))
        panel = self._make_panel(syntax, "")
        self._renderables.append(panel)

    def _render_file_read_result(self, preview: str, tid: str) -> None:
        """Render file read result — deepseek-tui content-first style."""
        dim = self._get_color('dim', '#565f89')
        sec_color = self._get_color('secondary', '#7dcfff')
        
        tc_data = self._tool_call_data.get(tid, {})
        tc_args = tc_data.get("arguments", {})
        filepath = tc_args.get("path", "")
        
        lines = preview.split("\n")
        lang = _detect_language_from_path(filepath) if filepath else "text"
        if lang == "text":
            lang = _detect_language_from_content(lines[:15])
        
        size_label = self._size_label(preview)
        
        # Content-first heading bar
        self._renderables.append(Text(""))
        if filepath:
            self._renderables.append(Text(
                f"  📄 {filepath}  ({size_label} · {lang})",
                style=f"bold {sec_color}"
            ))
        else:
            self._renderables.append(Text(
                f"  📄 Read  ({size_label} · {lang})",
                style=f"bold {sec_color}"
            ))
        
        # Code block
        display_content = preview
        max_len = 3000
        if len(preview) > max_len:
            display_content = preview[:max_len]
        
        syntax = Syntax(display_content, lang, theme="monokai", word_wrap=True,
                       line_numbers=True, padding=(1, 2))
        panel = self._make_panel(syntax, "")
        self._renderables.append(panel)
        
        if len(preview) > max_len:
            self._renderables.append(
                Text(f"  ... ({len(preview):,} chars total, showing first {max_len:,})",
                     style=f"dim {dim}")
            )

    def _render_file_write_result(self, preview: str, tid: str) -> None:
        """Render file write result — deepseek-tui content-first style."""
        success_col = self._get_color('success', '#9ece6a')
        err_color = self._get_color('error', '#f7768e')
        dim = self._get_color('dim', '#565f89')
        sec_color = self._get_color('secondary', '#7dcfff')
        
        tc_data = self._tool_call_data.get(tid, {})
        tc_args = tc_data.get("arguments", {})
        filepath = tc_args.get("path", "")
        
        self._renderables.append(Text(""))
        
        try:
            result_json = json.loads(preview)
            success_flag = result_json.get("success", True)
        except (json.JSONDecodeError, ValueError):
            success_flag = True
        
        status_icon = "✓" if success_flag else "✗"
        status_style = success_col if success_flag else err_color
        status_text = "written" if success_flag else "failed"
        
        # Content-first heading bar  
        if filepath:
            header = Text.assemble(
                (f"  {status_icon} Wrote ", f"bold {status_style}"),
                (f"{filepath}", f"bold {sec_color}"),
            )
        else:
            header = Text.assemble(
                (f"  {status_icon} Write ", f"bold {status_style}"),
                (status_text, f"dim {status_style}"),
            )
        self._renderables.append(header)
        
        # Show the written content
        content = tc_args.get("content", "")
        if content and filepath:
            size_label = self._size_label(content)
            lang = _detect_language_from_path(filepath)
            display_content = content
            max_len = 2000
            if len(content) > max_len:
                display_content = content[:max_len] + f"\n\n... ({len(content):,} total chars)"
            
            syntax = Syntax(display_content, lang, theme="monokai", word_wrap=True,
                          line_numbers=True, padding=(1, 2))
            panel = self._make_panel(
                syntax,
                f" ({size_label} · {lang})",
                padding=(0, 0),
            )
            self._renderables.append(panel)

    def _render_file_edit_result(self, preview: str, tid: str) -> None:
        """Render file edit result — deepseek-tui style with diff summary."""
        success_col = self._get_color('success', '#9ece6a')
        err_color = self._get_color('error', '#f7768e')
        dim = self._get_color('dim', '#565f89')
        sec_color = self._get_color('secondary', '#7dcfff')
        
        tc_data = self._tool_call_data.get(tid, {})
        tc_args = tc_data.get("arguments", {})
        filepath = tc_args.get("path", "")
        
        self._renderables.append(Text(""))
        
        try:
            result_json = json.loads(preview)
            success_flag = result_json.get("success", True)
        except (json.JSONDecodeError, ValueError):
            success_flag = True
        
        status_icon = "✓" if success_flag else "✗"
        status_style = success_col if success_flag else err_color
        status_text = "applied" if success_flag else "failed"
        
        # Status heading bar
        if filepath:
            self._renderables.append(Text.assemble(
                (f"  {status_icon} Edit {status_text}  ", f"bold {status_style}"),
                (filepath, f"bold {sec_color}"),
            ))
        else:
            self._renderables.append(Text.assemble(
                (f"  {status_icon} Edit ", f"bold {status_style}"),
                (status_text, f"dim {status_style}"),
            ))
        
        # Show diff with summary
        old_str = tc_args.get("old_string", "")
        new_str = tc_args.get("new_string", "")
        if old_str or new_str:
            diff_lines = _generate_diff(old_str, new_str, filepath)
            if diff_lines:
                self._render_diff_block(diff_lines, filepath, " ✐ Applied")

    def _render_insert_result(self, preview: str, tid: str) -> None:
        """Render Insert result — show what was inserted and where."""
        success_col = self._get_color('success', '#9ece6a')
        sec_color = self._get_color('secondary', '#7dcfff')
        self._renderables.append(Text(""))
        # Try to parse the JSON result
        try:
            data = json.loads(preview)
            path = data.get("path", "")
            success = data.get("success", False)
            if success and path:
                self._renderables.append(Text(f"  ✓ Inserted → {path}", style=f"bold {success_col}"))
            else:
                self._renderables.append(Text(f"  ✗ Insert failed: {data.get('error', 'Unknown error')}", style=f"bold {sec_color}"))
        except (json.JSONDecodeError, ValueError):
            self._renderables.append(Text(f"  ✓ {preview.strip()[:200]}", style=f"bold {success_col}"))

    def _render_undo_result(self, preview: str) -> None:
        """Render UndoEdit result."""
        success_col = self._get_color('success', '#9ece6a')
        sec_color = self._get_color('secondary', '#7dcfff')
        self._renderables.append(Text(""))
        try:
            data = json.loads(preview)
            success = data.get("success", False)
            msg = data.get("message", data.get("path", ""))
            if success:
                self._renderables.append(Text(f"  ↩ {msg}", style=f"bold {success_col}"))
            else:
                self._renderables.append(Text(f"  ✗ Undo failed: {data.get('error', '')}", style=f"bold {sec_color}"))
        except (json.JSONDecodeError, ValueError):
            self._renderables.append(Text(f"  ↩ {preview.strip()[:200]}", style=f"bold {success_col}"))

    # ── Tool result rendering ──

    def _render_tool_result(self, block: dict) -> None:
        """Render a tool result with category-aware formatting — deepseek-tui style."""
        tr = block.get("tool_result", {})
        tid = tr.get("tool_use_id", "")
        content = tr.get("content", "")
        is_error = tr.get("is_error", False)
        cat_str = tr.get("category", "unknown")
        truncated = tr.get("truncated", False)
        full_size = tr.get("full_size", 0)
        
        try:
            cat = ToolCategory(cat_str)
        except ValueError:
            cat = ToolCategory.UNKNOWN
        
        content_str = str(content)
        content_len = len(content_str)
        dim_color = self._get_color('dim', '#565f89')
        sec_color = self._get_color('secondary', '#7dcfff')
        err_color = self._get_color('error', '#f7768e')
        success = self._get_color('success', '#9ece6a')
        
        # Show assistant label if not shown yet
        if not self._assistant_label_shown:
            self._render_role_label("assistant", "Assistant")
            self._assistant_label_shown = True
        
        if is_error:
            self._renderables.append(Text(""))
            panel = self._make_panel(
                Text(content_str[:1000].strip(), style=err_color),
                " ✗ Error",
                is_error=True,
            )
            self._renderables.append(panel)
        else:
            rendered = False
            preview = content_str
            max_preview = 3000
            is_truncated = content_len > max_preview
            if is_truncated:
                preview = content_str[:max_preview]
            
            # Category-specific formatting
            if cat == ToolCategory.FILE_READ:
                self._render_file_read_result(preview, tid)
                rendered = True
            
            elif cat == ToolCategory.FILE_WRITE:
                self._render_file_write_result(preview, tid)
                rendered = True
            
            elif cat == ToolCategory.FILE_EDIT:
                tc_data = self._tool_call_data.get(tid, {})
                tc_name = tc_data.get("name", "")
                if tc_name == "Insert":
                    self._render_insert_result(preview, tid)
                elif tc_name == "UndoEdit":
                    self._render_undo_result(preview)
                else:
                    self._render_file_edit_result(preview, tid)
                rendered = True
            
            elif cat == ToolCategory.BASH:
                # If the command was `cat path` (a file read via shell),
                # render it as a file read, not terminal output.
                tc_data = self._tool_call_data.get(tid, {})
                tc_args = tc_data.get("arguments", {})
                cmd_raw = tc_args.get("command", "")
                file_op = _parse_cat_heredoc(cmd_raw) if cmd_raw else None
                
                if file_op and file_op.get("type") == "read" and preview.strip():
                    # Render as file read
                    filepath = file_op.get("path", "")
                    lang = _detect_language_from_path(filepath) if filepath else "text"
                    if lang == "text":
                        lang = _detect_language_from_content(preview.split("\n")[:15])
                    
                    size_label = self._size_label(preview)
                    self._renderables.append(Text(""))
                    if filepath:
                        self._renderables.append(Text(
                            f"  📄 {filepath}  ({size_label} · {lang})",
                            style=f"bold {sec_color}",
                        ))
                    else:
                        self._renderables.append(Text(
                            f"  📄 Read  ({size_label} · {lang})",
                            style=f"bold {sec_color}",
                        ))
                    
                    display = preview[:3000]
                    syntax = Syntax(display, lang, theme="monokai", word_wrap=True,
                                  line_numbers=True, padding=(1, 2))
                    panel = self._make_panel(syntax, "")
                    self._renderables.append(panel)
                    
                    if len(preview) > 3000:
                        self._renderables.append(Text(
                            f"  ... ({len(preview):,} chars total, showing first 3000)",
                            style=f"dim {dim_color}",
                        ))
                else:
                    # Regular terminal output
                    size_label = self._size_label(preview)
                    syntax = Syntax(preview, "ansi", theme="monokai", word_wrap=True, padding=(1, 2))
                    panel = self._make_panel(
                        syntax,
                        f" ⚡ Terminal Output ({size_label})",
                        padding=(0, 0),
                    )
                    self._renderables.append(Text(""))
                    self._renderables.append(panel)
                rendered = True
            
            elif cat == ToolCategory.TASK:
                # Sub-agent result — structured output with section parsing
                sections = {}
                current_section = None
                section_lines = []
                section_pattern = re.compile(
                    r'^(SUMMARY|CHANGES|EVIDENCE|RISKS|BLOCKERS):\s*$',
                    re.MULTILINE | re.IGNORECASE
                )
                for line in preview.split("\n"):
                    match = section_pattern.match(line)
                    if match:
                        if current_section:
                            sections[current_section] = "\n".join(section_lines).strip()
                        current_section = match.group(1).upper()
                        section_lines = []
                    elif current_section:
                        section_lines.append(line)
                if current_section:
                    sections[current_section] = "\n".join(section_lines).strip()
                
                if sections:
                    self._renderables.append(Text(""))
                    section_icons = {
                        "SUMMARY": ("📋", success),
                        "CHANGES": ("✐", sec_color),
                        "EVIDENCE": ("📌", self._get_color('primary', '#7aa2f7')),
                        "RISKS": ("⚠", self._get_color('warning', '#e0af68')),
                        "BLOCKERS": ("🛑", err_color),
                    }
                    for sec_name, sec_content in sections.items():
                        icon, style_color = section_icons.get(sec_name, ("·", dim_color))
                        if sec_content:
                            sec_size = self._size_label(sec_content)
                            panel = self._make_panel(
                                Text(sec_content[:1000], style=dim_color),
                                f" {icon} {sec_name.title()} ({sec_size})",
                            )
                            self._renderables.append(panel)
                    rendered = True
                else:
                    panel = self._make_panel(
                        Text(preview[:1000], style=dim_color),
                        " 🤖 SubAgent Result",
                    )
                    self._renderables.append(Text(""))
                    self._renderables.append(panel)
                    rendered = True
            
            elif cat in (ToolCategory.WEB_FETCH, ToolCategory.WEB_SEARCH):
                size_label = self._size_label(preview[:1500])
                panel = self._make_panel(
                    Text(preview[:1500], style=dim_color),
                    f" 🌐 Web Result ({size_label})",
                )
                self._renderables.append(Text(""))
                self._renderables.append(panel)
                rendered = True
            
            elif cat in (ToolCategory.FILE_LIST, ToolCategory.FILE_GLOB, ToolCategory.FILE_GREP):
                size_label = self._size_label(preview[:2000])
                panel = self._make_panel(
                    Text(preview[:2000], style=dim_color),
                    f" 📁 Listing ({size_label})",
                )
                self._renderables.append(Text(""))
                self._renderables.append(panel)
                rendered = True
            
            elif cat == ToolCategory.TASK_MGMT:
                tc_data = self._tool_call_data.get(tid, {})
                tc_name = tc_data.get("name", "")
                self._renderables.append(Text(""))
                if tc_name in ("TaskList", "TodoList"):
                    # Parse list results
                    lines = [l for l in preview.strip().split("\n") if l.strip()]
                    for line in lines:
                        self._renderables.append(Text(f"  │ {line}", style=f"dim {dim_color}"))
                    if not lines:
                        self._renderables.append(Text(f"  │ (empty)", style=f"dim {dim_color}"))
                elif tc_name == "TaskCreate":
                    self._renderables.append(Text(f"  ✅ {preview.strip()}", style=f"bold {success}"))
                elif tc_name == "TaskUpdate":
                    self._renderables.append(Text(f"  ✅ {preview.strip()}", style=f"bold {success}"))
                elif tc_name == "TodoComplete":
                    self._renderables.append(Text(f"  ✅ {preview.strip()}", style=f"bold {success}"))
                else:
                    self._renderables.append(Text(f"  ✓ {preview.strip()}", style=f"dim {success}"))
                rendered = True
            
            # Default fallback
            if not rendered:
                if preview.strip().startswith("{") or preview.strip().startswith("["):
                    try:
                        parsed = json.loads(preview)
                        formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
                        syntax = Syntax(formatted[:3000], "json", theme="monokai", word_wrap=True, padding=(1, 2))
                        panel = self._make_panel(syntax, " Result (JSON)", padding=(0, 0))
                        self._renderables.append(Text(""))
                        self._renderables.append(panel)
                        rendered = True
                    except (json.JSONDecodeError, ValueError):
                        pass
                
                if not rendered:
                    panel = self._make_panel(
                        Text(preview.strip()[:2000] if preview.strip() else "(empty)", style=f"dim {dim_color}"),
                        " Result",
                    )
                    self._renderables.append(Text(""))
                    self._renderables.append(panel)
            
            # Truncation indicator
            if is_truncated:
                self._renderables.append(
                    Text(f"  ... ({content_len:,} chars total, showing first {max_preview:,})", style=f"dim {dim_color}")
                )
        
        self._refresh_chat()

    # ── Non-streaming messages ──

    def add_message(self, role: str, content: str) -> None:
        if self._welcome_shown:
            self._hide_welcome()
        fg = self._get_color('foreground', '#c0caf5')
        dim = self._get_color('dim', '#565f89')
        
        if role == "user":
            self._render_role_label(role, "You")
            lines = content.split("\n")
            sec_color = self._get_color('secondary', '#7dcfff')
            for line in lines:
                self._renderables.append(Text(f"  {line}", style=f"bold {sec_color}"))
        elif role == "assistant":
            self._render_role_label(role, "Assistant")
            rendered = _render_markdown_rich(content)
            if rendered:
                for item in rendered:
                    self._renderables.append(item)
            else:
                self._renderables.append(Text(" (empty) ", style=f"dim {dim}"))
        elif role == "system":
            self._render_role_label(role, "System")
            for line in content.split("\n"):
                self._renderables.append(Text(f"  {line}", style=f"dim {dim}"))
        elif role == "error":
            self._render_role_label(role, "Error")
            err_color = self._get_color('error', '#f7768e')
            for line in content.split("\n"):
                self._renderables.append(Text(f"  {line}", style=f"bold {err_color}"))
        else:
            self._render_role_label(role, role.title())
            for line in content.split("\n"):
                self._renderables.append(Text(f"  {line}", style=fg))
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
        self._emitted_ids.clear()
        self._tool_call_data.clear()
        self._assistant_label_shown = False
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
