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
from pathlib import Path


logger = logging.getLogger("cdha.agent.cdh_acp")


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
    """Debug log via the ``cdha.agent.cdh_acp`` logger.

    Falls back to stderr if the logging system has not been configured
    yet (e.g. during very early adapter import when ``setup_logging`` has
    not been called).  This keeps the function safe to call from any
    module-import-time path without breaking the JSON-RPC stream on stdout.
    """
    if logger.handlers or logging.getLogger().handlers:
        logger.debug(" ".join(str(a) for a in args), **kwargs)
    else:
        print("[cdha]", *args, file=sys.stderr, flush=True)

from cdha.agent.engine import AgentEngine
from cdha.agent.permissions_store import PermissionStore
from cdha.agent.session import AgentSession
from cdha.config import load_config
from cdha.models.provider import ProviderRegistry
from cdha.models.registry import ModelRegistry
from cdha.models.messages import (
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

from cdha.models.providers.minimaxi_provider import MiniMaxiProvider
from cdha.models.providers.minimax_provider import MiniMaxProvider
from cdha.models.providers.anthropic_provider import AnthropicProvider
from cdha.models.providers.openai_provider import OpenAIProvider
from cdha.models.providers.deepseek_provider import DeepSeekProvider
from cdha.models.providers.glm_provider import GLMProvider
from cdha.models.providers.ollama_provider import OllamaProvider


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

    if name == "Read":
        path = str(arguments.get("path", ""))
        if path:
            return [{
                "type": "content",
                "content": {"type": "text", "text": f"📄 {path}"},
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

    args_text = json.dumps(arguments, indent=2, ensure_ascii=False)
    return [{
        "type": "content",
        "content": {"type": "text", "text": f"```json\n{args_text}\n```"},
    }]


def _format_tui_display_text(result_text: str) -> str:
    """Convert internal tool result JSON to user-visible text for TUI.

    Tools return dicts like ``{"success": true, "path": "..."}`` that are
    meaningful to the LLM but noisy for the user.  This function strips
    internal JSON wrappers and returns only what the user should see.

    Success results that have a ``path`` field render as ``✓ /path``;
    other success results fall through to a compact view of the rest
    of the dict so tools like ``TaskUpdate`` / ``TaskStop`` (which return
    ``{"success": true, ...}`` without a path) still show meaningful
    output instead of disappearing.
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


def _create_engine(cwd: str) -> AgentEngine:
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
    return AgentEngine(MinimalApp(), project_dir=project_dir)


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
        notification = {"jsonrpc": "2.0", "method": method, "params": params}
        print(json.dumps(notification), flush=True)

    def send_request(self, method: str, params: dict) -> asyncio.Future[dict]:
        """Send a JSONRPC request to A2TUI and return a Future for the response."""
        self._request_seq += 1
        req_id = f"svr_{self._request_seq}"
        future: asyncio.Future[dict] = asyncio.Future()
        self._pending_requests[req_id] = future
        request = {"jsonrpc": "2.0", "method": method, "params": params, "id": req_id}
        print(json.dumps(request), flush=True)
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

    def send_session_update(self, update: dict):
        """Send a session/update notification with proper ACP protocol format."""
        self.send_notification("session/update", {
            "sessionId": self.session_id,
            "update": update,
        })

    def _emit_tool_result(self, block: ToolResult) -> None:
        """Send a tool_result as a tool_call_update, accumulating with existing content."""
        display_text = _format_tui_display_text(block.content)

        # Update title with path from result if not already set
        if block.content and block.tool_use_id in self.tool_calls:
            try:
                parsed = json.loads(block.content)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(parsed, dict) and parsed.get("success") is True:
                    current_title = self.tool_calls[block.tool_use_id].get("title", "")
                    if ":" not in current_title:
                        if path := parsed.get("path"):
                            self.tool_calls[block.tool_use_id]["title"] = f"{current_title}: {_short_path(path, self.agent._project_dir)}"

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
            ],
        })

    async def session_new(self, cwd: str, mcp_servers: list):
        """Create new session."""
        cfg = load_config()
        self.agent = _create_engine(cwd)
        self.agent.set_agent(cfg.default_mode)
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
        self.agent = _create_engine(cwd)
        self.session_id = session_id

        loaded = self.agent.load_session(session_id)
        cfg = load_config()
        self.agent.set_agent(cfg.default_mode)
        self._perm_store.apply_to(self.agent.current_agent)
        self._send_available_commands()
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
                                "content": {"type": "text", "text": f"```thinking\n{filtered_thought}\n```"},
                            })
                    elif isinstance(block, MsgToolCall):
                        tool_kind = _kind_for_category(get_tool_category(block.name))
                        content_blocks = _build_tool_call_content(
                            block.name, block.arguments or {}
                        )
                        self.tool_calls[block.id] = {
                            "sessionUpdate": "tool_call",
                            "toolCallId": block.id,
                            "title": block.name,
                            "kind": tool_kind,
                            "status": _wire_status(block.status.value),
                            "content": content_blocks,
                        }
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
                            tr = ToolResult(
                                tool_use_id=item.get("tool_use_id", ""),
                                content=item.get("content", ""),
                                is_error=item.get("is_error", False),
                            )
                            self._emit_tool_result(tr)
                elif isinstance(content, dict) and content.get("type") == "tool_result":
                    tr = ToolResult(
                        tool_use_id=content.get("tool_use_id", ""),
                        content=content.get("content", ""),
                        is_error=content.get("is_error", False),
                    )
                    self._emit_tool_result(tr)

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

        text_buffer = ""
        in_thinking = False
        in_tool_call = False
        in_minimax_tool_call = False
        in_bare_tool_call = False
        bare_tool_start = 0

        def _flush_held_buffer() -> None:
            """Force-emit the held buffer as a plain message and reset
            all "in marker" flags.  Used by the watchdog below and by
            the early-exit path when a turn ends without a close
            marker.
            """
            nonlocal text_buffer
            nonlocal in_thinking, in_tool_call
            nonlocal in_minimax_tool_call, in_bare_tool_call, bare_tool_start
            if text_buffer.strip():
                self.send_session_update({
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": text_buffer},
                })
            text_buffer = ""
            in_thinking = in_tool_call = False
            in_minimax_tool_call = in_bare_tool_call = False
            bare_tool_start = 0

        def _emit_message(text: str) -> None:
            if not text:
                return
            self.send_session_update({
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
            nonlocal text_buffer, in_thinking, in_tool_call
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
                            self.send_session_update({
                                "sessionUpdate": "agent_thought_chunk",
                                "content": {"type": "text", "text": f"```thinking\n{thinking}\n```"},
                            })
                        text_buffer = text_buffer[idx + close_len:]
                        in_thinking = False
                    else:
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
            return {"stopReason": "error", "message": "No agent initialized"}

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

        self.agent._cancelled = False
        self.agent.on_text_chunk = self._make_stream_callback()

        # Track in-progress tool call args for incremental display
        _incremental_args: dict[str, str] = {}

        def _on_tool_call_delta(call_id: str, name: str, args_delta: str) -> None:
            if args_delta:
                _incremental_args[call_id] = _incremental_args.get(call_id, "") + args_delta
                display_args = _incremental_args[call_id]
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
        async for event in self.agent.chat_stream(user_content):
            if event.type == StreamEventType.TEXT_DELTA:
                self.send_session_update({
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": event.text},
                })
            elif event.type == StreamEventType.THINKING:
                thought_text = f"```thinking\n{event.thinking}\n```"
                self.send_session_update({
                    "sessionUpdate": "agent_thought_chunk",
                    "content": {"type": "text", "text": thought_text},
                })
            elif event.type == StreamEventType.TOOL_CALL_START:
                tool_kind = _kind_for_category(event.tool_category)
                existing = self.tool_calls.get(event.tool_id, {})
                self.tool_calls[event.tool_id] = {
                    "sessionUpdate": "tool_call",
                    "toolCallId": event.tool_id,
                    "title": event.tool_name,
                    "kind": tool_kind,
                    "status": "in_progress",
                    "content": existing.get("content", []),
                }
                self.send_session_update(self.tool_calls[event.tool_id])
            elif event.type == StreamEventType.TOOL_CALL_COMPLETE:
                if event.tool_id in self.tool_calls:
                    title = event.tool_name
                    if event.tool_args:
                        if path := event.tool_args.get("path", ""):
                            title = f"{event.tool_name}: {_short_path(path, self.agent._project_dir)}"
                        elif event.tool_name == "Bash":
                            cmd = str(event.tool_args.get("command", ""))[:60]
                            title = f"Bash: {cmd}"
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
                    })
                    self.send_session_update(self.tool_calls[event.tool_id])
            elif event.type == StreamEventType.TOOL_RESULT:
                status = "failed" if event.result_is_error else "completed"
                display_text = _format_tui_display_text(event.result_content or "")

                # Update title with path from result if not already set
                if event.result_content and event.tool_id in self.tool_calls:
                    try:
                        parsed = json.loads(event.result_content)
                    except json.JSONDecodeError:
                        pass
                    else:
                        if isinstance(parsed, dict) and parsed.get("success") is True:
                            current_title = self.tool_calls[event.tool_id].get("title", "")
                            if ":" not in current_title:
                                if path := parsed.get("path"):
                                    self.tool_calls[event.tool_id]["title"] = f"{current_title}: {_short_path(path, self.agent._project_dir)}"

                # TUI now renders all text content as Markdown.
                # Wrap multi-line results in a fenced code block so they
                # display as a code block rather than a raw paragraph.
                # Skip if already contains a code fence to avoid nesting.
                if display_text and "\n" in display_text and "```" not in display_text:
                    display_text = f"```\n{display_text}\n```"
                content_block = [{
                    "type": "content",
                    "content": {"type": "text", "text": display_text},
                }] if display_text else []
                if event.tool_id in self.tool_calls:
                    existing_content = self.tool_calls[event.tool_id].get("content", [])
                else:
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
            elif event.type == StreamEventType.ERROR:
                self.send_session_update({
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": f"Error: {event.error_message}"},
                })
                self.agent.save_session()
                return {"stopReason": "error", "message": event.error_message}
            elif event.type == StreamEventType.SUBAGENT_START:
                self.send_session_update({
                    "sessionUpdate": "subagent_start",
                    "subagentId": event.subagent_id,
                    "agentType": event.subagent_type,
                })
            elif event.type == StreamEventType.SUBAGENT_CHUNK:
                self.send_session_update({
                    "sessionUpdate": "subagent_chunk",
                    "subagentId": event.subagent_id,
                    "text": event.subagent_text,
                })
            elif event.type == StreamEventType.SUBAGENT_END:
                self.send_session_update({
                    "sessionUpdate": "subagent_end",
                    "subagentId": event.subagent_id,
                    "agentType": event.subagent_type,
                })
            elif event.type == StreamEventType.PLAN:
                self.send_session_update({
                    "sessionUpdate": "plan",
                    "entries": event.plan_entries,
                })
            elif event.type == StreamEventType.ASK_USER:
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
                        from cdha.agent.agents.types import AgentPermission
                        perm_key = self.agent._TOOL_NAME_TO_PERM_KEY.get(event.ask_action)
                        if perm_key:
                            attr_name = f"permission_{perm_key}"
                            setattr(self.agent.current_agent, attr_name, AgentPermission.ALLOW)
                            self._perm_store.set_override(perm_key, AgentPermission.ALLOW)
                    elif option_id == "reject_always":
                        from cdha.agent.agents.types import AgentPermission
                        perm_key = self.agent._TOOL_NAME_TO_PERM_KEY.get(event.ask_action)
                        if perm_key:
                            attr_name = f"permission_{perm_key}"
                            setattr(self.agent.current_agent, attr_name, AgentPermission.DENY)
                            self._perm_store.set_override(perm_key, AgentPermission.DENY)
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

        self.agent.save_session()
        stop_reason = "cancelled" if self.agent._cancelled else "end_turn"
        usage = self._build_session_usage()
        return {
            "sessionId": self.session_id,
            "stopReason": stop_reason,
            "usage": usage,
        }

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

    async def session_cancel(self, session_id: str, _meta: dict):
        """Cancel current session."""
        if self.agent:
            await self.agent.cancel()
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
            "session/set_mode": self._handle_session_set_mode,
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
                def _on_prompt_done(t):
                    resp = t.result()
                    if resp.get("id") is not None:
                        print(json.dumps(resp), flush=True)
                prompt_task.add_done_callback(_on_prompt_done)
            elif method == "session/cancel":
                if prompt_task and not prompt_task.done():
                    adapter.cancel_prompt()
                # Notification (no id) — nothing to respond with
            else:
                response = await server.handle_request(req)
                if response.get("id") is not None:
                    print(json.dumps(response), flush=True)


def main():
    asyncio.run(_main())

if __name__ == "__main__":
    main()