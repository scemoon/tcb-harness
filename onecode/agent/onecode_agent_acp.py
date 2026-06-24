#!/usr/bin/env python3
"""CDH ACP Adapter - Allows CDH Agent to communicate via ACP protocol.

This adapter runs as a subprocess and translates JSONRPC calls from A2TUI
into CDH AgentEngine calls.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from collections.abc import Callable
from pathlib import Path


logger = logging.getLogger("onecode.agent.cdh_acp")


def _short_path(p: str, project_dir: Path | None = None) -> str:
    """Return *p* relative to *project_dir* if it is an absolute path under it."""
    if not p or not project_dir:
        return p
    try:
        resolved = Path(p).resolve()
        return str(resolved.relative_to(project_dir.resolve()))
    except (ValueError, OSError):
        return p


def debug_log(*args, **kwargs):
    """Debug log via the ``onecode.agent.onecode_acp`` logger.

    Falls back to stderr if the logging system has not been configured
    yet (e.g. during very early adapter import when ``setup_logging`` has
    not been called).  This keeps the function safe to call from any
    module-import-time path without breaking the JSON-RPC stream on stdout.
    """
    if logger.handlers or logging.getLogger().handlers:
        logger.debug(" ".join(str(a) for a in args), **kwargs)
    else:
        print("[onecode]", *args, file=sys.stderr, flush=True)


_CRASH_LOG_DIR = Path.home() / ".cdh" / "logs"


def _dump_crash(context: str) -> None:
    """Write traceback to ``~/.cdh/logs/cdh_crash.log`` so it survives subprocess exit."""
    import os
    import traceback
    now = __import__("datetime").datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    _CRASH_LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = _CRASH_LOG_DIR / "cdh_crash.log"
    try:
        lines = [f"=== crash at {now} context={context} ===\n"]
        for tb_line in traceback.format_exc().splitlines(True):
            lines.append(tb_line)
        with open(os.fspath(path), "a", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception:
        pass


from onecode.agent.cdh_loader import CdhProjectLoader
from onecode.agent.engine import AgentEngine
from onecode.agent.permissions_store import PermissionStore
from onecode.agent.session import AgentSession
from onecode.config import load_config
from onecode.models.provider import ProviderRegistry
from onecode.models.registry import ModelRegistry
from onecode.models.messages import (
    StreamEventType,
    ToolCategory,
    AgentMessage,
    TextBlock,
    ThinkBlock,
    ToolCall as MsgToolCall,
    ToolResult,
    SubAgentBlock,
    LifecycleStatus,
    get_tool_category,
)

from onecode.models.providers.minimaxi_provider import MiniMaxiProvider
from onecode.models.providers.minimax_provider import MiniMaxProvider
from onecode.models.providers.anthropic_provider import AnthropicProvider
from onecode.models.providers.openai_provider import OpenAIProvider
from onecode.models.providers.deepseek_provider import DeepSeekProvider
from onecode.models.providers.glm_provider import GLMProvider
from onecode.models.providers.ollama_provider import OllamaProvider


_CATEGORY_TO_ACP_KIND: dict[str, str] = {
    ToolCategory.FILE_READ: "read",
    ToolCategory.FILE_WRITE: "edit",
    ToolCategory.FILE_EDIT: "edit",
    ToolCategory.FILE_LIST: "read",
    ToolCategory.FILE_GLOB: "search",
    ToolCategory.FILE_GREP: "search",
    ToolCategory.BASH: "execute",
    ToolCategory.WEB_FETCH: "fetch",
    ToolCategory.WEB_SEARCH: "search",
    ToolCategory.TASK: "other",
    ToolCategory.TASK_MGMT: "other",
    ToolCategory.INTERACTION: "other",
    ToolCategory.UNKNOWN: "other",
}


def _kind_for_category(cat: ToolCategory) -> str:
    """Map internal ``ToolCategory`` enum to ACP wire-format ``kind`` string.

    The TUI expects ``"read"``, ``"edit"``, ``"search"``, ``"execute"``,
    ``"fetch"`` or ``"other"`` (see ``tui/acp/protocol.py:ToolCall``).
    """
    return _CATEGORY_TO_ACP_KIND.get(cat, "other")


_DEFAULT_MODES = {
    "currentModeId": "build",
    "availableModes": [
        {"id": "build", "name": "Build", "description": "Full development agent. Edits and shell commands require user approval."},
        {"id": "plan",  "name": "Plan",  "description": "Read-only planning and analysis. Edits and shell commands require approval."},
        {"id": "solo",  "name": "Solo",  "description": "Independent mode with plan-first workflow. Edits allowed, shell commands require approval."},
    ],
}

_OPEN_MARKER = "[TOOL_CALL]"
_CLOSE_MARKER = "[/TOOL_CALL]"

# Structured tool call markers (see engine.py MINIMAX_TOOL_CALL_RE).
# The adapter's stream callback strips these from the user-visible text so
# raw ``<minimax:tool_call>`` XML never reaches the chat.
_MINIMAX_OPEN = "<minimax:tool_call>"
_MINIMAX_CLOSE = "</minimax:tool_call>"


def _extract_text_from_blocks(content: list) -> str:
    """Concatenate the `text` field of each `text` block in a content list."""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(item.get("text", ""))
    return "".join(parts)


def _scan_balanced_braces(text: str, open_pos: int) -> int | None:
    """Return position of the matching '}' for the '{' at open_pos.

    Handles nested braces, single/double-quoted strings, and
    single-line comments. Returns None if no matching brace is found.
    """
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
        elif c == '"':
            i += 1
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    i += 2
                else:
                    i += 1
            i += 1
        elif c == "'":
            i += 1
            while i < n and text[i] != "'":
                if text[i] == "\\" and i + 1 < n:
                    i += 2
                else:
                    i += 1
            i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
        else:
            i += 1
    return None


def _parse_tool_call_body(body: str) -> dict:
    """Parse the body of a [TOOL_CALL]...[/TOOL_CALL] block.

    Returns a dict with 'name' (str | None) and 'arguments' (dict).
    """
    body = body.strip()
    if not body or not body.startswith("{"):
        return {"name": None, "arguments": {}}

    body_close = _scan_balanced_braces(body, 0)
    if body_close is None:
        return {"name": None, "arguments": {}}
    inner = body[1:body_close]

    name_match = re.search(r'tool\s*=>\s*"([^"]+)"', inner)
    name = name_match.group(1) if name_match else None

    arguments: dict = {}
    args_match = re.search(r'args\s*=>\s*\{', inner)
    if args_match:
        args_outer = _scan_balanced_braces(inner, args_match.end() - 1)
        if args_outer is not None:
            args_body = inner[args_match.end():args_outer]
            for am in re.finditer(
                r'--(\w+)\s+"((?:[^"\\]|\\.)*)"', args_body, re.DOTALL
            ):
                arguments[am.group(1)] = am.group(2)

    return {"name": name, "arguments": arguments}


def _extract_legacy_tool_call(text: str) -> dict | None:
    """Parse a complete [TOOL_CALL]...[/TOOL_CALL] block from text.

    Returns a dict with:
        - name: tool name
        - arguments: dict of argument name -> value
        - span: (start, end) of the full [TOOL_CALL]...[/TOOL_CALL]
    Returns None if no complete block is found.
    """
    open_idx = text.find(_OPEN_MARKER)
    if open_idx < 0:
        return None
    body_start = open_idx + len(_OPEN_MARKER)
    close_idx = text.find(_CLOSE_MARKER, body_start)
    if close_idx < 0:
        return None
    body = text[body_start:close_idx]
    span_end = close_idx + len(_CLOSE_MARKER)

    parsed = _parse_tool_call_body(body)
    parsed["span"] = (open_idx, span_end)
    return parsed


_LANG_BY_EXT: dict[str, str] = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "jsx", ".tsx": "tsx", ".json": "json", ".yml": "yaml",
    ".yaml": "yaml", ".toml": "toml", ".md": "markdown", ".sh": "bash",
    ".html": "html", ".css": "css", ".rs": "rust", ".go": "go",
    ".java": "java", ".kt": "kotlin", ".swift": "swift", ".rb": "ruby",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".sql": "sql",
}


def _language_for_path(path: str) -> str:
    """Return a Markdown code-fence language hint based on file extension."""
    if not path:
        return ""
    dot = path.rfind(".")
    slash = max(path.rfind("/"), path.rfind("\\"))
    if dot > slash and dot >= 0:
        return _LANG_BY_EXT.get(path[dot:].lower(), "")
    return ""


_STATUS_TO_WIRE: dict[str, str] = {
    "pending": "pending",
    "in_progress": "in_progress",
    "running": "in_progress",
    "complete": "completed",
    "completed": "completed",
    "failed": "failed",
    "cancelled": "failed",
}


def _wire_status(value: str | None) -> str:
    """Map an internal LifecycleStatus value to the ACP wire literal.

    The ACP protocol (TUI side) expects ``ToolCallStatus = Literal["pending",
    "in_progress", "completed", "failed"]``; the internal enum uses ``complete``
    and ``cancelled``.  This helper normalises everything to a wire-valid value
    and defaults to ``"completed"`` for any unknown value.
    """
    if not value:
        return "completed"
    return _STATUS_TO_WIRE.get(value, "completed")


def _try_pretty_print_json(text: str) -> str:
    """If *text* looks like JSON, pretty-print it; otherwise return as-is.

    Handles both raw JSON and JSON that was embedded as a string inside
    another JSON value (i.e. with ``\\n``, ``\\"`` etc. as literal escapes).
    """
    stripped = text.strip()
    if not (stripped.startswith("{") or stripped.startswith("[")):
        return text

    # Direct parse
    try:
        obj = json.loads(stripped)
        return json.dumps(obj, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError):
        pass

    # The text may contain literal escape sequences (e.g. ``\n``, ``\"``)
    # from being nested inside another JSON string.  Unescape and retry.
    try:
        unescaped = stripped.encode("utf-8").decode("unicode_escape")
        obj = json.loads(unescaped)
        return json.dumps(obj, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return text


def _build_tool_call_content(name: str | None, arguments: dict) -> list:
    """Convert a tool's args into the ACP content blocks the TUI expects.

    The TUI has dedicated widgets for `diff` (DiffView) and structured text
    (Markdown / Static). JSON-fence fallbacks only kick in for tools we
    don't recognise, so known tools render as their intended visual.

    Write emits a Markdown block (`path` header + code fence) so the
    content reads as code rather than a noisy all-additions diff.
    Edit keeps the diff block because there are real before/after changes.
    """
    if not arguments:
        return []

    if name == "Read":
        return []

    _HEADER_ONLY_TOOLS = frozenset({
        "TodoCreate", "TodoGet", "TodoList", "TodoUpdate", "TodoOutput", "TodoStop",
        "Glob", "Spawn",
    })
    if name in _HEADER_ONLY_TOOLS:
        return []

    if name == "Write":
        path = str(arguments.get("path", ""))
        content = str(arguments.get("content", ""))
        if path:
            lang = _language_for_path(path)
            return [{
                "type": "content",
                "content": {
                    "type": "text",
                    "text": f"📄 {path}\n```{lang}\n{content}\n```",
                },
            }]

    if name == "Edit":
        path = str(arguments.get("path", ""))
        old = str(arguments.get("old_string", arguments.get("oldText", "")))
        new = str(arguments.get("new_string", arguments.get("newText", "")))
        if path:
            return [{
                "type": "diff",
                "path": path,
                "oldText": old,
                "newText": new,
            }]

    if name == "Bash":
        cmd = str(arguments.get("command", arguments.get("cmd", "")))
        if cmd:
            return [{
                "type": "content",
                "content": {
                    "type": "text",
                    "text": f"```bash\n$ {cmd}\n```",
                },
            }]

    if name == "ApplyPatch":
        patch = str(arguments.get("patch", ""))
        if patch:
            return [{
                "type": "content",
                "content": {"type": "text", "text": f"```diff\n{patch}\n```"},
            }]

    if name == "Insert":
        path = str(arguments.get("path", ""))
        line = arguments.get("line", -1)
        text = str(arguments.get("text", ""))
        if path:
            lang = _language_for_path(path)
            return [{
                "type": "content",
                "content": {
                    "type": "text",
                    "text": f"📝 {path} (line {line})\n```{lang}\n{text}\n```",
                },
            }]

    if name == "UndoEdit":
        path = str(arguments.get("path", ""))
        if path:
            return [{
                "type": "content",
                "content": {"type": "text", "text": f"↩️ Undo edit on {path}"},
            }]

    if name == "AskUser":
        q = str(arguments.get("question", ""))
        opts = arguments.get("options", [])
        lines = [f"❓ {q}"]
        for o in opts:
            label = o.get("label", "")
            desc = o.get("description", "")
            if desc:
                lines.append(f"  • {label} — {desc}")
            else:
                lines.append(f"  • {label}")
        return [{
            "type": "content",
            "content": {"type": "text", "text": "\n".join(lines)},
        }] if lines else []

    args_text = json.dumps(arguments, indent=2, ensure_ascii=False)
    return [{
        "type": "content",
        "content": {"type": "text", "text": f"```json\n{args_text}\n```"},
    }]


def _format_tui_display_text(result_text: str, tool_name: str = "") -> str:
    """Convert internal tool result JSON to user-visible text for TUI.

    Tools return dicts like ``{"success": true, "path": "..."}`` that are
    meaningful to the LLM but noisy for the user.  This function strips
    internal JSON wrappers and returns only what the user should see.

    Success results that have a ``path`` field render as ``✓ /path``;
    other success results fall through to a compact view of the rest
    of the dict.

    Task / Todo tools (TaskCreate, TaskUpdate, TaskList, …) are special-
    cased: their verbose ``{"task": {...}}`` / ``{"tasks": [...]}`` results
    are collapsed to a single concise marker (``✓ updated``) since the
    LLM's tool-call args already show what the agent did, and re-printing
    the full task object after every call clutters the conversation view.
    """
    if not result_text:
        return ""
    try:
        parsed = json.loads(result_text)
    except json.JSONDecodeError:
        return result_text
    if not isinstance(parsed, dict):
        return result_text
    if "error" in parsed:
        return str(parsed["error"])
    # Read: show actual file content (code fence + language wrapping in _emit_tool_result)
    if tool_name == "Read":
        return parsed.get("content", "")
    # Todo tools: collapse verbose state echoes to one-liner.
    if tool_name in _STATUS_ONLY_TOOLS:
        return "✓ updated"
    if parsed.get("success") is True:
        if path := parsed.get("path"):
            return f"✓ {path}"
        visible = {k: v for k, v in parsed.items() if k != "success"}
        if not visible:
            return "✓ done"
        try:
            return json.dumps(visible, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(visible)
    return result_text


_STATUS_ONLY_TOOLS = frozenset({
    "TodoCreate",
    "TodoGet",
    "TodoList",
    "TodoUpdate",
    "TodoOutput",
    "TodoStop",
})


_BARE_LEGACY_RE = re.compile(
    r"\{[^{}]*tool\s*=>\s*\"(?P<name>\w+)\"[^{}]*args\s*=>\s*\{",
    re.DOTALL,
)


def _find_bare_legacy_tool_call(text: str) -> int | None:
    """Find the start of a bare `{tool => "X", args => { ... }}` body.

    Unlike `[TOOL_CALL]...[/TOOL_CALL]`, this pattern has no enclosing
    markers — we have to scan to the matching `}` ourselves.
    """
    m = _BARE_LEGACY_RE.search(text)
    if m is None:
        return None
    # Reject matches that look like the inside of a fenced code block.
    if "```" in text[: m.start()]:
        last_fence = text.rfind("```", 0, m.start())
        if last_fence >= 0 and text.count("```", last_fence, m.start()) == 1:
            return None
    return m.start()


def _filter_tool_call_text(text: str) -> str:
    """Remove complete ``[TOOL_CALL]...[/TOOL_CALL]`` and
    ``<minimax:tool_call>...</minimax:tool_call>`` blocks from text.

    Incomplete blocks (no closing marker) are left in place so the caller
    can hold the buffer and wait for more input.
    """
    out: list[str] = []
    pos = 0
    while pos < len(text):
        parsed = _extract_legacy_tool_call(text[pos:])
        minimax_start = text.find(_MINIMAX_OPEN, pos)
        minimax_end = (
            text.find(_MINIMAX_CLOSE, pos) if minimax_start >= 0 else -1
        )
        minimax_span = (
            (minimax_start, minimax_end + len(_MINIMAX_CLOSE))
            if minimax_start >= 0 and minimax_end >= 0
            else None
        )

        candidates: list[tuple[int, tuple[int, int]]] = []
        if parsed is not None:
            candidates.append((parsed["span"][0], parsed["span"]))
        if minimax_span is not None:
            candidates.append((minimax_span[0], minimax_span))

        if not candidates:
            out.append(text[pos:])
            break

        candidates.sort(key=lambda c: c[0])
        rel_start, span = candidates[0]
        rel_end = span[1]
        abs_start = pos + rel_start
        abs_end = pos + rel_end
        before = text[pos:abs_start]
        if before:
            out.append(before)
        pos = abs_end
    return "".join(out)


def _create_engine(cwd: str, perm_store: PermissionStore | None = None) -> AgentEngine:
    cfg = load_config()
    ModelRegistry.initialize()
    provider_cls = ProviderRegistry.get(cfg.default_provider)
    if provider_cls is None:
        provider_cls = ProviderRegistry.get("minimaxi")

    class MinimalApp:
        config = cfg
        current_provider = cfg.default_provider
        current_model = cfg.default_model

    project_dir = Path(cwd).resolve() if cwd else Path.cwd()
    return AgentEngine(MinimalApp(), project_dir=project_dir, perm_store=perm_store)


class TextChunker:
    """对文本流按语义边界分组后发送，减少 ACP 消息频率。

    三种模式:
    - "words": 每 N 个分隔符（空格/换行/tab）切一次
    - "line":  每遇到换行切一次
    - "auto":  自动检测 ``` 代码块：代码块内用 line，外部用 words

    Args:
        send_fn: 收到完整文本块时的回调
        mode: "words" | "line" | "auto"
        words: words 模式下的分隔符计数阈值
        line_max: line 模式下无换行时的强制截断长度
        word_max: words 模式下无分隔符时的强制截断长度
    """

    def __init__(
        self,
        send_fn: Callable[[str], None],
        mode: str = "auto",
        words: int = 5,
        line_max: int = 500,
        word_max: int = 100,
    ):
        self._buf = ""
        self._send = send_fn
        self._mode = mode
        self._words = words
        self._line_max = line_max
        self._word_max = word_max

    def append(self, text: str) -> None:
        if not text:
            return
        self._buf += text
        self._process()

    def flush(self) -> None:
        if self._buf:
            self._send(self._buf)
            self._buf = ""

    def _process(self) -> None:
        while self._buf:
            in_code = False
            if self._mode == "auto":
                in_code = (self._buf.count("```") % 2 == 1)

            if in_code or self._mode == "line":
                n = self._buf.find("\n")
                if n >= 0:
                    n += 1
                elif len(self._buf) >= self._line_max:
                    n = self._line_max
                else:
                    break
            else:
                n = self._buf.find("\n")
                if n >= 0:
                    n += 1
                else:
                    sep_count = 0
                    for i, ch in enumerate(self._buf):
                        if ch in (' ', '\n', '\t'):
                            sep_count += 1
                            if sep_count >= self._words:
                                n = i + 1
                                break
                    if n < 0:
                        if len(self._buf) >= self._word_max:
                            n = self._word_max
                        else:
                            break

            chunk = self._buf[:n]
            self._buf = self._buf[n:].lstrip()
            if chunk:
                self._send(chunk)


class CDHACPAdapter:
    """Adapter that translates ACP protocol to CDH AgentEngine."""

    def __init__(self):
        self.agent = None
        self.session_id = None
        self.tool_calls = {}
        self.in_thinking = False
        self._pending_requests: dict[str, asyncio.Future[dict]] = {}
        self._request_seq = 0
        self._perm_store = PermissionStore()
        self._ask_user_future: asyncio.Future[dict] | None = None

    def _perm_store_load(self, cwd: str | None = None) -> None:
        """Load permission overrides from ``.cdh/permissions.json``."""
        project_dir = Path(cwd).resolve() if cwd else (self.agent._project_dir if self.agent else Path.cwd())
        cdh_dir = CdhProjectLoader.find_cdh_dir(project_dir)
        if cdh_dir:
            data = CdhProjectLoader.load_permissions(cdh_dir)
            if data:
                self._perm_store = PermissionStore.from_dict(data)

    def _perm_store_save(self) -> None:
        """Save permission overrides to ``.cdh/permissions.json``."""
        if not self.agent:
            return
        cdh_dir = CdhProjectLoader.find_cdh_dir(self.agent._project_dir)
        if cdh_dir:
            CdhProjectLoader.save_permissions(cdh_dir, self._perm_store.to_dict())

    def _handle_reset_permission(self, key: str = "") -> dict:
        """Handle /permission slash command.

        Without argument: clears all overrides.
        With argument (e.g. ``bash``): clears that specific override.
        """
        if key:
            old = self._perm_store.get_override(key)
            if old:
                self._perm_store.clear_override(key)
                setattr(self.agent.current_agent, f"permission_{key}", None)
                msg = f"Permission override `{key}` ({old.value}) cleared."
            else:
                msg = f"No override found for `{key}`."
        else:
            count = len(self._perm_store._overrides)
            self._perm_store.clear_all()
            msg = f"All {count} permission override(s) cleared."
        self._perm_store_save()
        self.send_session_update({
            "sessionUpdate": "agent_message_chunk",
            "content": {"type": "text", "text": f"✅ {msg}"},
        })
        return {"stopReason": "end_turn"}

    @staticmethod
    def _content_to_blocks(content: str | list) -> list:
        """Convert old-format message content to list of AgentBlock objects."""
        blocks: list = []
        if isinstance(content, str):
            blocks = CDHACPAdapter._text_to_blocks(content)
        elif isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type", "")
                if item_type == "text":
                    blocks.append(TextBlock(content=item.get("text", "")))
                elif item_type == "thinking":
                    blocks.append(ThinkBlock(content=item.get("thinking", "")))
                elif item_type == "tool_use":
                    blocks.append(MsgToolCall(
                        id=item.get("id", ""),
                        name=item.get("name", ""),
                        arguments=item.get("input", {}),
                        status=LifecycleStatus(item.get("status", "complete")),
                    ))
                elif item_type == "tool_result":
                    blocks.append(ToolResult(
                        tool_use_id=item.get("tool_use_id", ""),
                        content=item.get("content", ""),
                        is_error=item.get("is_error", False),
                    ))
                elif item_type == "subagent":
                    blocks.append(SubAgentBlock(
                        id=item.get("id", ""),
                        agent_type=item.get("agent_type", "default"),
                        prompt=item.get("prompt", ""),
                        result=item.get("result", ""),
                        status=item.get("status", "complete"),
                    ))
        return blocks

    @staticmethod
    def _text_to_blocks(text: str) -> list:
        """Convert text containing legacy [TOOL_CALL] / <thinking> patterns to blocks.

        Parses text that may contain:
        - [TOOL_CALL] {tool => "Name", args => { ... }} [/TOOL_CALL] patterns
        - <thinking>...</thinking> tags
        Returns a list of TextBlock, ThinkBlock, and MsgToolCall blocks.
        """
        THINKING_RE = re.compile(r'<think(?:ing)?>(.*?)</think(?:ing)?>', re.DOTALL)

        blocks: list = []
        remaining = text
        legacy_id = 0

        while remaining:
            parsed_tool = _extract_legacy_tool_call(remaining)
            tool_start = parsed_tool["span"][0] if parsed_tool else -1
            think_match = THINKING_RE.search(remaining)

            candidates: list[tuple[int, str]] = []
            if parsed_tool is not None:
                candidates.append((tool_start, "tool"))
            if think_match is not None:
                candidates.append((think_match.start(), "think"))

            if not candidates:
                break

            candidates.sort()
            next_start, match_type = candidates[0]

            before = remaining[:next_start]
            if before.strip():
                blocks.append(TextBlock(content=before))

            if match_type == "tool":
                assert parsed_tool is not None
                tool_name = parsed_tool["name"]
                span_end = parsed_tool["span"][1]
                if tool_name:
                    blocks.append(MsgToolCall(
                        id=f"legacy-{legacy_id}",
                        name=tool_name,
                        arguments=parsed_tool["arguments"],
                        status=LifecycleStatus.COMPLETE,
                    ))
                    legacy_id += 1
                remaining = remaining[span_end:]
            else:
                assert think_match is not None
                blocks.append(ThinkBlock(content=think_match.group(1)))
                remaining = remaining[think_match.end():]

        if remaining.strip():
            blocks.append(TextBlock(content=remaining))

        return blocks

    def send_notification(self, method: str, params: dict):
        """Send a JSONRPC notification to A2TUI."""
        try:
            notification = {"jsonrpc": "2.0", "method": method, "params": params}
            print(json.dumps(notification), flush=True)
        except (TypeError, ValueError, OSError) as e:
            _dump_crash("send_notification")
            debug_log("send_notification failed: %s", e)

    def send_request(self, method: str, params: dict) -> asyncio.Future[dict]:
        """Send a JSONRPC request to A2TUI and return a Future for the response."""
        self._request_seq += 1
        req_id = f"svr_{self._request_seq}"
        future: asyncio.Future[dict] = asyncio.Future()
        self._pending_requests[req_id] = future
        request = {"jsonrpc": "2.0", "method": method, "params": params, "id": req_id}
        try:
            print(json.dumps(request), flush=True)
        except (TypeError, ValueError, OSError) as e:
            _dump_crash("send_request")
            debug_log("send_request failed: %s", e)
            if not future.done():
                future.set_exception(e)
        return future

    def resolve_pending_request(self, req_id: str, result: dict) -> bool:
        """Resolve a pending request with the given result. Returns True if found."""
        future = self._pending_requests.pop(req_id, None)
        if future is not None and not future.done():
            future.set_result(result)
            return True
        return False

    def cancel_prompt(self):
        """Synchronously cancel the current prompt (called from main loop)."""
        if self.agent:
            self.agent._cancelled = True
            for child in self.agent._child_engines:
                child._cancelled = True

    def resolve_ask_user(self, answer: str, cancelled: bool) -> dict:
        """Resolve the pending ask_user request with the user's answer.

        Called from the main loop when a ``session/ask_user_answer`` request arrives.
        """
        if self._ask_user_future is not None and not self._ask_user_future.done():
            self._ask_user_future.set_result({"answer": answer, "cancelled": cancelled})
        return {"ok": True}

    def send_session_update(self, update: dict):
        """Send a session/update notification with proper ACP protocol format."""
        self.send_notification("session/update", {
            "sessionId": self.session_id,
            "update": update,
        })

    def _emit_tool_result(self, block: ToolResult) -> None:
        """Send a tool_result as a tool_call_update, accumulating with existing content."""
        # Look up tool name from the tracked tool_calls entry
        tool_name = self.tool_calls.get(block.tool_use_id, {}).get("title", "")
        # Title may be like "Bash: ls -la" — keep just the leading tool name
        if tool_name and ":" in tool_name:
            tool_name = tool_name.split(":", 1)[0].strip()
        display_text = _format_tui_display_text(block.content, tool_name)

        # Update title with path/subject from result if not already set
        if block.content and block.tool_use_id in self.tool_calls:
            try:
                parsed = json.loads(block.content)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(parsed, dict) and parsed.get("success") is True:
                    current_title = self.tool_calls[block.tool_use_id].get("title", "")
                    if ":" not in current_title:
                        if tool_name in ("TodoCreate", "TodoUpdate"):
                            task_info = parsed.get("task", {})
                            if isinstance(task_info, dict):
                                if subject := task_info.get("subject", ""):
                                    self.tool_calls[block.tool_use_id]["title"] = f"{current_title}: {subject}"
                                elif path := parsed.get("path"):
                                    self.tool_calls[block.tool_use_id]["title"] = f"{current_title}: {_short_path(path, self.agent._project_dir)}"
                        elif path := parsed.get("path"):
                            self.tool_calls[block.tool_use_id]["title"] = f"{current_title}: {_short_path(path, self.agent._project_dir)}"

        # Wrap multi-line results in a fenced code block for proper rendering.
        # Use bash-style fence for Bash/Glob, detect language for Read.
        if display_text and "\n" in display_text and "```" not in display_text:
            lang = ""
            tool_info = self.tool_calls.get(block.tool_use_id, {})
            tname = tool_info.get("_tool_name", "")
            targs = tool_info.get("_tool_args", {})
            if tname in ("Bash", "Glob"):
                lang = "bash"
            elif tname == "Read" and isinstance(targs, dict):
                path = str(targs.get("path", ""))
                if path:
                    lang = _language_for_path(path)
            if lang:
                display_text = f"```{lang}\n{display_text}\n```"
            else:
                display_text = f"```\n{display_text}\n```"

        content_block = [{
            "type": "content",
            "content": {"type": "text", "text": display_text},
        }] if display_text else []
        existing = self.tool_calls.get(block.tool_use_id, {}).get("content", [])
        update = {
            "sessionUpdate": "tool_call_update",
            "toolCallId": block.tool_use_id,
            "status": "failed" if block.is_error else "completed",
            "content": existing + content_block,
        }
        if block.tool_use_id in self.tool_calls:
            self.tool_calls[block.tool_use_id].update(update)
        else:
            self.tool_calls[block.tool_use_id] = {
                "sessionUpdate": "tool_call",
                "toolCallId": block.tool_use_id,
                "title": "Tool call",
                "kind": "other",
                **update,
            }
        self.send_session_update(self.tool_calls[block.tool_use_id])

    def _replay_tool_or_subagent(self, tool_use_id: str, content: str, is_error: bool) -> None:
        """Replay a tool result — subagent events for Task, tool_call_update otherwise."""
        tc = self.tool_calls.get(tool_use_id)
        if tc and tc.get("_tool_name") == "Spawn":
            args = tc.get("_tool_args", {})
            agent_type = args.get("agent_type", "general")
            prompt = args.get("prompt", "")
            self.send_session_update({
                "sessionUpdate": "subagent_start",
                "subagentId": tool_use_id,
                "agentType": agent_type,
                "prompt": prompt,
            })
            if content:
                self.send_session_update({
                    "sessionUpdate": "subagent_chunk",
                    "subagentId": tool_use_id,
                    "text": content,
                })
            self.send_session_update({
                "sessionUpdate": "subagent_end",
                "subagentId": tool_use_id,
                "agentType": agent_type,
            })
        else:
            tr = ToolResult(
                tool_use_id=tool_use_id,
                content=content,
                is_error=is_error,
            )
            self._emit_tool_result(tr)

    async def initialize(self, protocol_version: int, client_capabilities: dict, client_info: dict):
        """Handle ACP initialize."""
        return {
            "protocolVersion": 1,
            "agentCapabilities": {
                "loadSession": True,
                "promptCapabilities": {
                    "audio": False,
                    "embeddedContent": True,
                    "image": True,
                },
            },
            "authMethods": [],
            "serverInfo": {
                "name": "cdh-agent",
                "title": "CDH Agent",
                "version": "1.0.0",
            },
        }

    def _send_available_commands(self) -> None:
        """Send slash commands available in the current agent mode."""
        self.send_session_update({
            "sessionUpdate": "available_commands_update",
            "availableCommands": [
                {"name": "exit", "description": "Exit A2TUI", "input": None},
                {"name": "permission", "description": "Clear permission overrides (use `/permission edit` for specific key)", "input": None},
            ],
        })

    async def session_new(self, cwd: str, mcp_servers: list):
        """Create new session."""
        cfg = load_config()
        self.agent = _create_engine(cwd, perm_store=self._perm_store)
        self.agent.set_agent(cfg.default_mode)
        self._perm_store_load()
        self._perm_store.apply_to(self.agent.current_agent)

        session = AgentSession()
        session.name = "New Session"
        session.mode = cfg.default_mode
        session.project = str(Path(cwd).resolve() if cwd else Path.cwd())
        session.model = cfg.default_model
        session.provider = cfg.default_provider
        session.save()
        self.agent.attach_session(session)
        self.session_id = session.id

        # Restore tasks from project .cdh/ if available
        self.agent.load_tasks_from_project()

        self._send_available_commands()

        return {
            "sessionId": self.session_id,
            "modes": {
                "currentModeId": cfg.default_mode,
                "availableModes": _DEFAULT_MODES["availableModes"],
            },
        }

    async def session_load(self, cwd: str, mcp_servers: list, session_id: str):
        """Load existing session."""
        self._perm_store_load(cwd)
        self.agent = _create_engine(cwd, perm_store=self._perm_store)
        self.session_id = session_id

        loaded = self.agent.load_session(session_id)
        cfg = load_config()
        self.agent.set_agent(cfg.default_mode)
        self._perm_store.apply_to(self.agent.current_agent)
        self._send_available_commands()

        # Also restore tasks from project .cdh/ as fallback / supplement
        self.agent.load_tasks_from_project()

        if not loaded:
            return {"modes": _DEFAULT_MODES}

        # Walk the in-memory context (preserves list-of-blocks structure)
        # instead of the raw _session.messages dicts, which only carry
        # `content: str`.  Engine.chat_stream() stores tool_use / tool_result
        # blocks in context.Message.content, and we need them at replay time.
        for ctx_msg in self.agent.context.messages:
            role = ctx_msg.role
            content = ctx_msg.content
            if role == "user":
                user_text = content if isinstance(content, str) else _extract_text_from_blocks(content)
                self.send_session_update({
                    "sessionUpdate": "user_message_chunk",
                    "content": {"type": "text", "text": user_text},
                })
            elif role == "assistant":
                if isinstance(content, str):
                    blocks = self._content_to_blocks(content)
                else:
                    blocks = self._content_to_blocks(content)

                for block in blocks:
                    if isinstance(block, TextBlock):
                        filtered_text = _filter_tool_call_text(block.content)
                        if filtered_text.strip():
                            self.send_session_update({
                                "sessionUpdate": "agent_message_chunk",
                                "content": {"type": "text", "text": filtered_text},
                            })
                    elif isinstance(block, ThinkBlock):
                        filtered_thought = _filter_tool_call_text(block.content)
                        if filtered_thought.strip():
                            self.send_session_update({
                                "sessionUpdate": "agent_thought_chunk",
                                "content": {"type": "text", "text": filtered_thought},
                            })
                    elif isinstance(block, MsgToolCall):
                        tool_kind = _kind_for_category(get_tool_category(block.name))
                        content_blocks = _build_tool_call_content(
                            block.name, block.arguments or {}
                        )
                        title = block.name
                        args = block.arguments or {}
                        if path := args.get("path", ""):
                            title = f"{block.name}: {_short_path(path, self.agent._project_dir)}"
                        elif block.name == "Bash":
                            cmd = str(args.get("command", ""))
                            title = f"Bash: {cmd}"
                        elif block.name == "TodoCreate":
                            subject = str(args.get("subject", ""))
                            if subject:
                                title = f"TodoCreate: {subject}"
                        elif block.name == "TodoUpdate":
                            subject = str(args.get("subject", ""))
                            if subject:
                                title = f"TodoUpdate: {subject}"
                        elif block.name in ("TodoGet", "TodoStop", "TodoOutput"):
                            tid = str(args.get("taskId", args.get("task_id", "")))
                            if tid:
                                title = f"{block.name}: {tid}"
                        elif block.name == "Glob":
                            pattern = str(args.get("pattern", ""))
                            if pattern:
                                title = f"Glob: {pattern}"
                        self.tool_calls[block.id] = {
                            "sessionUpdate": "tool_call",
                            "toolCallId": block.id,
                            "title": title,
                            "kind": tool_kind,
                            "status": _wire_status(block.status.value),
                            "content": content_blocks,
                            "_tool_name": block.name,
                            "_tool_args": block.arguments or {},
                        }
                        # Skip sending tool_call for Task tools — SubAgent widget
                        # is rendered via subagent_start/subagent_chunk/subagent_end
                        # when the corresponding tool_result is processed below.
                        if block.name != "Spawn":
                            self.send_session_update(self.tool_calls[block.id])
                    elif isinstance(block, ToolResult):
                        self._emit_tool_result(block)
                    elif isinstance(block, SubAgentBlock):
                        content_block = [{
                            "type": "content",
                            "content": {"type": "text", "text": block.result},
                        }] if block.result else []
                        self.send_session_update({
                            "sessionUpdate": "subagent_start",
                            "subagentId": block.id,
                            "agentType": block.agent_type,
                            "prompt": block.prompt,
                        })
                        if block.result:
                            self.send_session_update({
                                "sessionUpdate": "subagent_chunk",
                                "subagentId": block.id,
                                "text": block.result,
                            })
                        self.send_session_update({
                            "sessionUpdate": "subagent_end",
                            "subagentId": block.id,
                            "agentType": block.agent_type,
                        })
            elif role == "tool":
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_result":
                            self._replay_tool_or_subagent(
                                item.get("tool_use_id", ""),
                                item.get("content", ""),
                                item.get("is_error", False),
                            )
                elif isinstance(content, dict) and content.get("type") == "tool_result":
                    self._replay_tool_or_subagent(
                        content.get("tool_use_id", ""),
                        content.get("content", ""),
                        content.get("is_error", False),
                    )

        return {
            "modes": {
                "currentModeId": cfg.default_mode,
                "availableModes": _DEFAULT_MODES["availableModes"],
            },
        }

    def _make_stream_callback(self):
        """Create a thinking-aware streaming callback for real-time token output.

        Buffers text deltas from the provider, detects <thinking>...</thinking>,
        [TOOL_CALL]...[/TOOL_CALL], <minimax:tool_call>...</minimax:tool_call>,
        and bare `{tool => "X", args => { ... }}` boundaries (all cross-chunk
        tolerant), strips them from the text buffer so they don't appear as
        raw agent messages, and routes remaining content to the appropriate
        ACP session update type.

        Tool call notifications are sent by TOOL_CALL_START/TOOL_CALL_COMPLETE
        events from the engine, not from text parsing here.
        """
        # Safety cap on the held buffer: if a model emits an unclosed
        # ``<thinking>`` / ``[TOOL_CALL]`` / ``<minimax:tool_call>`` tag
        # and then the stream is truncated (network drop, cancel,
        # provider error before the close marker arrives), the buffer
        # would otherwise grow forever and every subsequent chunk
        # would be silently swallowed.  When the buffer exceeds this
        # cap we give up on detecting markers and flush the held text
        # as a plain message so the user still sees *something*.
        _MAX_HELD_BYTES = 64 * 1024

        chunker = getattr(self, "_text_chunker", None)
        _direct_send = self.send_session_update  # fallback when chunker not configured
        text_buffer = ""
        in_thinking = False
        in_tool_call = False
        in_minimax_tool_call = False
        in_bare_tool_call = False
        bare_tool_start = 0
        thinking_sent_len = 0  # how much of text_buffer has been sent to TUI

        def _flush_held_buffer() -> None:
            """Force-emit the held buffer as a plain message and reset
            all "in marker" flags.  Used by the watchdog below and by
            the early-exit path when a turn ends without a close
            marker.
            """
            nonlocal text_buffer, thinking_sent_len
            nonlocal in_thinking, in_tool_call
            nonlocal in_minimax_tool_call, in_bare_tool_call, bare_tool_start
            if chunker:
                chunker.flush()
            if text_buffer.strip():
                _direct_send({
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": text_buffer},
                })
            text_buffer = ""
            thinking_sent_len = 0
            in_thinking = in_tool_call = False
            in_minimax_tool_call = in_bare_tool_call = False
            bare_tool_start = 0

        def _emit_message(text: str) -> None:
            if not text:
                return
            if chunker:
                chunker.append(text)
            else:
                _direct_send({
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": text},
                })

        def _safe_start(s: str) -> str:
            """Return text before any partial <thinking / <think or [TOOL_CALL] or
            <minimax:tool_call> tag at buffer end."""
            tags = ("<thinking>", "<think>", "[TOOL_CALL]", _MINIMAX_OPEN)
            cut = len(s)
            for tag in tags:
                for i in range(len(tag) - 1, 0, -1):
                    if s.endswith(tag[:i]):
                        cut = min(cut, len(s) - i)
                        break
            return s[:cut]

        def on_chunk(text: str):
            nonlocal text_buffer, thinking_sent_len, in_thinking, in_tool_call
            nonlocal in_minimax_tool_call, in_bare_tool_call, bare_tool_start
            text_buffer += text

            # Watchdog: if a marker opened but the close never arrived
            # and the buffer has grown past the safety cap, give up
            # and emit the held text as a plain message.  The model
            # is either malformed or the stream was truncated; either
            # way the user should see *something* rather than a
            # silently held buffer that never resolves.
            if (
                in_thinking
                or in_tool_call
                or in_minimax_tool_call
                or in_bare_tool_call
            ) and len(text_buffer) > _MAX_HELD_BYTES:
                _flush_held_buffer()
                # After flushing, fall through into the normal
                # scanning loop on the now-empty buffer.

            while text_buffer:
                if in_thinking:
                    close_thinking = text_buffer.find("</thinking>")
                    close_think = (
                        text_buffer.find("</think>")
                        if close_thinking < 0 else -1
                    )
                    idx = close_thinking if close_thinking >= 0 else close_think
                    close_len = (
                        len("</thinking>") if close_thinking >= 0
                        else len("</think>") if close_think >= 0 else 0
                    )
                    if idx >= 0:
                        thinking = text_buffer[:idx]
                        if thinking:
                            # Send any remaining partial before the close
                            if thinking_sent_len < len(thinking):
                                partial = thinking[thinking_sent_len:]
                                self.send_session_update({
                                    "sessionUpdate": "agent_thought_chunk",
                                    "content": {"type": "text", "text": partial},
                                })
                            # Persist COMPLETE thinking to engine context
                            on_thinking = getattr(self.agent, "on_thinking", None)
                            if on_thinking is not None:
                                try:
                                    on_thinking(thinking)
                                except Exception:
                                    debug_log("on_thinking callback failed", exc_info=True)
                        text_buffer = text_buffer[idx + close_len:]
                        thinking_sent_len = 0
                        in_thinking = False
                    else:
                        # Stream partial thinking content incrementally to TUI
                        if thinking_sent_len < len(text_buffer):
                            partial = text_buffer[thinking_sent_len:]
                            self.send_session_update({
                                "sessionUpdate": "agent_thought_chunk",
                                "content": {"type": "text", "text": partial},
                            })
                            thinking_sent_len = len(text_buffer)
                        break
                elif in_tool_call:
                    close_idx = text_buffer.find(_CLOSE_MARKER)
                    if close_idx < 0:
                        # No close marker yet — hold the whole buffer.
                        break
                    # Strip [TOOL_CALL]...[/TOOL_CALL] from text buffer.
                    # The engine emits TOOL_CALL_START/COMPLETE separately.
                    text_buffer = text_buffer[close_idx + len(_CLOSE_MARKER):]
                    in_tool_call = False
                elif in_minimax_tool_call:
                    close_idx = text_buffer.find(_MINIMAX_CLOSE)
                    if close_idx < 0:
                        # No close marker yet — hold the whole buffer.
                        break
                    # Strip <minimax:tool_call>...</minimax:tool_call> from
                    # the text buffer.  The engine emits the structured
                    # TOOL_CALL_START/COMPLETE events separately.
                    text_buffer = text_buffer[close_idx + len(_MINIMAX_CLOSE):]
                    in_minimax_tool_call = False
                elif in_bare_tool_call:
                    m = _BARE_LEGACY_RE.match(text_buffer, bare_tool_start)
                    if m is None:
                        # Pattern got invalidated — discard the held span.
                        text_buffer = text_buffer[bare_tool_start:]
                        in_bare_tool_call = False
                        bare_tool_start = 0
                        break
                    args_open = text_buffer.find("{", m.end() - 1)
                    if args_open < 0:
                        break
                    args_close = _scan_balanced_braces(text_buffer, args_open)
                    if args_close is None:
                        # Need more chunks to close the inner args.
                        break
                    outer_close = _scan_balanced_braces(text_buffer, bare_tool_start)
                    if outer_close is None or outer_close <= args_close:
                        break
                    text_buffer = text_buffer[outer_close + 1:]
                    in_bare_tool_call = False
                    bare_tool_start = 0
                else:
                    tc_idx = text_buffer.find(_OPEN_MARKER)
                    minimax_idx = text_buffer.find(_MINIMAX_OPEN)
                    think_idx = text_buffer.find("<thinking>")
                    if think_idx < 0:
                        think_short_idx = text_buffer.find("<think>")
                    else:
                        think_short_idx = -1
                    bare_idx = _find_bare_legacy_tool_call(text_buffer)

                    # Pick the earliest opener among all known markers.
                    candidates: list[tuple[int, str]] = []
                    if tc_idx >= 0:
                        candidates.append((tc_idx, "legacy"))
                    if minimax_idx >= 0:
                        candidates.append((minimax_idx, "minimax"))
                    if think_idx >= 0:
                        candidates.append((think_idx, "think"))
                    if think_short_idx >= 0:
                        candidates.append((think_short_idx, "think_short"))
                    if bare_idx is not None:
                        candidates.append((bare_idx, "bare"))

                    if not candidates:
                        safe = _safe_start(text_buffer)
                        if safe:
                            _emit_message(safe)
                        text_buffer = text_buffer[len(safe):]
                        if not _safe_start(text_buffer):
                            text_buffer = ""
                        continue

                    candidates.sort()
                    next_idx, kind = candidates[0]

                    if next_idx > 0:
                        _emit_message(text_buffer[:next_idx])

                    if kind == "minimax":
                        text_buffer = text_buffer[next_idx + len(_MINIMAX_OPEN):]
                        in_minimax_tool_call = True
                    elif kind == "legacy":
                        text_buffer = text_buffer[next_idx + len(_OPEN_MARKER):]
                        in_tool_call = True
                    elif kind in ("think", "think_short"):
                        tag_len = len("<thinking>") if kind == "think" else len("<think>")
                        text_buffer = text_buffer[next_idx + tag_len:]
                        in_thinking = True
                    else:
                        # Bare legacy: peek whether the closing brace is
                        # already in the buffer.
                        m = _BARE_LEGACY_RE.match(text_buffer, next_idx)
                        args_open = text_buffer.find("{", m.end() - 1) if m else -1
                        args_close = (
                            _scan_balanced_braces(text_buffer, args_open)
                            if args_open >= 0 else None
                        )
                        outer_close = (
                            _scan_balanced_braces(text_buffer, next_idx)
                            if args_close is not None else None
                        )
                        if (
                            m is not None and args_open >= 0
                            and args_close is not None
                            and outer_close is not None
                            and outer_close > args_close
                        ):
                            text_buffer = text_buffer[outer_close + 1:]
                        else:
                            in_bare_tool_call = True
                            bare_tool_start = next_idx
                            break

        return on_chunk

    async def session_prompt(self, prompt: list, session_id: str):
        """Send prompt to agent and stream results."""
        if self.agent is None:
            debug_log("session_prompt called but self.agent is None")
            return {"stopReason": "error", "message": "No agent initialized"}

        debug_log(
            "session_prompt start session=%s prompt_blocks=%d",
            session_id, len(prompt),
        )

        # Collect ALL content blocks from the prompt (text, resource, etc.)
        # instead of only extracting the text portion.
        user_content: list[dict] = []
        for block in prompt:
            btype = block.get("type", "text")
            if btype == "text":
                user_content.append(block)
            elif btype == "resource":
                user_content.append(block)
            elif btype == "image":
                user_content.append(block)
            else:
                # Pass through unknown types, the context layer will handle them
                user_content.append(block)

        # ── Slash-command handling ─────────────────────────────
        if user_content and user_content[0].get("type") == "text":
            text = user_content[0].get("text", "").strip()
            if text == "/permission":
                return self._handle_reset_permission()
            if text.startswith("/permission "):
                key = text.split("/permission ", 1)[1].strip()
                return self._handle_reset_permission(key)

        # Fresh per-turn tracking (tool_calls accumulates across one turn only)
        self.tool_calls = {}
        self.agent._cancelled = False

        # Create chunkers for agent_message_chunk and agent_thought_chunk
        self._text_chunker = TextChunker(
            send_fn=lambda text: self.send_session_update({
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": text},
            }),
            mode="auto",
            words=5,
        )
        self._thought_chunker = TextChunker(
            send_fn=lambda text: self.send_session_update({
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": "text", "text": text},
            }),
            mode="auto",
            words=5,
        )
        self.agent.on_text_chunk = self._make_stream_callback()
        # Persist thinking blocks into the engine's context so they survive
        # session reload (otherwise the TUI only sees them during streaming).
        self.agent.on_thinking = lambda text: self.agent._pending_thinking_blocks.append(text)

        # Track in-progress tool call args for incremental display
        _incremental_args: dict[str, str] = {}
        _last_sent_len: dict[str, int] = {}
        _ARGS_THROTTLE_CHARS = 50

        def _on_tool_call_delta(call_id: str, name: str, args_delta: str) -> None:
            # Skip Spawn — SubAgent widget handles display via subagent_* events
            if name == "Spawn":
                return
            if args_delta:
                _incremental_args[call_id] = _incremental_args.get(call_id, "") + args_delta
                display_args = _incremental_args[call_id]
                # Throttle: only send when accumulated enough new chars
                if len(display_args) - _last_sent_len.get(call_id, 0) < _ARGS_THROTTLE_CHARS:
                    return
                _last_sent_len[call_id] = len(display_args)
                try:
                    parsed = json.loads(display_args)
                    display_text = json.dumps(parsed, indent=2, ensure_ascii=False)
                except (json.JSONDecodeError, TypeError):
                    display_text = display_args
                self.send_session_update({
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": call_id,
                    "title": name or "Tool call",
                    "status": "in_progress",
                    "content": [{
                        "type": "content",
                        "content": {"type": "text", "text": f"```json\n{display_text}\n```"},
                    }] if display_text else [],
                })

        self.agent.on_tool_call_delta = _on_tool_call_delta
        try:
            async for event in self.agent.chat_stream(user_content):
                if event.type == StreamEventType.TEXT_DELTA:
                    self._text_chunker.append(event.text)
                elif event.type == StreamEventType.THINKING:
                    self._thought_chunker.append(event.thinking)
                elif event.type == StreamEventType.TOOL_CALL_START:
                    self._text_chunker.flush()
                    self._thought_chunker.flush()
                    tool_kind = _kind_for_category(event.tool_category)
                    existing = self.tool_calls.get(event.tool_id, {})
                    self.tool_calls[event.tool_id] = {
                        "sessionUpdate": "tool_call",
                        "toolCallId": event.tool_id,
                        "title": event.tool_name,
                        "kind": tool_kind,
                        "status": "in_progress",
                        "content": existing.get("content", []),
                        "_tool_name": event.tool_name,
                    }
                        # Skip sending tool_call for Spawn tools — SubAgent widget
                    # handles the display via subagent_start events.
                    if event.tool_name != "Spawn":
                        self.send_session_update(self.tool_calls[event.tool_id])
                elif event.type == StreamEventType.TOOL_CALL_COMPLETE:
                    if event.tool_id in self.tool_calls:
                        title = event.tool_name
                        if event.tool_args:
                            if path := event.tool_args.get("path", ""):
                                title = f"{event.tool_name}: {_short_path(path, self.agent._project_dir)}"
                            elif event.tool_name == "Bash":
                                cmd = str(event.tool_args.get("command", ""))
                                title = f"Bash: {cmd}"
                            elif event.tool_name == "TodoCreate":
                                subject = str(event.tool_args.get("subject", ""))
                                if subject:
                                    title = f"TodoCreate: {subject}"
                            elif event.tool_name == "TodoUpdate":
                                subject = str(event.tool_args.get("subject", ""))
                                if subject:
                                    title = f"TodoUpdate: {subject}"
                            elif event.tool_name in ("TodoGet", "TodoStop", "TodoOutput"):
                                tid = str(event.tool_args.get("taskId", event.tool_args.get("task_id", "")))
                                if tid:
                                    title = f"{event.tool_name}: {tid}"
                            elif event.tool_name == "Glob":
                                pattern = str(event.tool_args.get("pattern", ""))
                                if pattern:
                                    title = f"Glob: {pattern}"
                            content = _build_tool_call_content(
                                event.tool_name, event.tool_args
                            )
                            debug_log(
                                "TOOL_CALL_COMPLETE %s id=%s args_keys=%s title=%s content_blocks=%d",
                                event.tool_name, event.tool_id,
                                list(event.tool_args.keys()), title,
                                len(content),
                            )
                        else:
                            content = []
                            debug_log(
                                "TOOL_CALL_COMPLETE %s id=%s NO args",
                                event.tool_name, event.tool_id,
                            )
                        self.tool_calls[event.tool_id].update({
                            "sessionUpdate": "tool_call_update",
                            "toolCallId": event.tool_id,
                            "title": title,
                            "status": "pending",
                            "content": content,
                            "_tool_name": event.tool_name,
                            "_tool_args": event.tool_args,
                        })
                        # Skip sending tool_call_update for Spawn — SubAgent widget
                        # handles the display via subagent_start/chunk/end events.
                        if event.tool_name != "Spawn":
                            self.send_session_update(self.tool_calls[event.tool_id])
                elif event.type == StreamEventType.TOOL_RESULT:
                    # Spawn tool results: subagent_start/chunk/end events were
                    # already sent during subagent execution — just skip the
                    # tool_call_update (no duplicate SubAgent widget needed).
                    tname = self.tool_calls.get(event.tool_id, {}).get("_tool_name", "")
                    if tname == "Spawn":
                        try:
                            self.agent.save_session()
                        except Exception:
                            debug_log("Failed to save session after subagent", exc_info=True)
                        continue
                    status = "failed" if event.result_is_error else "completed"
                    display_text = _format_tui_display_text(
                        event.result_content or "", tname,
                    )

                    # Update title with path/subject from result if not already set
                    if event.result_content and event.tool_id in self.tool_calls:
                        try:
                            parsed = json.loads(event.result_content)
                        except json.JSONDecodeError:
                            pass
                        else:
                            if isinstance(parsed, dict) and parsed.get("success") is True:
                                current_title = self.tool_calls[event.tool_id].get("title", "")
                                if ":" not in current_title:
                                    tname = self.tool_calls[event.tool_id].get("_tool_name", "")
                                    if tname in ("TodoCreate", "TodoUpdate"):
                                        task_info = parsed.get("task", {})
                                        if isinstance(task_info, dict):
                                            if subject := task_info.get("subject", ""):
                                                self.tool_calls[event.tool_id]["title"] = f"{current_title}: {subject}"
                                            elif path := parsed.get("path"):
                                                self.tool_calls[event.tool_id]["title"] = f"{current_title}: {_short_path(path, self.agent._project_dir)}"
                                    elif path := parsed.get("path"):
                                        self.tool_calls[event.tool_id]["title"] = f"{current_title}: {_short_path(path, self.agent._project_dir)}"

                    # Add "denied" hint for reject-always overrides
                    if event.result_is_error and display_text and "denied" in display_text:
                        display_text += "\n\n💡 Use `/permission` to clear a 'reject always' override."

                    # TUI now renders all text content as Markdown.
                    # Wrap multi-line results in a fenced code block so they
                    # display as a code block rather than a raw paragraph.
                    # For Read results, detect language from the file path.
                    # For Bash/Glob, use bash-style fence.
                    # Skip if already contains a code fence to avoid nesting.
                    if display_text and "\n" in display_text and "```" not in display_text:
                        lang = ""
                        tool_info = self.tool_calls.get(event.tool_id, {})
                        tname = tool_info.get("_tool_name", "")
                        targs = tool_info.get("_tool_args", {})
                        if tname in ("Bash", "Glob"):
                            lang = "bash"
                        elif tname == "Read" and isinstance(targs, dict):
                            path = str(targs.get("path", ""))
                            if path:
                                lang = _language_for_path(path)
                        if lang:
                            display_text = f"```{lang}\n{display_text}\n```"
                        else:
                            display_text = f"```\n{display_text}\n```"
                    content_block = [{
                        "type": "content",
                        "content": {"type": "text", "text": display_text},
                    }] if display_text else []
                    existing_content = self.tool_calls.get(event.tool_id, {}).get("content", [])
                    if not isinstance(existing_content, list):
                        existing_content = []
                    debug_log(
                        "TOOL_RESULT id=%s status=%s result_len=%d display_len=%d existing_blocks=%d new_blocks=%d",
                        event.tool_id, status,
                        len(event.result_content or ""), len(display_text),
                        len(existing_content), len(content_block),
                    )
                    update = {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": event.tool_id,
                        "status": status,
                        "content": existing_content + content_block,
                    }
                    if event.tool_id in self.tool_calls:
                        self.tool_calls[event.tool_id].update(update)
                    else:
                        self.tool_calls[event.tool_id] = {
                            "sessionUpdate": "tool_call",
                            "toolCallId": event.tool_id,
                            "title": "Tool call",
                            "kind": "other",
                            "status": status,
                            **update,
                        }
                    self.send_session_update(self.tool_calls[event.tool_id])
                    try:
                        self.agent.save_session()
                    except Exception:
                        debug_log("Failed to save session after tool result", exc_info=True)
                elif event.type == StreamEventType.ERROR:
                    self._text_chunker.flush()
                    self._thought_chunker.flush()
                    self.send_session_update({
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": f"Error: {event.error_message}"},
                    })
                    try:
                        self.agent.save_session()
                    except Exception:
                        debug_log("Failed to save session on error", exc_info=True)
                    return {"stopReason": "error", "message": event.error_message}
                elif event.type == StreamEventType.SUBAGENT_START:
                    self._text_chunker.flush()
                    self._thought_chunker.flush()
                    self.send_session_update({
                        "sessionUpdate": "subagent_start",
                        "subagentId": event.subagent_id,
                        "agentType": event.subagent_type,
                        "prompt": event.subagent_prompt,
                    })
                elif event.type == StreamEventType.SUBAGENT_CHUNK:
                    self.send_session_update({
                        "sessionUpdate": "subagent_chunk",
                        "subagentId": event.subagent_id,
                        "text": event.subagent_text,
                    })
                elif event.type == StreamEventType.SUBAGENT_THINKING:
                    self.send_session_update({
                        "sessionUpdate": "subagent_thinking",
                        "subagentId": event.subagent_id,
                        "text": event.subagent_thinking_text,
                    })
                elif event.type == StreamEventType.SUBAGENT_END:
                    self.send_session_update({
                        "sessionUpdate": "subagent_end",
                        "subagentId": event.subagent_id,
                        "agentType": event.subagent_type,
                        "status": event.subagent_status,
                        "error": event.subagent_error,
                    })
                elif event.type == StreamEventType.PLAN:
                    self.send_session_update({
                        "sessionUpdate": "plan",
                        "entries": event.plan_entries,
                    })
                elif event.type == StreamEventType.ASK_USER:
                    self._text_chunker.flush()
                    self._thought_chunker.flush()

                    # Handle AskUser tool — show question inline via session/update notification
                    if event.ask_action == "AskUser":
                        if event.ask_questions:
                            self.send_session_update({
                                "sessionUpdate": "ask_user",
                                "questions": event.ask_questions,
                                "context": event.ask_context or "",
                                "toolId": event.tool_id,
                            })
                        else:
                            self.send_session_update({
                                "sessionUpdate": "ask_user",
                                "question": event.ask_question,
                                "context": event.ask_context or "",
                                "options": event.ask_options,
                                "toolId": event.tool_id,
                            })
                        answer = ""
                        cancelled = False
                        # AskUser re-ask flow:
                        #   1) send full question, wait up to 60s for response
                        #   2) on timeout: send brief "请确认" reminder, wait 60s
                        #   3) on second timeout: use the default/best option
                        #      instead of cancelling, so the agent can keep going
                        #      with a sensible default choice.
                        _ASK_USER_REASK_TIMEOUT = 60
                        _no_response = False
                        for _attempt in range(2):
                            try:
                                self._ask_user_future = asyncio.get_event_loop().create_future()
                                ask_response = await asyncio.wait_for(
                                    self._ask_user_future,
                                    timeout=_ASK_USER_REASK_TIMEOUT,
                                )
                                answer = ask_response.get("answer", "")
                                cancelled = ask_response.get("cancelled", False)
                                _no_response = False
                                break
                            except (asyncio.TimeoutError, Exception):
                                if _attempt == 0:
                                    # Brief re-ask: do NOT resend the full question
                                    self.send_session_update({
                                        "sessionUpdate": "ask_user_remind",
                                        "text": "请确认？",
                                        "toolId": event.tool_id,
                                    })
                                    _no_response = True
                                    continue
                                # Second timeout: pick the default option
                                answer = self._pick_default_ask_user_answer(event)
                                cancelled = False
                                _no_response = True
                            finally:
                                self._ask_user_future = None
                        if _no_response and not cancelled and answer:
                            self.send_session_update({
                                "sessionUpdate": "ask_user_default_used",
                                "answer": answer,
                                "toolId": event.tool_id,
                            })
                        result = await self.agent.resolve_approval(
                            approved=not cancelled, answer=answer,
                        )
                        if result:
                            tid = result.get("tool_use_id", "") or event.tool_id
                            rstr = result.get("content", "") or ""
                            ierr = result.get("is_error", False)
                            self.agent.context.add_message(
                                "tool",
                                [{"type": "tool_result", "tool_use_id": tid,
                                  "content": rstr, "is_error": ierr}],
                                name=tid,
                            )
                            # Update TUI tool call status
                            status = "failed" if ierr else "completed"
                            content_block = [{
                                "type": "content",
                                "content": {"type": "text", "text": rstr},
                            }] if rstr else []
                            self.send_session_update({
                                "sessionUpdate": "tool_call_update",
                                "toolCallId": tid,
                                "status": status,
                                "content": content_block,
                            })
                        continue

                    # Build tool call content for the permission request
                    tool_kind = _kind_for_category(get_tool_category(event.ask_action))
                    pending = (self.agent._pending_approval or {}).get("tool_call", {})
                    tool_args = pending.get("input", {}) if pending else {}
                    tool_content = _build_tool_call_content(
                        event.ask_action, tool_args
                    ) if tool_args else []

                    # Prepend the question as a visible content block so the TUI
                    # permission dialog shows *what* the agent wants to do instead
                    # of an empty ``_meta`` that the TUI ignores.
                    question_block = {
                        "type": "content",
                        "content": {"type": "text", "text": f"❓ {event.ask_question}"},
                    }
                    tool_content = [question_block] + tool_content

                    # Guard against orphan permission requests: if the engine
                    # didn't supply a tool id, fall back to the pending approval
                    # id; if that's also empty, log and skip the request so the
                    # TUI doesn't render a dialog with no associated tool widget.
                    tool_call_id = event.tool_id or pending.get("id", "")
                    if not tool_call_id:
                        debug_log(
                            "ASK_USER skipped: no tool_id (action=%s question=%s)",
                            event.ask_action, event.ask_question,
                        )
                        continue

                    permission_params = {
                        "sessionId": session_id,
                        "options": [
                            {"name": "Allow once", "optionId": "allow_once", "kind": "allow_once"},
                            {"name": "Allow always", "optionId": "allow_always", "kind": "allow_always"},
                            {"name": "Reject once", "optionId": "reject_once", "kind": "reject_once"},
                            {"name": "Reject always", "optionId": "reject_always", "kind": "reject_always"},
                        ],
                        "toolCall": {
                            "toolCallId": tool_call_id,
                            "title": event.ask_action,
                            "kind": tool_kind,
                            "content": tool_content,
                            "status": "pending",
                        },
                    }
                    try:
                        perm_future = self.send_request(
                            "session/request_permission", permission_params
                        )
                        perm_response = await perm_future
                        outcome = perm_response.get("outcome", {})
                        option_id = outcome.get("optionId", "reject_once")
                        approved = option_id in ("allow_once", "allow_always")

                        if option_id == "allow_always":
                            from onecode.agent.agents.types import AgentPermission
                            perm_key = self.agent._TOOL_NAME_TO_PERM_KEY.get(event.ask_action)
                            if perm_key:
                                attr_name = f"permission_{perm_key}"
                                setattr(self.agent.current_agent, attr_name, AgentPermission.ALLOW)
                                self._perm_store.set_override(perm_key, AgentPermission.ALLOW)
                                self._perm_store_save()
                        elif option_id == "reject_always":
                            from onecode.agent.agents.types import AgentPermission
                            perm_key = self.agent._TOOL_NAME_TO_PERM_KEY.get(event.ask_action)
                            if perm_key:
                                attr_name = f"permission_{perm_key}"
                                setattr(self.agent.current_agent, attr_name, AgentPermission.DENY)
                                self._perm_store.set_override(perm_key, AgentPermission.DENY)
                                self._perm_store_save()
                    except Exception:
                        approved = False

                    result = await self.agent.resolve_approval(approved)
                    if result:
                        result_str = result.get("content", "") or ""
                        is_error = result.get("is_error", False)
                        tid = result.get("tool_use_id", "") or tool_call_id
                        status = "failed" if is_error else "completed"
                        content_block = [{
                            "type": "content",
                            "content": {"type": "text", "text": result_str},
                        }] if result_str else []
                        self.send_session_update({
                            "sessionUpdate": "tool_call_update",
                            "toolCallId": tid,
                            "status": status,
                            "content": content_block,
                        })
                        # Add result to LLM context
                        self.agent.context.add_message(
                            "tool",
                            [{"type": "tool_result", "tool_use_id": tid,
                              "content": result_str, "is_error": is_error}],
                            name=tid,
                        )
                    verb = "Approved" if approved else "Rejected"
                    self.send_session_update({
                        "sessionUpdate": "agent_message_chunk",
                        "content": {
                            "type": "text",
                            "text": f"⚡ {verb}: {event.ask_action} — {event.ask_question}",
                        },
                    })

        except Exception:
            import traceback
            tb = traceback.format_exc()
            _dump_crash("chat_stream")
            debug_log("Unhandled exception in chat_stream:\n%s", tb, exc_info=True)
            print(f"[cdh-agent-acp] ERROR in chat_stream:\n{tb}", file=sys.stderr, flush=True)
            self._text_chunker.flush()
            self._thought_chunker.flush()
            self.send_session_update({
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": f"Error: internal error"},
            })
            try:
                self.agent.save_session()
            except Exception:
                pass
            try:
                self.agent.save_tasks_to_project()
            except Exception:
                pass
            return {"stopReason": "error", "message": "Internal agent error"}

        self._text_chunker.flush()
        self._thought_chunker.flush()

        try:
            self.agent.save_session()
        except Exception:
            debug_log("Failed to save session at turn end", exc_info=True)

        # Persist tasks to project .cdh/ so they survive Ctrl+C
        try:
            self.agent.save_tasks_to_project()
        except Exception:
            debug_log("Failed to save tasks to .cdh at turn end", exc_info=True)

        # Send context usage stats to TUI sidebar
        ctx = self.agent.context
        used = ctx._token_count if ctx else 0
        size = ctx.config.max_tokens if ctx else 0
        self.send_session_update({
            "sessionUpdate": "usage_update",
            "used": used,
            "size": size,
        })

        # Tool call summary suppressed — internal step tracking
        # is not shown to avoid cluttering conversation output.

        stop_reason = "cancelled" if self.agent._cancelled else "end_turn"
        usage = self._build_session_usage()
        return {
            "sessionId": self.session_id,
            "stopReason": stop_reason,
            "usage": usage,
        }

    def _pick_default_ask_user_answer(self, event) -> str:
        """Pick the default answer for a timed-out AskUser prompt.

        Heuristic:
        - If a question has an option with ``default: true``, use it.
        - Otherwise pick the first option.
        - Multi-question prompts return a JSON string of ``{idx: value}``.
        - Single-question prompts return the option value as a plain string.
        - If the question has no options (free-text), return an empty string
          so the agent treats it as a no-op.
        """
        questions = getattr(event, "ask_questions", None) or []
        options = getattr(event, "ask_options", None) or []

        def _pick(opt_list: list) -> str:
            if not opt_list:
                return ""
            for opt in opt_list:
                if opt.get("default"):
                    return str(opt.get("value", ""))
            return str(opt_list[0].get("value", ""))

        if questions:
            answers = {str(i): _pick(q.get("options", [])) for i, q in enumerate(questions)}
            return json.dumps(answers)
        if options:
            return _pick(options)
        return ""

    def _build_session_usage(self) -> dict:
        """Aggregate per-turn usage from the engine into a single Usage dict.

        The TUI's ``tui/acp/protocol.py:SessionPromptResponse.usage`` is a
        free-form ``Usage`` object.  We sum the per-turn input/output/total
        tokens tracked by the engine; missing fields fall back to 0.
        """
        turn_usages = getattr(self.agent, "_turn_usages", None) or []
        if not turn_usages:
            return {
                "total_tokens": int(getattr(self.agent, "total_tokens", 0) or 0),
                "input_tokens": 0,
                "output_tokens": 0,
            }
        total_in = sum(int(u.get("input_tokens", 0) or 0) for u in turn_usages)
        total_out = sum(int(u.get("output_tokens", 0) or 0) for u in turn_usages)
        total_all = sum(int(u.get("total_tokens", 0) or 0) for u in turn_usages)
        if total_all == 0:
            total_all = total_in + total_out
        return {
            "total_tokens": total_all,
            "input_tokens": total_in,
            "output_tokens": total_out,
        }

    async def session_save(self, session_id: str, _meta: dict):
        """Save current session state."""
        if self.agent:
            try:
                self.agent.save_session()
            except Exception:
                debug_log("Failed to save session on save", exc_info=True)
        return {}

    async def session_cancel(self, session_id: str, _meta: dict):
        """Cancel current session."""
        if self.agent:
            await self.agent.cancel()
            try:
                self.agent.save_session()
            except Exception:
                debug_log("Failed to save session on cancel", exc_info=True)
            # Persist tasks to .cdh so they survive Ctrl+C and re-entry
            try:
                self.agent.save_tasks_to_project()
            except Exception:
                debug_log("Failed to save tasks to .cdh on cancel", exc_info=True)
        return {}

    async def session_set_mode(self, session_id: str, mode_id: str):
        """Set session mode — propagates to engine and notifies TUI."""
        if self.agent:
            self.agent.set_agent(mode_id)
            self._perm_store.apply_to(self.agent.current_agent)
            self.send_session_update({
                "sessionUpdate": "current_mode_update",
                "currentModeId": mode_id,
            })
            self._send_available_commands()
        return {"modeId": mode_id}

    # ── Terminal RPC stubs ──────────────────────────────────────────
    async def terminal_create(
        self, session_id: str, terminal_id: str, command: str, args: list[str] | None = None,
        cwd: str | None = None, env: dict | None = None, output_byte_limit: int | None = None,
    ) -> dict:
        return {"terminalId": terminal_id}

    async def terminal_kill(self, session_id: str, terminal_id: str) -> dict:
        return {}

    async def terminal_output(self, session_id: str, terminal_id: str) -> dict:
        return {"output": "", "truncated": False, "exitStatus": None}

    async def terminal_release(self, session_id: str, terminal_id: str) -> dict:
        return {}

    async def terminal_wait_for_exit(self, session_id: str, terminal_id: str) -> dict:
        return {"exitCode": 0, "signal": None}


class JSONRPCServer:
    def __init__(self, adapter: CDHACPAdapter):
        self.adapter = adapter
        self.methods = {
            "initialize": self._handle_initialize,
            "session/new": self._handle_session_new,
            "session/load": self._handle_session_load,
            "session/prompt": self._handle_session_prompt,
            "session/cancel": self._handle_session_cancel,
            "session/save": self._handle_session_save,
            "session/set_mode": self._handle_session_set_mode,
            "session/ask_user_answer": self._handle_ask_user_answer,
            "terminal/create": self._handle_terminal_create,
            "terminal/kill": self._handle_terminal_kill,
            "terminal/output": self._handle_terminal_output,
            "terminal/release": self._handle_terminal_release,
            "terminal/wait_for_exit": self._handle_terminal_wait_for_exit,
        }

    async def handle_request(self, request: dict):
        """Handle a JSONRPC request."""
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")

        handler = self.methods.get(method)
        if handler is None:
            return {"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Method not found: {method}"}, "id": req_id}

        try:
            result = await handler(params)
            return {"jsonrpc": "2.0", "result": result, "id": req_id}
        except Exception as e:
            return {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}, "id": req_id}

    async def _handle_initialize(self, params: dict):
        return await self.adapter.initialize(
            params.get("protocolVersion"),
            params.get("clientCapabilities", {}),
            params.get("clientInfo", {}),
        )

    async def _handle_session_new(self, params: dict):
        return await self.adapter.session_new(
            params.get("cwd", "."),
            params.get("mcpServers", []),
        )

    async def _handle_session_load(self, params: dict):
        return await self.adapter.session_load(
            params.get("cwd", "."),
            params.get("mcpServers", []),
            params.get("sessionId"),
        )

    async def _handle_session_save(self, params: dict):
        return await self.adapter.session_save(
            params.get("sessionId"),
            params.get("_meta", {}),
        )

    async def _handle_session_prompt(self, params: dict):
        return await self.adapter.session_prompt(
            params.get("prompt", []),
            params.get("sessionId"),
        )

    async def _handle_session_cancel(self, params: dict):
        return await self.adapter.session_cancel(
            params.get("sessionId"),
            params.get("_meta", {}),
        )

    async def _handle_ask_user_answer(self, params: dict):
        return self.adapter.resolve_ask_user(
            params.get("answer", ""),
            params.get("cancelled", True),
        )

    async def _handle_session_set_mode(self, params: dict):
        return await self.adapter.session_set_mode(
            params.get("sessionId"),
            params.get("modeId"),
        )

    async def _handle_terminal_create(self, params: dict):
        return await self.adapter.terminal_create(
            params.get("sessionId"),
            params.get("terminalId"),
            params.get("command"),
            params.get("args"),
            params.get("cwd"),
            params.get("env"),
            params.get("outputByteLimit"),
        )

    async def _handle_terminal_kill(self, params: dict):
        return await self.adapter.terminal_kill(
            params.get("sessionId"),
            params.get("terminalId"),
        )

    async def _handle_terminal_output(self, params: dict):
        return await self.adapter.terminal_output(
            params.get("sessionId"),
            params.get("terminalId"),
        )

    async def _handle_terminal_release(self, params: dict):
        return await self.adapter.terminal_release(
            params.get("sessionId"),
            params.get("terminalId"),
        )

    async def _handle_terminal_wait_for_exit(self, params: dict):
        return await self.adapter.terminal_wait_for_exit(
            params.get("sessionId"),
            params.get("terminalId"),
        )


async def _main():
    adapter = CDHACPAdapter()
    server = JSONRPCServer(adapter)
    prompt_task: asyncio.Task | None = None

    async def _run_prompt(req: dict):
        try:
            result = await server._handle_session_prompt(req.get("params", {}))
            return {"jsonrpc": "2.0", "result": result, "id": req.get("id")}
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            _dump_crash("_run_prompt")
            print(f"[cdh-agent-acp] ERROR in _run_prompt:\n{tb}", file=sys.stderr, flush=True)
            debug_log("_run_prompt failed: %s\n%s", e, tb, exc_info=True)
            return {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}, "id": req.get("id")}

    while True:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            break

        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        requests = request if isinstance(request, list) else [request]

        for req in requests:
            if not isinstance(req, dict):
                continue

            # Check if this is a response to a pending server→client request
            if "id" in req and ("result" in req or "error" in req):
                req_id = req.get("id")
                if isinstance(req_id, str) and req_id in adapter._pending_requests:
                    adapter.resolve_pending_request(req_id, req.get("result", {}))
                    continue

            method = req.get("method", "")
            req_id = req.get("id")

            if method == "session/prompt":
                # Run prompt in background so main loop stays responsive
                # to cancel notifications on stdin
                prompt_task = asyncio.create_task(_run_prompt(req))
                def _on_prompt_done(t, req=req):
                    try:
                        resp = t.result()
                    except Exception as exc:
                        _dump_crash("_on_prompt_done")
                        debug_log(f"Prompt task raised unhandled exception: {exc}", exc_info=True)
                        resp = {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(exc)}, "id": req.get("id")}
                    if resp.get("id") is not None:
                        try:
                            print(json.dumps(resp), flush=True)
                        except (TypeError, ValueError, OSError) as e:
                            _dump_crash("_on_prompt_done_send")
                            debug_log("_on_prompt_done send failed: %s", e)
                prompt_task.add_done_callback(_on_prompt_done)
            elif method == "session/cancel":
                if prompt_task and not prompt_task.done():
                    adapter.cancel_prompt()
                # Notification (no id) — nothing to respond with
            else:
                response = await server.handle_request(req)
                if response.get("id") is not None:
                    try:
                        print(json.dumps(response), flush=True)
                    except (TypeError, ValueError, OSError) as e:
                        _dump_crash("main_loop_send")
                        debug_log("main loop send failed: %s", e)


def main():
    asyncio.run(_main())

if __name__ == "__main__":
    main()