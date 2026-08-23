from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from dataclasses import dataclass
from typing import Callable

from onecode.agent.agents.types import AgentPermission
from onecode.agent.cdh_loader import CdhProjectLoader
from onecode.agent.context import ContextManager
from onecode.agent.permissions_store import PermissionStore
from onecode.models.provider import ContentBlockType, ProviderRegistry

from onecode.agent.session import AgentSession
from onecode.memory import AgentMemory, MemoryLayer
from onecode.models.errors import ContextLengthError, TransientProviderError, safe_error_msg
from onecode.models.messages import StreamEvent, StreamEventType

logger = logging.getLogger("onecode.agent.engine")

# Subagent depth limit — subagents are leaf nodes by default (max depth = 1),
# controlled via `agent.max_subagent_depth` in onecode.config.yaml.
_MAX_SUBAGENT_DEPTH = 1

# Marker embedded in injected nudge messages for robust cleanup.
# Searching by content is resilient to context compaction, index shifts,
# and concurrent message insertion — unlike the index-based approach.
_INJECT_MARKER = "<!-- INJECTED_NUDGE -->"

# Maximum wall-clock seconds for a single subagent execution.  Prevents
# hung subagents from blocking the parent engine indefinitely.
_SUBAGENT_TIMEOUT = 600


def _get_block_type(block: Any) -> str:
    """Get content block type string, handling both dict and ContentBlock."""
    if isinstance(block, dict):
        return block.get("type", "")
    return str(getattr(block, "type", "") or "")


def _get_block_text(block: Any) -> str:
    """Get content block text, handling both dict and ContentBlock."""
    if isinstance(block, dict):
        return str(block.get("text", "") or block.get("content", "") or "")
    text = getattr(block, "text", None) or getattr(block, "content", None)
    return str(text or "")


@dataclass(frozen=True)
class ToolEvent:
    """Event emitted during the agent loop lifecycle (Clawd-Code style)."""
    kind: str  # "tool_use" | "tool_result" | "tool_error"
    tool_name: str = ""
    tool_input: dict | None = None
    tool_output: Any = None
    tool_use_id: str | None = None
    is_error: bool = False
    error: str | None = None


ToolEventHandler = Callable[[ToolEvent], None]


class TurnCancelledError(Exception):
    """Raised when the user cancels the agent's turn mid-execution."""


TOOL_CALL_RE = re.compile(
    r'<tool_call\s+name=["\']([^"\']+)["\']\s+id=["\']([^"\']+)["\']>(.*?)</tool_call>',
    re.DOTALL,
)

# Structured tool call format used by the minimaxi / claude / Anthropic-style
# models.  Looks like::
#
#     <minimax:tool_call>
#     <invoke name="Read">
#     <parameter name="path">SPEC.md</parameter>
#     </invoke>
#     <invoke name="Bash">
#     <parameter name="command">ls -la</parameter>
#     <parameter name="timeout">30</parameter>
#     </invoke>
#     </minimax:tool_call>
#
# We match the outer block, then split into individual <invoke> elements
# inside ``_extract_minimax_tool_uses``.
MINIMAX_TOOL_CALL_RE = re.compile(
    r'<minimax:tool_call>(.*?)</minimax:tool_call>',
    re.DOTALL,
)

# An individual <invoke name="X">...</invoke> block.  ``name`` is captured
# separately so we can call ``_parse_minimax_invoke_body`` on the inner XML.
_MINIMAX_INVOKE_RE = re.compile(
    r'<invoke\s+name="([^"]+)">(.*?)</invoke>',
    re.DOTALL,
)

# A single <parameter name="X">value</parameter> element.  The value can span
# multiple lines, may contain entity-escaped angle brackets, and we tolerate
# either double or single quotes around the name.
_MINIMAX_PARAM_RE = re.compile(
    r'<parameter\s+name=["\']([^"\']+)["\']>(.*?)</parameter>',
    re.DOTALL,
)

THINKING_RE = re.compile(
    r'<think(?:ing)?>(.*?)</think(?:ing)?>',
    re.DOTALL,
)

_LEGACY_OPEN = "[TOOL_CALL]"
_LEGACY_CLOSE = "[/TOOL_CALL]"


def _parse_minimax_invoke_body(body: str) -> dict:
    """Parse the inner XML of a single ``<invoke name="X">`` block.

    Returns a dict ``{"name": str, "arguments": {param_name: value, ...}}``.
    The ``arguments`` dict is empty if no ``<parameter>`` children are found.
    """
    body = body.strip()
    arguments: dict = {}
    for m in _MINIMAX_PARAM_RE.finditer(body):
        param_name = m.group(1)
        raw_value = m.group(2)
        arguments[param_name] = _unescape_xml(raw_value)
    return arguments


def _unescape_xml(s: str) -> str:
    """Reverse the common XML / HTML entity escapes.

    We keep this conservative — the five predefined entities and the numeric
    ones — so we never accidentally mangle content that legitimately contains
    ampersands.
    """
    return (
        s.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("&amp;", "&")
    )


def _extract_minimax_tool_uses(text: str, id_start: int = 0) -> tuple[list[dict], str, int]:
    """Extract ``<minimax:tool_call>...</minimax:tool_call>`` blocks.

    Returns ``(tool_uses, cleaned_text, next_id)`` where ``tool_uses`` is a
    list of ``{id, name, input}`` dicts and ``cleaned_text`` has every
    matched block removed.  ``id_start`` is the next available tool id
    counter (caller-owned, see ``AgentEngine._tool_id_counter``); the next
    free id is returned in the tuple so callers can pass it to subsequent
    extractions without losing uniqueness.
    """
    tool_uses: list[dict] = []
    cleaned = text
    counter = id_start
    while True:
        m = MINIMAX_TOOL_CALL_RE.search(cleaned)
        if m is None:
            break
        block_body = m.group(1)
        for inv in _MINIMAX_INVOKE_RE.finditer(block_body):
            name = inv.group(1)
            arguments = _parse_minimax_invoke_body(inv.group(2))
            counter += 1
            tool_uses.append({
                "id": f"minimax-{counter}",
                "name": name,
                "input": arguments,
            })
        cleaned = cleaned[:m.start()] + cleaned[m.end():]
    return tool_uses, cleaned, counter


def _scan_balanced_braces(text: str, open_pos: int) -> int | None:
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
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
        else:
            i += 1
    return None


def _parse_legacy_tool_body(body: str) -> dict:
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


def _extract_legacy_tool_uses(
    text: str, id_start: int = 0
) -> tuple[list[dict], str, int]:
    """Extract all [TOOL_CALL]...[/TOOL_CALL] blocks from text.

    Returns (tool_uses, cleaned_text, next_id) where tool_uses has
    [{id, name, input}, ...] and cleaned_text has all markers removed.
    ``id_start`` lets the caller share a monotonic counter across multiple
    extraction passes; the next free id is returned so callers can pass it
    forward.
    """
    tool_uses: list[dict] = []
    cleaned = text
    counter = id_start
    while True:
        open_idx = cleaned.find(_LEGACY_OPEN)
        if open_idx < 0:
            break
        body_start = open_idx + len(_LEGACY_OPEN)
        close_idx = cleaned.find(_LEGACY_CLOSE, body_start)
        if close_idx < 0:
            # Unclosed marker — stop looking
            break
        body = cleaned[body_start:close_idx]
        span_end = close_idx + len(_LEGACY_CLOSE)
        parsed = _parse_legacy_tool_body(body)
        name = parsed.get("name")
        if name:
            counter += 1
            tool_uses.append({
                "id": f"legacy-{counter}",
                "name": name,
                "input": parsed.get("arguments", {}),
            })
        cleaned = cleaned[:open_idx] + cleaned[span_end:]
    return tool_uses, cleaned, counter


_TODO_STATUSES = {"pending", "in_progress", "completed"}


class TodoManager:
    """Unified todo manager (formerly TodoManager).

    Each todo has: id, subject, description, activeForm, status, owner, blocks,
    blockedBy, metadata, output. Supports dependency tracking and progress
    display in the TUI Plan sidebar.

    Persistence format (``to_dict``/``from_dict``) accepts both the new
    single-list layout and the legacy ``{"tasks": [...], "todos": [...]}``
    layout for backwards compatibility with existing session files.
    """

    def __init__(self, on_change: Callable[[], None] | None = None):
        self._todos: dict[str, dict] = {}
        self._order: list[str] = []
        self._id_counter = 0
        self._on_change = on_change

    def _mark_dirty(self) -> None:
        if self._on_change:
            self._on_change()

    def _next_id(self) -> str:
        self._id_counter += 1
        return f"t{self._id_counter}"

    # ── Todo CRUD ──

    def create_todo(
        self,
        subject: str,
        description: str = "",
        active_form: str = "",
        metadata: dict | None = None,
    ) -> dict:
        """Create a todo with dependency tracking support."""
        todo_id = self._next_id()
        todo = {
            "id": todo_id,
            "_order": self._id_counter,
            "subject": subject,
            "description": description,
            "activeForm": active_form,
            "status": "pending",
            "owner": None,
            "blocks": [],
            "blockedBy": [],
            "metadata": dict(metadata or {}),
            "output": "",
        }
        self._todos[todo_id] = todo
        self._order.append(todo_id)
        self._mark_dirty()
        return todo

    def get_todo(self, todo_id: str) -> dict | None:
        return self._todos.get(todo_id)

    def list_todos(self) -> list[dict]:
        """List all todos in creation order."""
        return [self._todos[tid] for tid in self._order if tid in self._todos]

    def update_todo(self, todo_id: str, **fields) -> dict | None:
        """Update todo fields. Supports: subject, description, activeForm, status,
        owner, metadata, addBlocks, addBlockedBy. Returns updated todo or None."""
        todo = self._todos.get(todo_id)
        if todo is None:
            return None

        updated = []

        for field in ("subject", "description", "activeForm", "owner"):
            if field in fields:
                v = fields[field]
                if isinstance(v, str) and v != todo.get(field):
                    todo[field] = v
                    updated.append(field)

        if "status" in fields:
            status = fields["status"]
            if status == "deleted":
                self._todos.pop(todo_id, None)
                if todo_id in self._order:
                    self._order.remove(todo_id)
                self._mark_dirty()
                return {"id": todo_id, "deleted": True}
            if status in _TODO_STATUSES and status != todo.get("status"):
                todo["status"] = status
                updated.append("status")

        for rel_field, input_key in (("blocks", "addBlocks"), ("blockedBy", "addBlockedBy")):
            if input_key in fields:
                ids = fields[input_key]
                if isinstance(ids, list):
                    cur = list(todo.get(rel_field) or [])
                    for x in ids:
                        if isinstance(x, str) and x not in cur:
                            cur.append(x)
                    if cur != todo.get(rel_field):
                        todo[rel_field] = cur
                        updated.append(rel_field)

        if "metadata" in fields:
            md = fields["metadata"]
            if isinstance(md, dict):
                existing = dict(todo.get("metadata") or {})
                for k, v in md.items():
                    if v is None:
                        existing.pop(k, None)
                    else:
                        existing[k] = v
                todo["metadata"] = existing
                updated.append("metadata")

        if "output" in fields:
            v = fields["output"]
            if isinstance(v, str):
                todo["output"] = v
                updated.append("output")

        self._mark_dirty()
        return todo

    def get_todo_output(self, todo_id: str) -> dict:
        """Get output for a todo."""
        todo = self._todos.get(todo_id)
        if todo is None:
            return {"retrieval_status": "not_found", "task": None}
        output = str(todo.get("output") or "")
        return {
            "retrieval_status": "success" if output else "not_ready",
            "task": {
                "task_id": todo_id,
                "task_type": "todo_list",
                "status": todo.get("status"),
                "description": todo.get("description"),
                "output": output,
            },
        }

    def clear_todos(self) -> None:
        self._todos.clear()
        self._order.clear()
        self._id_counter = 0
        self._mark_dirty()

    def clear_completed(self) -> None:
        completed_ids = [tid for tid in self._order if tid in self._todos and self._todos[tid].get("status") == "completed"]
        for tid in completed_ids:
            self._todos.pop(tid, None)
            self._order.remove(tid)
        if completed_ids:
            self._mark_dirty()

    # ── Serialization ──

    def to_dict(self) -> dict:
        """Serialize todos for persistence."""
        return {
            "todos": [dict(self._todos[tid]) for tid in self._order if tid in self._todos],
            "id_counter": self._id_counter,
        }

    @classmethod
    def from_dict(cls, data: dict, on_change: Callable[[], None] | None = None) -> "TodoManager":
        """Restore todo manager from saved dict.

        Accepts the unified ``{"todos": [...]}`` layout (preferred) and the
        legacy ``{"tasks": [...], "todos": [...]}`` layout where ``todos``
        entries may use the old ``{text, done}`` shape — these are converted
        on the fly to the new ``{subject, status}`` shape.
        """
        tm = cls(on_change=on_change)
        tm.reload_from_dict(data)
        return tm

    def reload_from_dict(self, data: dict) -> None:
        """Reload state from *data* in place, preserving the instance identity.

        This is critical because tool instances (``TodoCreateTool`` etc.)
        hold a direct reference to the same ``TodoManager`` object.  If we
        replaced ``self._todo_manager`` with a new instance, the tools
        would silently write to the stale one while the engine reads from
        the fresh one — creating the illusion of success but never
        persisting or emitting plan updates.
        """
        self._todos.clear()
        self._order.clear()
        self._id_counter = data.get("id_counter", 0)

        raw_todos: list[dict] = []
        if "todos" in data:
            raw_todos.extend(data.get("todos") or [])
        if "tasks" in data:
            raw_todos.extend(data.get("tasks") or [])

        for t in raw_todos:
            todo = dict(t)
            if "subject" not in todo and "text" in todo:
                todo["subject"] = todo.pop("text")
            if "status" not in todo and "done" in todo:
                todo["status"] = "completed" if todo.pop("done") else "pending"
            todo.setdefault("status", "pending")
            tid = todo.get("id") or self._next_id()
            todo["id"] = tid
            todo.setdefault("_order", self._id_counter)
            self._todos[tid] = todo
            if tid not in self._order:
                self._order.append(tid)


# Tools that require a task plan before execution (plan gate)
_EXECUTION_TOOLS: frozenset[str] = frozenset({
    "Write", "Edit", "Insert", "ApplyPatch", "Bash",
})


class AgentEngine:
    def __init__(self, app, project_dir: Path | None = None, perm_store: PermissionStore | None = None):
        from onecode.agent.tools.file_ops import ToolFactory
        from onecode.agent.agents.types import BuildAgent
        from onecode.agent.hooks import HookManager
        from onecode.skills.loader import SkillLoader
        from onecode.mcp.manager import MCPManager
        from onecode.agent.tools.cron_tools import CronScheduler
        from onecode.agent.tools.lsp_tools import LSPTool
        from onecode.agent.tools.config_tool import ConfigReadTool, ConfigWriteTool
        from onecode.agent.tools.communication_tools import SendMessageTool
        self.app = app
        self._project_dir = (project_dir or Path.cwd()).resolve()
        self.context = ContextManager()
        self.file_ops = ToolFactory.create_file_ops(self._project_dir)
        self.shell = ToolFactory.create_shell(self._project_dir)
        self.current_agent: AgentConfig = BuildAgent()  # noqa: F821
        self.iterations = 0
        self.total_tokens = 0
        self._skills_loaded = False
        self._session: Optional[AgentSession] = None
        self._memory = AgentMemory()
        self._hooks = HookManager()
        self._todo_manager = TodoManager(on_change=self._on_todo_change)
        self._plan_dirty: bool = False
        # Plan mode denial counter — reset per session
        self._plan_denial_count: int = 0
        # Per-tool denial counters for loop protection (any agent/mode)
        self._tool_denial_count: dict[str, int] = {}
        # Path of the plan document saved when the plan agent submits for approval
        self._approved_plan_path: str | None = None
        # Cache of the last plan snapshot that was emitted to the TUI.  Used
        # by ``_emit_plan_update`` to dedupe redundant emits when the todos
        # have not actually changed between turns.  The first emit of a
        # session/cycle always wins (cache starts empty).
        self._last_emitted_plan: tuple = ()
        self._project_config: dict = {}
        self._project_context_loaded = False
        self._pending_approval: dict | None = None  # {tool_call, result_key}
        self._last_user_msg: str | None = None  # Last SendMessage visible to user

        # Clawd-Code subsystems
        self._skill_loader = SkillLoader()

        # Loop system (L2 Verification + L3 Event)
        from onecode.config import load_config
        _cfg = load_config()
        self._cfg = _cfg

        self._mcp = MCPManager(
            timeout=_cfg.mcp.timeout,
            heartbeat_interval=_cfg.mcp.heartbeat_interval,
        )
        self._cron_scheduler = CronScheduler()
        self._lsp_tool = LSPTool()

        # Register default CloudBase MCP entry (shows in ``mcp list`` even
        # without credentials — actual connect happens when skill loads).
        from onecode.mcp.cloudbase import ensure_configured as _ensure_cb
        _ensure_cb(self._mcp)
        self._verification_loop: Optional["VerificationLoop"] = None  # noqa: F821
        self._event_bridge: Optional["EventBridge"] = None  # noqa: F821
        if _cfg.loops.verification.enabled:
            agent_type = getattr(app, 'current_agent', None)
            agent_name = getattr(agent_type, 'name', 'build') if agent_type else 'build'
            vcfg = _cfg.loops.verification.for_agent(agent_name)
            if vcfg.enabled:
                from onecode.verification import VerificationLoop
                from onecode.verification.gates import LintGate, TypeGate, TestGate
                self._verification_loop = VerificationLoop(policy=vcfg.policy)
                self._verification_loop.activate()
                if "lint" in vcfg.gates:
                    self._verification_loop.register_gate(LintGate())
                if "type" in vcfg.gates:
                    self._verification_loop.register_gate(TypeGate())
                if "test" in vcfg.gates:
                    self._verification_loop.register_gate(TestGate())
        if _cfg.loops.event.enabled:
            from onecode.agent.event_bridge import EventBridge
            self._event_bridge = EventBridge(bus=None)
        app_config = getattr(app, 'config', None)
        self._config_tool_read = ConfigReadTool(app_config) if app_config else None
        self._config_tool_write = ConfigWriteTool(app_config) if app_config else None

        # Codebase engine (lazy init)
        self._codebase_engine: Optional["CodebaseEngine"] = None  # noqa: F821

        # Tool registry (Clawd-Code pattern)
        self._tool_registry = self._build_tool_registry()
        self._send_message_tool = SendMessageTool()

        # Per-turn usage tracking (Clawd-Code style)
        self._turn_usages: list[dict[str, int]] = []

        # Turn-level issue tracking — collects provider errors, context overflows,
        # verification failures across all turns so the final session summary
        # can report every problem encountered, not just the first one.
        self._turn_events: list[dict] = []

        # Event callbacks
        self.on_event: ToolEventHandler | None = None
        self.on_text_chunk: Callable[[str], None] | None = None
        self.on_tool_call_delta: Callable[[str, str, str], None] | None = None
        self.on_thinking: Callable[[str], None] | None = None
        self._streaming_used: bool = False
        self._pending_thinking_blocks: list[str] = []

        # Cancellation support
        self._cancelled: bool = False

        # Subagent depth limit — subagents are leaf nodes (max depth = 1).
        self._subagent_depth: int = 0

        # ContextLengthError crisis flag — when set, skip codebase/memory
        # auto-injection to avoid "compact → re-inject → compact" loops.
        self._ctx_crisis: bool = False

        # Verification retry counter per session.
        self._verification_fail_count: int = 0

        # Store last tool results by tool_use_id for TurnRecord assembly.
        self._last_tool_results: dict[str, str] = {}

        # Skip codebase auto-retrieval / long-term memory recall inside
        # subagent engines.  Both are project-seeding steps meant for the
        # top-level chat loop; a subagent already receives a fully-formed
        # explicit prompt from the parent and does NOT need toEmbed/index
        # the whole codebase or recall memories again — that path
        # previously called ``CodebaseIndexer.index()`` (a long
        # synchronous loop, blocking the event loop and cancel) plus
        # ``CodebaseRetriever._retrieve_embedding()`` (one httpx call per
        # chunk, each with a 30s timeout, so ~minutes of dead time), which
        # is the root cause of the "subagent shows no stream output and
        # can't be stopped" hang observed in production.
        self._disable_retrieval: bool = False

        # Monotonic tool-call id counter — shared across every
        # ``chat_stream`` turn so the same id is never reused even when the
        # model re-emits ``legacy-0`` / ``minimax-0`` in a fresh turn.
        # Touched only by ``_extract_*_tool_uses`` through the engine
        # instance, not by the module-level helpers (which take an explicit
        # ``id_start`` for testability).
        self._tool_id_counter: int = 0

        # Subagent engines spawned by this engine — we track them so
        # cancelling the parent also cancels in-flight subagents.
        self._child_engines: list[AgentEngine] = []

        # Permission overrides shared across subagents
        self._perm_store: PermissionStore = perm_store or PermissionStore()

        # Plan gate: mode-aware enforcement based on agent type
        # "hard" (plan mode) rejects execution tools without plan
        # "soft" (build/solo mode) suggests planning but doesn't block
        # "off" (agents with permission_task=DENY) no enforcement
        self._plan_gate_mode: str = "off"

        # Flag set when exiting Plan mode — suppresses auto-advancement of todos
        # until user explicitly starts executing real work in the new mode.
        self._just_exited_plan_mode: bool = False

        # ReAct state tracking
        self._react_phase: str = "thought"  # "thought" | "action" | "observation"
        self._direct_execution_count: int = 0  # Track direct tool use for routing-decision reminder

        # Consecutive turns with zero tool_uses — if the LLM repeatedly
        # refuses to call tools despite pending todos, we cap the loop
        # instead of cycling until max_turns is exhausted.
        self._empty_tool_turns: int = 0

        # Track injected nudge messages for cleanup after chat_stream exits.
        self._injected_msg_indices: list[int] = []

        # Checkpoint manager for protecting file state before destructive operations
        from onecode.agent.checkpoint import CheckpointManager
        self._checkpoint_manager = CheckpointManager(self._project_dir)

    def _build_tool_registry(self) -> ToolRegistry:  # noqa: F821
        from onecode.agent.tools.registry import ToolRegistry
        from onecode.agent.tools.file_tools import ReadTool, WriteTool, EditTool, InsertTool, UndoEditTool, GlobTool, GrepTool, ListTool
        from onecode.agent.tools.apply_patch_tool import ApplyPatchTool
        from onecode.agent.tools.bash_tool import BashTool
        from onecode.agent.tools.web_tools import WebFetchTool, WebSearchTool
        from onecode.agent.tools.communication_tools import SendMessageTool, AskUserTool, ToolSearchTool
        from onecode.agent.tools.todo_tools import (TodoCreateTool, TodoGetTool, TodoListTool, TodoUpdateTool,
            TodoOutputTool, TodoStopTool, TodoClearTool)
        from onecode.agent.tools.agent_tools import AgentTool, TaskTool
        from onecode.agent.tools.skill_tools import SkillTool
        from onecode.agent.tools.mcp_tools import MCPTool as MCPToolTool, MCPResourcesTool
        from onecode.agent.tools.cron_tools import CronCreateTool, CronListTool, CronRemoveTool
        from onecode.agent.tools.git_tools import WorktreeTool
        registry = ToolRegistry()
        # File tools
        registry.register(ReadTool(self.file_ops))
        registry.register(WriteTool(self.file_ops))
        registry.register(EditTool(self.file_ops))
        registry.register(InsertTool(self.file_ops))
        registry.register(UndoEditTool(self.file_ops))
        registry.register(GlobTool(self.file_ops))
        registry.register(GrepTool(self.file_ops))
        registry.register(ListTool(self.file_ops))
        registry.register(ApplyPatchTool(self.file_ops))
        # Shell
        registry.register(BashTool(self.shell))
        # Web
        registry.register(WebFetchTool())
        registry.register(WebSearchTool())
        # Communication
        self._send_message_tool = SendMessageTool()
        registry.register(self._send_message_tool)
        registry.register(AskUserTool())
        registry.register(ToolSearchTool(registry))
        # Task management
        registry.register(TodoCreateTool(self._todo_manager))
        registry.register(TodoGetTool(self._todo_manager))
        registry.register(TodoListTool(self._todo_manager))
        registry.register(TodoUpdateTool(self._todo_manager))
        registry.register(TodoOutputTool(self._todo_manager))
        registry.register(TodoStopTool(self._todo_manager))
        registry.register(TodoClearTool(self._todo_manager))
        # Agent tools
        registry.register(AgentTool(registry, permission_checker=self._check_tool_permission))
        registry.register(TaskTool(self._spawn_subagent_async))

        # Skill tool (Clawd-Code pattern)
        registry.register(SkillTool(self._skill_loader))

        # MCP tools (Clawd-Code pattern)
        registry.register(MCPToolTool(self._mcp))
        registry.register(MCPResourcesTool(self._mcp))

        # LSP tool (Clawd-Code pattern)
        registry.register(self._lsp_tool)

        # Cron tools (Clawd-Code pattern)
        registry.register(CronCreateTool(self._cron_scheduler))
        registry.register(CronListTool(self._cron_scheduler))
        registry.register(CronRemoveTool(self._cron_scheduler))

        # Git worktree tool (Clawd-Code pattern)
        registry.register(WorktreeTool(workspace_root=self._project_dir))

        # Config tools (Clawd-Code pattern)
        if self._config_tool_read:
            registry.register(self._config_tool_read)
        if self._config_tool_write:
            registry.register(self._config_tool_write)

        # Codebase search tool (lazy — engine initialised on first search)
        from onecode.codebase.tools import CodebaseSearchTool
        registry.register(CodebaseSearchTool(lambda: self._codebase_engine))
        return registry

    def _is_plan_mode(self) -> bool:
        from onecode.agent.agents.types import AgentPermission
        return (self.current_agent is not None
                and self.current_agent.permission_edit == AgentPermission.DENY
                and self.current_agent.permission_bash == AgentPermission.DENY)

    def _resolve_plan_gate_mode(self) -> str:
        """Determine plan gate strictness based on current agent type.
        
        Returns "hard" (reject execution tools without plan), "soft" (nudge only),
        or "off" (no enforcement).
        """
        from onecode.agent.agents.types import AgentPermission
        if self.current_agent.permission_task == AgentPermission.DENY:
            return "off"
        if self.current_agent.name == "plan":
            return "hard"
        return "soft"

    def _has_pending_todos(self) -> bool:
        return any(
            t.get("status") in ("pending", "in_progress")
            for t in self._todo_manager.list_todos()
        )

    def _notify_event(self, event: ToolEvent) -> None:
        """Emit a ToolEvent to the registered callback (Clawd-Code pattern)."""
        if self.on_event:
            try:
                self.on_event(event)
            except Exception as e:
                logger.warning("ToolEvent callback failed: %s", e)

    def _inject_nudge(self, lines: list[str]) -> None:
        """Inject a user nudge message for later cleanup (marker-based)."""
        self.context.add_message(
            "user",
            [{"type": "text", "text": f"{_INJECT_MARKER}\n" + "\n".join(lines)}],
        )

    def _cleanup_injected_messages(self) -> None:
        """Remove all injected nudge messages by marker content.

        Uses the ``_INJECT_MARKER`` string embedded in message text, which
        is resilient to context compaction and index shifts — unlike the
        previous index-based approach that could corrupt the message list
        when markers referred to stale positions.
        """
        marker = _INJECT_MARKER
        kept: list = []
        removed_tokens = 0
        for m in self.context.messages:
            content_str = ""
            if isinstance(m.content, str):
                content_str = m.content
            elif isinstance(m.content, list):
                content_str = " ".join(
                    str(b.get("text", "")) for b in m.content if isinstance(b, dict)
                )
            if marker in content_str:
                removed_tokens += self.context._estimate_message_tokens(m)
            else:
                kept.append(m)
        self.context.messages = kept
        self.context._token_count -= removed_tokens
        self._injected_msg_indices.clear()

    def _emit_text_chunks(self, text: str, chunk_size: int = 12) -> None:
        """Emit user-visible text in small chunks (Clawd-Code pattern)."""
        if self.on_text_chunk is None or not text:
            return
        if chunk_size <= 0:
            chunk_size = len(text)
        for idx in range(0, len(text), chunk_size):
            try:
                self.on_text_chunk(text[idx:idx + chunk_size])
            except Exception as e:
                logger.warning("on_text_chunk failed: %s", e)
                return

    def _emit_plan_update(self) -> list[StreamEvent]:
        """Emit a plan update event from current todos, deduped against last emit.

        Returns an empty list when the plan snapshot is byte-identical to the
        last emission, so callers can no-op without paying the JSON-RPC + TUI
        widget-recompose cost.  The cache is a tuple of ``(content, status,
        priority)`` triples — order-sensitive, so reordering the todo list
        also triggers a re-emit.
        """
        entries = [
            (
                t.get("subject") or t.get("description", ""),
                t.get("status", "pending"),
                t.get("metadata", {}).get("priority", "medium"),
            )
            for t in self._todo_manager.list_todos()
        ]
        if entries == self._last_emitted_plan:
            return []
        self._last_emitted_plan = entries
        # Convert the cached tuples back to wire-format dicts for the stream
        # event.  The TUI side expects dicts; the dedupe cache stays tuples
        # to avoid the per-emit dict-construction cost on the hot path.
        wire_entries = [
            {"content": c, "status": s, "priority": p}
            for (c, s, p) in entries
        ]
        return [StreamEvent.plan(wire_entries)]

    def _auto_advance_after_spawn(self, subagent_prompt: str) -> None:
        """After a Spawn subagent completes, auto-advance todo status.

        Finds the first ``in_progress`` todo (typically the one the subagent
        was working on) and marks it ``completed``.  If another ``pending``
        todo remains, injects a user message into the LLM context directing
        the agent to continue — no need to wait for the LLM to spontaneously
        call ``TodoUpdate`` then ``Spawn`` again.
        """
        todos = self._todo_manager.list_todos()
        in_progress = [t for t in todos if t.get("status") == "in_progress"]
        if in_progress:
            tid = in_progress[0]["id"]
            self._todo_manager.update_todo(tid, status="completed")

        pending = [t for t in self._todo_manager.list_todos() if t.get("status") == "pending"]
        if pending:
            lines = ["# Continue working — remaining todos", ""]
            for t in pending:
                sub = t.get("subject", "")
                desc = t.get("description", "")
                if desc and desc != sub:
                    lines.append(f"- `{t['id']}`: {sub} — {desc}")
                else:
                    lines.append(f"- `{t['id']}`: {sub}")
            lines.append("")
            lines.append("Continue with the next pending todo above. Do NOT stop.")
            body = "\n".join(lines)
            self.context.add_message("user", [{"type": "text", "text": body}])

    def _refresh_pending_todos_nudge(self) -> None:
        """Inject a reminder that nudges the agent to advance unfinished todos.

        Called at the start of each ReAct turn. If there are pending or
        in-progress todos, a strong ``<!-- PENDING_TODOS -->`` section is
        injected into the system context directing the agent to continue
        working rather than summarising or stopping early.

        When no todos are open, any stale nudge is removed so the context
        stays clean.
        """
        marker = "<!-- PENDING_TODOS -->"
        open_todos = [t for t in self._todo_manager.list_todos()
                      if t.get("status") in ("pending", "in_progress")]
        if not open_todos:
            self.context.remove_system_by_marker(marker)
            return

        in_progress = [t for t in open_todos if t.get("status") == "in_progress"]
        pending = [t for t in open_todos if t.get("status") == "pending"]

        def _label(t: dict) -> str:
            sid = t.get("id", "?")
            sub = t.get("subject") or t.get("description", "")
            owner = t.get("owner")
            owner_part = f" (owner={owner})" if owner else ""
            return f"- `{sid}`{owner_part}: {sub}"

        lines: list[str] = []
        total = len(in_progress) + len(pending)
        lines.append(f"## ⚠️ Open todos ({total}) — you MUST continue working on these")
        lines.append("Do NOT end your turn until ALL todos below are completed.")
        if in_progress:
            labels = "\n".join(_label(t) for t in in_progress)
            lines.append(f"\nIn progress:\n{labels}")
        if pending:
            labels = "\n".join(_label(t) for t in pending)
            lines.append(f"\nPending:\n{labels}")
        if not self._is_plan_mode():
            lines.append(
                "\nFor each completed todo, call TodoUpdate(status=\"completed\") "
                "immediately. Then proceed to the next pending todo. "
                "Do NOT summarise or stop — keep working."
            )
        else:
            lines.append(
                "\nProceed to the next pending task. "
                "Do NOT summarise or stop — keep working."
            )
        body = f"{marker}\n" + "\n".join(lines)
        if not self.context.replace_system_section(marker, body):
            self.context.insert_system_before_non_system(body)

    def _on_todo_change(self) -> None:
        """Callback invoked by TodoManager whenever todos mutate.

        Sets a dirty flag so the next opportunity in ``chat_stream`` will
        emit a fresh plan event.  Decoupling the callback from the emit
        keeps the public API synchronous and avoids re-entrancy.

        Subagents have an isolated TodoManager and (since Todo tools are
        denied via disallowed_tools for subagents) cannot mutate the parent's
        shared plan, so this callback only fires for the main agent's own
        TodoManager.

        Also persists todos to ``.cdh/todos.json`` immediately so they
        survive a crash or Ctrl+C before the next ACP turn boundary.
        """
        self._plan_dirty = True
        self.save_todos_to_project()

    @property
    def _workspace(self) -> Path:
        return self._project_dir

    def _get_affected_files(self, tool_name: str, tool_input: dict) -> list[str]:
        """Extract list of file paths affected by a tool call."""
        if tool_name in ("Edit", "Write", "Insert", "Read", "Glob", "Grep", "List"):
            path = tool_input.get("path", "")
            return [path] if path else []
        if tool_name == "Bash":
            cmd = tool_input.get("command", "")
            files = []
            for part in cmd.split():
                if self._project_dir.exists() and (self._project_dir / part).exists():
                    if (self._project_dir / part).is_file():
                        files.append(part)
            return files
        if tool_name == "ApplyPatch":
            content = tool_input.get("patch", "") or tool_input.get("content", "")
            import re
            paths = re.findall(r'^(?:---|\+\+\+) [ab]/(.+)$', content, re.MULTILINE)
            return list(set(paths))
        return []

    def set_agent(self, agent_type: str, keep_todos: bool = False) -> None:
        from onecode.agent.agents.types import (
            AgentMode,
            AgentPermission,
            BUILD_AGENT_INSTRUCTIONS,
            PLAN_AGENT_INSTRUCTIONS,
            SOLO_AGENT_INSTRUCTIONS,
            EXPLORE_AGENT_INSTRUCTIONS,
            SUBAGENT_CONSTRAINTS,
            create_agent,
            PLAN_GATE_HARD,
            PLAN_GATE_SOFT,
            filter_tool_descriptions,
        )
        was_plan_mode = self._is_plan_mode()
        self.current_agent = create_agent(agent_type)

        # Plan / solo / build agents get dedicated, self-contained instruction
        # templates (workflow / format / constraints / response style)
        # instead of the generic description + gate + response-style
        # assembly below.
        agent_templates = {
            "plan": PLAN_AGENT_INSTRUCTIONS,
            "solo": SOLO_AGENT_INSTRUCTIONS,
            "build": BUILD_AGENT_INSTRUCTIONS,
            "explore": EXPLORE_AGENT_INSTRUCTIONS,
        }
        template = agent_templates.get(self.current_agent.name)
        system_parts = [template] if template else [self.current_agent.description]

        if was_plan_mode and not self._is_plan_mode():
            if not keep_todos:
                self._todo_manager.clear_todos()
                self.context.remove_system_by_marker("<!-- PENDING_TODOS -->")
            self._just_exited_plan_mode = True
            self._plan_denial_count = 0
            self._tool_denial_count.clear()
            self.context.remove_system_by_marker("<!-- PLAN_MODE_DENIED -->")

        if self.current_agent.name not in agent_templates:
            edit_ask = self.current_agent.should_ask_for_edit()
            bash_ask = self.current_agent.should_ask_for_bash()
            if edit_ask or bash_ask:
                restrictions = []
                if edit_ask:
                    restrictions.append("- File edits require user approval")
                if bash_ask:
                    restrictions.append("- Shell commands require user approval")
                system_parts.append("\n".join(restrictions))

        if self.current_agent.mode == AgentMode.SUBAGENT:
            system_parts.append(SUBAGENT_CONSTRAINTS)

        if self.current_agent.name not in agent_templates:
            if self.current_agent.permission_task != AgentPermission.DENY:
                if self.current_agent.mode.name == "SUBAGENT":
                    pass  # subagents don't need plan gate
                elif self.current_agent.permission_edit == AgentPermission.DENY and self.current_agent.permission_bash == AgentPermission.DENY:
                    pass  # read-only mode, no gate needed
                elif self.current_agent.permission_task == AgentPermission.DENY:
                    pass
                else:
                    gate = PLAN_GATE_HARD if self.current_agent.mode == AgentMode.PRIMARY and self.current_agent.name == "plan" else PLAN_GATE_SOFT
                    system_parts.append(gate)

        # Response style with CoT reasoning guidance.
        if self.current_agent.name in agent_templates:
            pass  # response style already embedded in the instruction templates
        elif self.current_agent.mode == AgentMode.SUBAGENT:
            system_parts.append(
                "\n## Response style\n"
                "- **Every round starts with Chain of Thought reasoning** "
                "inside `<thinking>`:\n"
                "  1. Review what the last round's tools produced — any errors?\n"
                "  2. Assess progress against the task — what remains?\n"
                "  3. Decide the next action.\n"
                "- If you need to reason between tool calls, wrap your "
                "reasoning in `<thinking>...</thinking>`.\n"
                "- **Intermediate rounds**: visible text is for progress "
                "updates only.  Do NOT announce "
                '"done" or "complete" unless ALL work is actually finished.\n'
                "- **FINAL round** (all work done): output a visible summary "
                "describing what was accomplished, changed, or decided — "
                "do NOT wrap in `<thinking>`.\n"
                "- **Asking the user**: when you need user feedback, input, or "
                "approval, ALWAYS use the AskUser tool to pause and wait for a "
                "response. Never output a question in visible text and continue "
                "executing — the session will not pause for your question.\n"
            )
        elif self.current_agent.permission_task != AgentPermission.DENY:
            system_parts.append(
                "\n## Response style\n"
                "- **Every round starts with Chain of Thought reasoning** "
                "inside `<thinking>`:\n"
                "  1. Review what the last round's tools produced — any errors?\n"
                "  2. Assess progress against todos — done / pending?\n"
                "  3. Decide the next single action — direct tool or `Spawn`?\n"
                "- **Plan-driven execution**:\n"
                "  - Output a step-by-step plan as Markdown first.\n"
                "  - Simple / single-step task → execute directly.\n"
                "  - Complex / multi-step task → `Spawn(agent_type, prompt)` to "
                "delegate execution.\n"
                "- If you need to reason between tool calls, wrap your "
                "reasoning in `<thinking>...</thinking>`.\n"
                "- **Intermediate rounds**: visible text is for progress "
                "updates only.  Do NOT announce "
                '"done" or "complete" unless ALL work is actually completed.\n'
                "- **FINAL round** (all work done): "
                "output a visible summary describing what was accomplished, "
                "what was changed, and any important outcomes or limitations — "
                "do NOT wrap in `<thinking>`.\n"
                "- **Asking the user**: when you need user feedback, input, or "
                "approval, ALWAYS use the AskUser tool to pause and wait for a "
                "response. Never output a question in visible text and continue "
                "executing — the session will not pause for your question.\n"
            )
        else:
            system_parts.append(
                "\n## Response style\n"
                "- **Every round starts with Chain of Thought reasoning** "
                "inside `<thinking>`:\n"
                "  1. Review what the last round's tools produced — any errors?\n"
                "  2. Assess progress — what remains?\n"
                "  3. Decide the next action.\n"
                "- If you need to reason between tool calls, wrap your "
                "reasoning in `<thinking>...</thinking>`.\n"
                "- **Intermediate rounds**: visible text is for progress "
                "updates only.  Do NOT announce "
                '"done" or "complete" unless ALL work is actually finished.\n'
                "- **FINAL round** (all work done): output a visible summary "
                "describing what was accomplished, changed, or decided — "
                "do NOT wrap in `<thinking>`.\n"
                "- **Asking the user**: when you need user feedback, input, or "
                "approval, ALWAYS use the AskUser tool to pause and wait for a "
                "response. Never output a question in visible text and continue "
                "executing — the session will not pause for your question.\n"
            )

        tagged_content = "<!-- AGENT_CONFIG -->\n" + "\n".join(system_parts)
        if not self.context.replace_system_section("<!-- AGENT_CONFIG -->", tagged_content):
            self.context.add_system(tagged_content)

        # Inject TOOL_DESCRIPTIONS as its own marker so it can be independently
        # stripped when the provider supports native tool schemas.
        tool_desc = filter_tool_descriptions(
            allowlist=self.current_agent.tools or None,
            denylist=self.current_agent.disallowed_tools or None,
        )
        tool_tagged = "<!-- TOOL_DESCRIPTIONS -->\n" + tool_desc
        if not self.context.replace_system_section("<!-- TOOL_DESCRIPTIONS -->", tool_tagged):
            self.context.add_system(tool_tagged)

        # Re-apply user permission overrides (e.g. "allow always")
        self._perm_store.apply_to(self.current_agent)

    def _strip_agent_config_tool_descriptions(self) -> None:
        """Remove the ``<!-- TOOL_DESCRIPTIONS -->`` system section.

        Called after the provider is known, for providers that support
        native tool schemas and don't need the prose TOOL_DESCRIPTIONS.
        """
        self.context.remove_system_by_marker("<!-- TOOL_DESCRIPTIONS -->")

    def get_available_tools(self) -> str:
        from onecode.agent.agents.types import filter_tool_descriptions
        return filter_tool_descriptions(
            allowlist=self.current_agent.tools or None,
            denylist=self.current_agent.disallowed_tools or None,
        )

    def _load_skills(self, force: bool = False) -> None:
        if self._skills_loaded and not force:
            return

        # Remove previously loaded skill-tagged messages so they don't
        # accumulate across agent switches or skill re-loads.
        self.context.remove_system_by_marker("<!-- SKILL:")
        self.context.remove_system_by_marker("<!-- PROJECT_DOC -->")
        self.context.remove_system_by_marker("<!-- CDH_PROJECT -->")
        self.context.remove_system_by_marker("<!-- AIDLC_NUDGE -->")
        self._skills_loaded = True

        has_cloudbase = False
        for skill in self._skill_loader.get_enabled():
            tagged = f"<!-- SKILL:{skill.name} -->\n{skill.content}"
            self.context.add_system(tagged)
            if skill.name in ("cloudbase", "tcb"):
                has_cloudbase = True

        if has_cloudbase:
            from onecode.mcp.cloudbase import ensure_configured as _ensure_cb
            needs_reconnect = not _ensure_cb(self._mcp)
            if not self._mcp.is_connected("cloudbase") or needs_reconnect:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        task = asyncio.create_task(self._mcp.connect("cloudbase"))
                        task.add_done_callback(
                            lambda t: logger.info("CloudBase MCP connection task completed")
                        )
                except Exception as e:
                    logger.warning("Failed to schedule CloudBase MCP connect: %s", e)

        # Project-level single-file doc (AGENTS.md at workspace root)
        from onecode.agent.project_doc import load_project_doc
        project_doc = load_project_doc(self._workspace)
        if project_doc:
            self.context.add_system(f"<!-- PROJECT_DOC -->\n{project_doc}")

        # Load project .cdh/ state into context
        cdh_content = CdhProjectLoader.load_for_workspace(self._workspace)
        if cdh_content:
            self.context.add_system(f"<!-- CDH_PROJECT -->\n{cdh_content}")

        # AI-DLC contextual nudge (passive triggering for AI-DLC projects)
        aidlc_nudge = CdhProjectLoader.load_aidlc_nudge(self._workspace)
        if aidlc_nudge:
            self.context.add_system(aidlc_nudge)

    def _inject_project_context(self, project_name: str) -> None:
        if not project_name:
            return
        if self._project_context_loaded:
            return

        self._project_context_loaded = True
        self._project_config = {}

        context_parts = [
            f"Project: {project_name}",
            f"Platform: {self._project_config.get('platform', 'unknown')}",
        ]

        env_id = self._project_config.get("cloudbase", {}).get("envId", "")
        if env_id:
            context_parts.append(f"TCB EnvId: {env_id}")

        self.context.add_system("\n".join(context_parts))

    def _should_retrieve_codebase(self) -> bool:
        try:
            cfg = self.app.config.codebase
            return cfg.enabled and cfg.auto_retrieve
        except Exception:
            return False

    async def _get_codebase_engine(self):
        if self._codebase_engine is not None:
            return self._codebase_engine
        try:
            cfg = self.app.config.codebase
            if not cfg.enabled:
                return None
            from onecode.codebase import CodebaseEngine
            self._codebase_engine = CodebaseEngine(self._project_dir, cfg)
            await self._codebase_engine.ensure_indexed()
            return self._codebase_engine
        except Exception as e:
            logger.warning("Failed to init codebase engine: %s", e)
            return None

    async def chat(self, user_input: str) -> str:
        await asyncio.to_thread(self._load_skills)

        project_name = getattr(self.app, "current_project", None) or ""
        if project_name:
            self._inject_project_context(project_name)

        self.context.add_user(user_input)

        # Proactive AI-DLC intent analysis for AI-DLC projects
        from cdh.project_loader import CdhProjectLoader
        if CdhProjectLoader.is_aidlc_project(self._workspace):
            intent_analysis = CdhProjectLoader.analyze_user_intent(user_input, self._workspace)
            if intent_analysis and intent_analysis.get("confidence", 0) >= 0.6:
                analysis_msg = (
                    f"\n<!-- AI-DLC Intent Analysis (auto-injected) -->\n"
                    f"User intent detected: {intent_analysis['suggestion']}\n"
                    f"Reasons: {', '.join(intent_analysis.get('reasons', []))}\n"
                    f"If this is an AI-DLC task, consider starting with phase: "
                    f"`{intent_analysis['phases'][0]}`\n"
                )
                self.context.add_system(analysis_msg)

        self.context.set_model(self.app.current_model)
        if self.context.should_compact():
            level = self.context.compact()
            if level not in ("none",):
                logger.info("Context compaction applied: %s", level)

        provider_cls = ProviderRegistry.get(self.app.current_provider)
        if not provider_cls:
            return f"Provider '{self.app.current_provider}' not available."

        config = self.app.config.providers.get(self.app.current_provider)
        if config is None:
            return f"Provider '{self.app.current_provider}' not configured."

        provider = provider_cls(
            api_key=config.api_key or "",
            endpoint=config.endpoint or None,
        )

        response = await provider.chat(
            self.context.get_context(),
            model=self.app.current_model,
        )

        self.context.add_assistant(response.content)
        self.iterations += 1
        self.total_tokens += response.usage.get("total_tokens", 0)
        return response.content

    def _parse_tool_calls(self, text: str) -> list[dict]:
        calls = []
        for match in TOOL_CALL_RE.finditer(text):
            name = match.group(1)
            call_id = match.group(2)
            raw_input = match.group(3).strip()
            try:
                parsed_input = json.loads(raw_input) if raw_input else {}
            except json.JSONDecodeError:
                parsed_input = {"raw": raw_input}
            calls.append({"name": name, "id": call_id, "input": parsed_input})
        return calls

    def _validate_edit(self, path: str) -> str | None:
        try:
            content = self.file_ops.read(path, 0, 0)
            if content and "error" not in str(content).lower():
                return None
            return f"Warning: File may not have been written correctly: {path}"
        except Exception as e:
            return f"Warning: Could not verify file: {e}"

    def _tool_category(self, name: str) -> str:
        """Map tool name to category for structured display."""
        from onecode.models.messages import get_tool_category
        return get_tool_category(name).value

    _TOOL_NAME_TO_PERM_KEY: dict[str, str] = {
        "Read": "read",
        "Write": "edit",
        "Edit": "edit",
        "Insert": "edit",
        "UndoEdit": "edit",
        "ApplyPatch": "edit",
        "Bash": "bash",
        "WebFetch": "webfetch",
        "WebSearch": "websearch",
        "Glob": "glob",
        "Grep": "grep",
        "List": "list",
        "Spawn": "task",
        "Agent": "task",
        "Skill": "skill",
        "codebase_search": "read",
        "TodoCreate": "todowrite",
        "TodoUpdate": "todowrite",
        "TodoStop": "todowrite",
        "TodoClear": "todowrite",
        "TodoGet": "todoread",
        "TodoList": "todoread",
        "TodoOutput": "todoread",
    }

    def _check_tool_permission(self, name: str, inp: dict) -> str | None:
        """Unified agent-level permission check for all tools."""
        from onecode.agent.agents.types import AgentPermission
        # Enforce agent allow/deny lists at runtime. This is the runtime
        # safety net behind filter_tool_descriptions(): even if the LLM
        # still emits a tool the system prompt hid (e.g. TodoCreate in a
        # subagent, after context compaction re-introduced the name), the
        # call is denied here rather than leaking through.
        if not self.current_agent.tool_allowed(name):
            return json.dumps({"success": False, "error": f"{name} denied (disallowed for {self.current_agent.name})"})
        perm_key = self._TOOL_NAME_TO_PERM_KEY.get(name)
        tools_config = self.current_agent.get_tools_config()
        if perm_key is None:
            # Fallback: if tool is not in the explicit mapping, check whether
            # it is read-only. If not, treat it as an edit-tool and use the
            # edit permission. This catches tools like ConfigWrite, CronCreate,
            # Worktree, MCPTool, etc. that would otherwise bypass plan mode.
            spec = self._tool_registry.get(name)
            if spec and not spec.spec().is_read_only:
                perm = tools_config.get("edit", AgentPermission.ALLOW)
                if perm == AgentPermission.DENY:
                    return json.dumps({"success": False, "error": f"{name} denied (read-only mode)"})
                if perm == AgentPermission.ASK:
                    return json.dumps({"success": False, "error": f"{name} requires approval", "requires_approval": True})
            return None
        perm = tools_config.get(perm_key, AgentPermission.ALLOW)
        if perm == AgentPermission.DENY:
            return json.dumps({"success": False, "error": f"{name} denied"})
        if perm == AgentPermission.ASK:
            return json.dumps({"success": False, "error": f"{name} requires approval", "requires_approval": True})
        return None

    def hidden_tool_names(self) -> set[str]:
        """Tools that must NOT be advertised to the LLM for the current agent.

        Mirrors ``_check_tool_permission`` exactly: a tool is hidden when it
        is disallowed by the agent's allow/deny lists, or when its permission
        key resolves to hard DENY. Unmapped non-read-only tools fall back to
        the edit permission, matching the runtime fallback.
        """
        from onecode.agent.agents.types import AgentPermission
        agent = self.current_agent
        tools_config = agent.get_tools_config()
        hidden: set[str] = set()
        for spec in self._tool_registry.list_specs():
            name = spec.name
            if not agent.tool_allowed(name):
                hidden.add(name)
                continue
            perm_key = self._TOOL_NAME_TO_PERM_KEY.get(name)
            if perm_key is not None:
                if tools_config.get(perm_key, AgentPermission.ALLOW) == AgentPermission.DENY:
                    hidden.add(name)
            elif not spec.is_read_only:
                if tools_config.get("edit", AgentPermission.ALLOW) == AgentPermission.DENY:
                    hidden.add(name)
        return hidden

    def _register_tool_denial(self, name: str) -> None:
        """Track repeated permission denials for one tool and inject an
        escalating hint so the model stops retrying calls that can never
        succeed in the current mode."""
        count = self._tool_denial_count.get(name, 0) + 1
        self._tool_denial_count[name] = count
        marker = f"<!-- TOOL_DENIED_{name} -->"
        self.context.remove_system_by_marker(marker)
        if count >= 3:
            self.context.insert_system_before_non_system(
                f"{marker}\n"
                f"## Repeatedly blocked tool: {name}\n"
                f"You have tried to use `{name}` {count} times and it was "
                f"denied every time. It will NEVER succeed in the current "
                f"agent/mode. Stop calling it. Re-read the plan and the "
                f"available tool list, adjust your approach, or use AskUser "
                f"to ask the user how to proceed."
            )
        else:
            self.context.insert_system_before_non_system(
                f"{marker}\n"
                f"You attempted to use `{name}` but it was denied by the "
                f"current agent's permissions. Do NOT retry the same call — "
                f"adjust your approach or ask the user via AskUser."
            )

    def _save_plan_document(self, plan_text: str) -> str | None:
        """Persist the submitted plan to ``.cdh/plans/plan-{id}.md``.

        Returns the absolute path, or None on failure. The document survives
        context compaction and is re-read by the execution agent at handoff.
        """
        try:
            from onecode.agent.cdh_loader import CdhProjectLoader
            cdh_dir = CdhProjectLoader.find_cdh_dir_for_todos(self._project_dir)
            if cdh_dir is None:
                cdh_dir = self._project_dir / CdhProjectLoader.CDH_DIRNAME
            plans_dir = cdh_dir / "plans"
            plans_dir.mkdir(parents=True, exist_ok=True)
            path = plans_dir / f"plan-{int(time.time())}.md"
            path.write_text(plan_text or "(empty plan)", "utf-8")
            return str(path)
        except Exception as e:
            logger.warning("Failed to save plan document: %s", e)
            return None

    def _plan_handoff(self, plan_path: str | None) -> None:
        """Switch from the plan agent to the execution agent after approval.

        Keeps the approved task list (todos) and injects the approved plan
        document into the execution agent's system context so it survives
        compaction and stays the single source of truth.
        """
        try:
            if self.current_agent.name != "plan":
                return
            self.set_agent("solo", keep_todos=True)
            plan_text = ""
            if plan_path:
                try:
                    plan_text = Path(plan_path).read_text("utf-8")
                except Exception:
                    plan_text = ""
            todos = "\n".join(
                f"- [{t['id']}] {t['subject']}"
                for t in self._todo_manager.list_todos()
            )
            section = (
                "<!-- APPROVED_PLAN -->\n"
                "## Approved plan (execution mode)\n"
                f"Plan document: {plan_path}\n\n"
                f"{plan_text}\n\n"
                "### Task list\n"
                f"{todos or '(empty)'}\n\n"
                "Execute the approved plan: work through the task list and "
                "mark each todo completed via TodoUpdate as you finish it."
            )
            if not self.context.replace_system_section("<!-- APPROVED_PLAN -->", section):
                self.context.insert_system_before_non_system(section)
        except Exception as e:
            logger.warning("Plan handoff failed: %s", e)

    def _react_phase_text(self, round_no: int) -> str:
        """Per-round CoT guidance header; the plan agent has its own stages."""
        if self.current_agent and self.current_agent.name == "plan":
            return f"<!-- REACT_PHASE -->\n## Round {round_no} — 思考 → 规划 → 审批\n"
        return f"<!-- REACT_PHASE -->\n## Round {round_no} — 思考 → Todo → 行动\n"

    async def _execute_tool(self, tool_call: dict) -> dict:
        from onecode.agent.tools.registry import ToolCall as RegistryToolCall
        name = tool_call["name"]
        tid = tool_call["id"]
        inp = tool_call["input"]
        category = self._tool_category(name)
        base = {"tool_use_id": tid, "is_error": False, "category": category}
        try:
            denied = self._check_tool_permission(name, inp)
            if denied:
                self._register_tool_denial(name)
                return {**base, "content": denied, "is_error": True}

            call = RegistryToolCall(name=name, input=inp, tool_use_id=tid)
            result = await self._tool_registry.dispatch_async(
                call, cancel_check=lambda: self._cancelled,
            )

            # Handle SendMessage tracking
            if name == "SendMessage":
                msg_output = result.output if isinstance(result.output, dict) else {}
                self._last_user_msg = msg_output.get("message", "")
                return {**base, "content": json.dumps(result.output), "is_error": result.is_error}

            # Format output for backward compatibility
            output = self._format_tool_output(result)
            return {**base, "content": output, "is_error": result.is_error}
        except Exception as e:
            logger.exception(f"Tool execution error: {e}")
            return {**base, "content": f"Error: {safe_error_msg(e)}", "is_error": True}

    def _format_tool_output(self, result: RegistryToolResult) -> str:  # noqa: F821
        import json
        output = result.output
        if isinstance(output, str):
            return output
        try:
            return json.dumps(output)
        except (TypeError, ValueError):
            return str(output)

    def cancel(self):
        """Cancel the current chat_stream turn and all in-flight subagents."""
        self._cancelled = True
        for child in self._child_engines:
            child._cancelled = True
        self._mcp.cancel_all()

    async def shutdown(self):
        """Release OS resources held by this engine (LSP, MCP, cron)."""
        self._cancelled = True
        for child in self._child_engines:
            child._cancelled = True
        self._lsp_tool.stop_all()
        await self._mcp.disconnect_all()
        self._cron_scheduler.stop_loop()

    def __del__(self):
        """Fallback cleanup on garbage collection — wrapped in try/except
        to avoid crashing during interpreter teardown when modules may
        already be collected."""
        try:
            self._lsp_tool.stop_all()
        except Exception:
            pass
        try:
            self._cron_scheduler.stop_loop()
        except Exception:
            pass

    async def chat_stream(self, user_input: str | list[dict]) -> AsyncIterator[StreamEvent | str]:
        await asyncio.to_thread(self._load_skills)
        self._ctx_err_retries = 0
        self._verification_fail_count = 0
        preview = user_input[:100] if isinstance(user_input, str) else f"[{len(user_input)} content blocks]"
        logger.info(f"chat_stream() called with user_input='{preview}'")

        project_name = getattr(self.app, "current_project", None) or ""
        if project_name:
            was_context_loaded = self._project_context_loaded
            self._inject_project_context(project_name)
            if not was_context_loaded:
                yield StreamEvent.text_delta(
                    f"\n📋 项目: {project_name}\n继续开发中...\n\n"
                )
        else:
            pass

        # Emit initial plan so the TUI Plan widget is mounted (or refreshed
        # to the current snapshot) at the start of every turn.  This is
        # required because the Plan widget only renders when an ``entries``
        # value arrives — without this, the widget never appears until the
        # agent happens to call a task tool.
        for event in self._emit_plan_update():
            yield event
        self._plan_dirty = False

        # ── Codebase auto-retrieval ──
        # Skipped entirely for subagent engines (see _disable_retrieval)
        # to avoid the 2.3s+ indexer loop and the per-chunk embedding httpx
        # calls that block the event loop and freeze streaming/cancel.
        # Also skipped when _ctx_crisis is set to prevent "compact →
        # re-inject → compact" loops after a ContextLengthError recovery.
        if (
            isinstance(user_input, str)
            and self._should_retrieve_codebase()
            and not self._disable_retrieval
            and not self._ctx_crisis
        ):
            try:
                engine = await self._get_codebase_engine()
                if engine:
                    chunks = await engine.retrieve(user_input)
                    ctx_text = engine.format_context(
                        chunks, max_tokens=self.app.config.codebase.max_chunk_tokens
                    )
                    if ctx_text:
                        tagged = f"<!-- CODEBASE -->\n{ctx_text}"
                        if not self.context.replace_system_section("<!-- CODEBASE -->", tagged):
                            self.context.add_system(tagged)
                    else:
                        self.context.remove_system_by_marker("<!-- CODEBASE -->")
            except Exception as e:
                logger.warning("Codebase retrieval failed: %s", e)

        # ── Long-term memory recall ──
        if (
            isinstance(user_input, str)
            and self._session
            and self.app.config.memory.enabled
            and self.app.config.memory.auto_recall
            and not self._disable_retrieval
            and not self._ctx_crisis
        ):
            try:
                top_k = self.app.config.memory.top_k
                results = self._memory.search_memories(user_input, top_k=top_k)
                if results:
                    lines = ["## Relevant past memories"]
                    for r in results:
                        lines.append(r.content[:300])
                    tagged = "<!-- MEMORY -->\n" + "\n".join(lines)
                    if not self.context.replace_system_section("<!-- MEMORY -->", tagged):
                        self.context.add_system(tagged)
                else:
                    self.context.remove_system_by_marker("<!-- MEMORY -->")
            except Exception as e:
                logger.warning("Memory recall failed: %s", e)

        # ── REACT_PHASE must be injected BEFORE add_user so system
        # messages stay at the top of the message list.  On subsequent
        # chat_stream calls replace_system_section updates it in-place.
        cot_phase_init = self._react_phase_text(1)
        if not self.context.replace_system_section("<!-- REACT_PHASE -->", cot_phase_init):
            self.context.add_system(cot_phase_init)

        self.context.add_user(user_input)

        # Plan gate: activate based on agent mode, not content heuristics.
        # Gate fires reactively when agent tries execution tools without a plan.
        self._plan_gate_mode = self._resolve_plan_gate_mode()

        self.context.set_model(self.app.current_model)
        if self.context.should_compact():
            level = self.context.compact()
            if level not in ("none",):
                logger.info("Context compaction at turn start: %s", level)

        provider_name = self.app.current_provider
        model_name = self.app.current_model
        logger.info(f"Using provider='{provider_name}', model='{model_name}'")
        logger.info(
            "chat_stream engine state: project=%s agent=%s todos=%d context_msgs=%d ctx_tokens=%d",
            project_name or "(none)",
            self.current_agent.name if self.current_agent else "None",
            len(self._todo_manager.list_todos()),
            len(self.context.messages),
            self.context._token_count,
        )

        provider_cls = ProviderRegistry.get(provider_name)
        if not provider_cls:
            available = list(ProviderRegistry._registry.keys()) if hasattr(ProviderRegistry, '_registry') else "unknown"
            error_msg = f"Provider '{provider_name}' not available. Available: {available}"
            logger.error(error_msg)
            yield StreamEvent.error(error_msg)
            return

        config = self.app.config.providers.get(provider_name)
        if config is None:
            available = list(self.app.config.providers.keys())
            error_msg = f"Provider '{provider_name}' not configured. Available providers: {available}"
            logger.error(error_msg)
            yield StreamEvent.error(error_msg)
            return

        logger.info(f"Creating provider instance: {provider_cls.__name__}")
        provider_kwargs = dict(api_key=config.api_key or "", endpoint=config.endpoint or None)
        provider = provider_cls(**provider_kwargs)

        # If the provider supports native tool schemas (OpenAI/Anthropic/DeepSeek
        # etc.), strip the prose TOOL_DESCRIPTIONS from system context to save
        # tokens. The structured ``tools`` kwarg provides the same info.
        if not hasattr(provider, 'supports_native_tools') or provider.supports_native_tools():
            self._strip_agent_config_tool_descriptions()

        # Reset per-turn usage tracking
        self._turn_usages = []

        # Guard against concurrent chat_stream calls: if the engine was
        # already cancelled before the adapter called us, honour that.
        # Do NOT blindly reset _cancelled — a caller may have called
        # cancel() between turn boundary.
        if self._cancelled:
            logger.warning("chat_stream: engine already cancelled, aborting")
            yield StreamEvent.text_delta("\n\n*Cancelled*\n\n")
            return

        # ── Agent loop: 思考 → Todo → 行动 (per-Round) ──
        is_anthropic = provider.is_anthropic_style()
        max_turns = self.current_agent.max_turns or 5000
        hard_limit = max_turns
        hard_limit_extensions = 0
        max_hard_limit_extensions = float('inf') if (
            self.current_agent.name == "solo" or self._has_pending_todos()
        ) else 5

        def _infinite_turns():
            t = 0
            while True:
                yield t
                t += 1

        for turn in _infinite_turns():
            # Absolute ceiling: never exceed max_iterations (safety net)
            absolute_ceiling = self.app.config.agent.max_iterations
            if turn >= absolute_ceiling:
                if not self._has_pending_todos():
                    logger.warning(
                        "Absolute ceiling (%d) reached at turn %d — stopping",
                        absolute_ceiling, turn,
                    )
                    break
            # Dynamic extension: if hard_limit reached but agent is still
            # actively working (pending todos, or just called tools), keep going.
            if turn >= hard_limit:
                if hard_limit_extensions < max_hard_limit_extensions and (
                    self._has_pending_todos() or self._empty_tool_turns == 0
                ):
                    pending = sum(1 for t in self._todo_manager.list_todos()
                                  if t.get("status") in ("pending", "in_progress"))
                    hard_limit_extensions += 1
                    logger.info(
                        "hard_limit (%d) reached at turn %d with %d pending todos — "
                        "extending dynamically (extension %d/%d)",
                        hard_limit, turn, pending,
                        hard_limit_extensions, max_hard_limit_extensions,
                    )
                    hard_limit += 20
                    lines = [
                        "<!-- FORCE_CONTINUE -->",
                        f"## {turn} rounds completed, {pending} todos still pending",
                        "Continue executing the next todo. Do NOT stop or summarise.",
                    ]
                    self._inject_nudge(lines)
                else:
                    if self._has_pending_todos():
                        pending = sum(1 for t in self._todo_manager.list_todos()
                                      if t.get("status") in ("pending", "in_progress"))
                        logger.warning(
                            "hard_limit extensions exhausted at turn %d with %d pending todos — pausing",
                            turn, pending,
                        )
                        yield StreamEvent.text_delta(
                            f"\n\n*Pausing: hard_limit extensions exhausted with {pending} pending todos. "
                            "Type 'continue' to proceed or 'stop' to end.*\n\n"
                        )
                        return
            if self._cancelled:
                self._cleanup_injected_messages()
                yield StreamEvent.text_delta("\n\n*Turn cancelled*\n\n")
                return

            # ── Thought Phase: update CoT reasoning guidance for this turn ──
            # Cleanup stale reminders that may have accumulated
            self.context.remove_system_by_marker("<!-- ROUTING_REMINDER -->")
            self.context.remove_system_by_marker("<!-- PLAN_REMINDER -->")
            # Inject (or refresh) a nudge that prioritizes any unfinished todos
            # from this session. The marker is replaced in-place so the context
            # stays bounded — the agent always sees the current open list.
            self._refresh_pending_todos_nudge()
            if turn > 0:
                self.context.replace_system_section(
                    "<!-- REACT_PHASE -->",
                    self._react_phase_text(turn + 1),
                )

            self._pending_thinking_blocks = []

            self.context.set_model(self.app.current_model)
            if self.context.should_compact():
                level = self.context.compact()
                if level not in ("none",):
                    logger.info("Context compaction at turn %d: %s", turn, level)
            elif turn > 0 and turn % 3 == 0:
                self.context._update_token_count()
                logger.debug("Periodic token recalibration at turn %d: ~%d tokens",
                             turn + 1, self.context._token_count)

            turn_retries = 0
            turn_usage: dict[str, int] = {}
            response_text = ""
            tool_uses: list[dict] = []

            try:
                context_messages = self.context.get_context()
                logger.info(f"Calling provider.chat_stream_response (turn {turn+1})")
                self._streaming_used = False
                if self.on_text_chunk is not None:
                    _original_cb = self.on_text_chunk
                    def _stream_wrapper(text: str) -> None:
                        self._streaming_used = True
                        if self._cancelled:
                            raise TurnCancelledError()
                        _original_cb(text)
                    stream_cb = _stream_wrapper
                else:
                    stream_cb = None
                chat_response = await provider.chat_stream_response(
                    context_messages,
                    model=model_name,
                    on_text_chunk=stream_cb,
                    on_tool_call_delta=self.on_tool_call_delta,
                    cancel_check=lambda: self._cancelled,
                    tools=self._tool_registry.make_openai_schemas(
                        exclude=self.hidden_tool_names()
                    ),
                )
                response_text = chat_response.content
                tool_uses = chat_response.tool_uses
                if not tool_uses and (
                    "<minimax:tool_call>" in response_text
                    or _LEGACY_OPEN in response_text
                ):
                    parsed_uses, response_text, self._tool_id_counter = (
                        _extract_minimax_tool_uses(
                            response_text, id_start=self._tool_id_counter
                        )
                    )
                    legacy_uses, response_text, self._tool_id_counter = (
                        _extract_legacy_tool_uses(
                            response_text, id_start=self._tool_id_counter
                        )
                    )
                    tool_uses = parsed_uses + legacy_uses
                    if tool_uses:
                        logger.info(
                            "Extracted %d text tool uses (%d minimax, %d legacy) from response",
                            len(tool_uses), len(parsed_uses), len(legacy_uses),
                        )
                if chat_response.usage:
                    turn_usage = chat_response.usage
            except NotImplementedError:
                logger.info("chat_stream_response not supported, falling back to non-streaming chat()")
                try:
                    context_messages = self.context.get_context()
                    model_response = await provider.chat(
                        context_messages,
                        model=model_name,
                    tools=self._tool_registry.make_openai_schemas(
                        exclude=self.hidden_tool_names()
                    ),
                    )
                    response_text = model_response.get_text()
                    tool_uses = [
                        {"id": tu.id, "name": tu.name, "input": tu.input}
                        for cb in model_response.content
                        if cb.type == ContentBlockType.TOOL_USE and cb.tool_use
                        for tu in [cb.tool_use]
                    ]
                    if not tool_uses and (
                        "<minimax:tool_call>" in response_text
                        or _LEGACY_OPEN in response_text
                    ):
                        parsed_uses, response_text, self._tool_id_counter = (
                            _extract_minimax_tool_uses(
                                response_text, id_start=self._tool_id_counter
                            )
                        )
                        legacy_uses, response_text, self._tool_id_counter = (
                            _extract_legacy_tool_uses(
                                response_text, id_start=self._tool_id_counter
                            )
                        )
                        tool_uses = parsed_uses + legacy_uses
                        if tool_uses:
                            logger.info(
                                "Extracted %d text tool uses (%d minimax, %d legacy) from chat() fallback",
                                len(tool_uses), len(parsed_uses), len(legacy_uses),
                            )
                    if model_response.usage:
                        turn_usage = model_response.usage
                except TransientProviderError:
                    raise  # propagate to outer TransientProviderError handler for retry
                except (KeyboardInterrupt, asyncio.CancelledError):
                    self._cleanup_injected_messages()
                    yield StreamEvent.text_delta("\n\n*Turn cancelled*\n\n")
                    return
                except Exception as e:
                    logger.exception(f"Error during chat() fallback turn {turn+1}: {e}")
                    if self._has_pending_todos():
                        pending = sum(1 for t in self._todo_manager.list_todos()
                                      if t.get("status") in ("pending", "in_progress"))
                        yield StreamEvent.text_delta(
                            f"\n\n*Error: {safe_error_msg(e)}, {pending} todos remaining. Attempting to continue...*\n\n"
                        )
                        continue
                    yield StreamEvent.error(safe_error_msg(e))
                    break
            except TurnCancelledError:
                self._cleanup_injected_messages()
                yield StreamEvent.text_delta("\n\n*Turn cancelled*\n\n")
                return
            except ContextLengthError as e:
                ctx_retries = getattr(self, '_ctx_err_retries', 0) + 1
                self._ctx_err_retries = ctx_retries
                ctx_msgs_before = len(self.context.messages)
                ctx_tokens_before = self.context._token_count
                logger.warning(
                    "ContextLengthError on turn %d (ctx_attempt %d): %s\n"
                    "  context_msgs=%d ctx_tokens=%d — forcing compaction",
                    turn + 1, ctx_retries, e,
                    ctx_msgs_before, ctx_tokens_before,
                )
                self._turn_events.append({
                    "turn": turn + 1,
                    "kind": "context_overflow_retry",
                    "ctx_retries": ctx_retries,
                    "message": str(e),
                })
                if ctx_retries >= 3:
                    logger.error(
                        "ContextLengthError exhausted %d compaction retries "
                        "on turn %d — giving up", ctx_retries, turn + 1,
                    )
                    self._turn_events.append({
                        "turn": turn + 1,
                        "kind": "context_overflow_exhausted",
                        "ctx_retries": ctx_retries,
                        "message": str(e),
                    })
                    yield StreamEvent.error(
                        f"Context length exceeded (turn {turn+1}), "
                        f"compaction exhausted after {ctx_retries} attempts"
                    )
                    if self._has_pending_todos():
                        pending = sum(1 for t in self._todo_manager.list_todos()
                                      if t.get("status") in ("pending", "in_progress"))
                        yield StreamEvent.text_delta(
                            f"\n\n*Context overflow with {pending} pending todos. Pausing for user input...*\n\n"
                        )
                        return
                    break
                level = self.context.compact()
                ctx_tokens_after = self.context._token_count
                tokens_unchanged = ctx_tokens_after >= ctx_tokens_before
                if tokens_unchanged and ctx_retries >= 2:
                    self._ctx_crisis = True
                    for marker in ("<!-- SKILL:", "<!-- AI-DLC:",
                                   "<!-- PROJECT_DOC -->",
                                   "<!-- CODEBASE -->", "<!-- MEMORY -->",
                                   "<!-- CDH_PROJECT -->", "<!-- COMPACT_SUMMARY -->"):
                        removed = self.context.remove_system_by_marker(marker)
                        if removed:
                            logger.info(
                                "ContextLengthError crisis: removed %d system "
                                "msg(s) with marker %s", removed, marker,
                            )
                    level = self.context.compact()
                    ctx_tokens_after = self.context._token_count
                if ctx_tokens_after >= ctx_tokens_before and self._ctx_crisis:
                    for m in self.context.messages:
                        if m.role == "system" and isinstance(m.content, str) and len(m.content) > 2000:
                            m.content = m.content[:2000] + "\n... [emergency truncation]"
                    self.context._update_token_count()
                    ctx_tokens_after = self.context._token_count
                if ctx_tokens_after < ctx_tokens_before:
                    logger.info(
                        "ContextLengthError recovery (ctx_attempt %d): compact "
                        "level=%s tokens %d→%d, retrying turn %d",
                        ctx_retries, level, ctx_tokens_before,
                        ctx_tokens_after, turn + 1,
                    )
                    yield StreamEvent.text_delta(
                        "\n\n*Context window exceeded, compressing and retrying…*\n\n"
                    )
                    continue
                logger.error(
                    "ContextLengthError recovery failed (ctx_attempt %d): "
                    "level=%s tokens before=%d after=%d",
                    ctx_retries, level, ctx_tokens_before, ctx_tokens_after,
                )
                yield StreamEvent.error(
                    f"Context length exceeded (turn {turn+1}), "
                    f"compaction did not reduce tokens"
                )
                break
            except TransientProviderError as e:
                turn_retries += 1
                max_retries = self._cfg.retry.max_attempts
                backoff_max = self._cfg.retry.backoff_max
                backoff_jitter = self._cfg.retry.backoff_jitter
                if turn_retries <= max_retries:
                    if self._cancelled:
                        self._cleanup_injected_messages()
                        yield StreamEvent.text_delta("\n\n*Turn cancelled*\n\n")
                        return
                    if e.retry_after is not None:
                        delay = max(0.0, e.retry_after)
                    else:
                        delay = min(2 ** (turn_retries - 1), backoff_max)
                    jitter = random.uniform(-backoff_jitter, backoff_jitter) if backoff_jitter > 0 else 0.0
                    delay = max(0.1, delay + jitter)
                    logger.warning(
                        "Transient provider error on turn %d, "
                        "retry %d/%d after %.1fs: %s",
                        turn + 1, turn_retries, max_retries, delay, e,
                    )
                    self._turn_events.append({
                        "turn": turn + 1,
                        "kind": "provider_error_retry",
                        "retry": turn_retries,
                        "delay": round(delay, 2),
                        "message": str(e),
                    })
                    yield StreamEvent.text_delta(
                        f"\n\n*Transient error, retrying in {delay:.1f}s…*\n\n"
                    )
                    await asyncio.sleep(delay)
                    continue
                ctx_msgs = len(self.context.messages)
                ctx_tokens = self.context._token_count
                logger.exception(
                    f"Transient provider error on turn {turn+1} "
                    f"(exhausted {turn_retries} retries): {e}\n"
                    f"  provider={provider_name} model={model_name} "
                    f"context_msgs={ctx_msgs} ctx_tokens={ctx_tokens}"
                )
                self._turn_events.append({
                    "turn": turn + 1,
                    "kind": "provider_error_exhausted",
                    "message": str(e),
                })
                yield StreamEvent.error(f"Provider error (turn {turn+1}): {safe_error_msg(e)}")
                if self._has_pending_todos():
                    pending = sum(1 for t in self._todo_manager.list_todos()
                                  if t.get("status") in ("pending", "in_progress"))
                    yield StreamEvent.text_delta(
                        f"\n\n*Transient error exhausted with {pending} pending todos. Pausing for user input...*\n\n"
                    )
                    return
                break
            except (KeyboardInterrupt, asyncio.CancelledError):
                self._cleanup_injected_messages()
                yield StreamEvent.text_delta("\n\n*Turn cancelled*\n\n")
                return
            except Exception as e:
                ctx_msgs = len(self.context.messages)
                ctx_tokens = self.context._token_count
                logger.exception(
                    f"Error during chat_stream_response turn {turn+1}: {e}\n"
                    f"  provider={provider_name} model={model_name} "
                    f"context_msgs={ctx_msgs} ctx_tokens={ctx_tokens}"
                )
                if self._has_pending_todos():
                    pending = sum(1 for t in self._todo_manager.list_todos()
                                  if t.get("status") in ("pending", "in_progress"))
                    logger.info(f"Error with %d pending todos, attempting to continue...", pending)
                    yield StreamEvent.text_delta(
                        f"\n\n*Error: {safe_error_msg(e)}, {pending} todos remaining. Attempting to continue...*\n\n"
                    )
                    continue
                yield StreamEvent.error(f"Provider error (turn {turn+1}): {safe_error_msg(e)}")
                break

            # Check cancellation after provider call (covers non-streaming
            # responses and cases where on_text_chunk was never called).
            if self._cancelled:
                self._cleanup_injected_messages()
                yield StreamEvent.text_delta("\n\n*Turn cancelled*\n\n")
                return

            # Track usage
            self._turn_usages.append(turn_usage)
            if turn_usage:
                self.total_tokens += turn_usage.get("total_tokens", 0)

            # Extract thinking blocks from response. In the streaming path
            # the adapter's _make_stream_callback already stripped <thinking>
            # markers from the text and routed them through self.on_thinking
            # (which appends to _pending_thinking_blocks). The non-streaming
            # fallback still has the markers inline, so we parse them here.
            thinking_blocks = list(self._pending_thinking_blocks)
            clean_text = response_text
            for match in THINKING_RE.finditer(response_text):
                tb = match.group(1)
                if tb not in thinking_blocks:
                    thinking_blocks.append(tb)
            if thinking_blocks or self._pending_thinking_blocks:
                clean_text = THINKING_RE.sub('', response_text).strip()
                if not self._streaming_used:
                    for tb in thinking_blocks:
                        yield StreamEvent.thinking(tb)

            # Log the raw model response so developers can verify the
            # model is actually emitting ``<thinking>`` markers (and not
            # bleeding planning prose into the visible answer).  Goes
            # to the onecode root logger → ~/.onecode/logs/onecode.log when
            # ``setup_logging(DEBUG)`` is in effect.
            logger.debug(
                "RAW_RESPONSE turn=%d text_len=%d first_200=%r "
                "thinking_blocks=%d tool_uses=%d streaming_used=%s",
                turn + 1,
                len(response_text),
                response_text[:200],
                len(thinking_blocks),
                len(tool_uses),
                self._streaming_used,
            )

            # ── Auto-ask detection: if the LLM output a question as plain text,
            # the Do phase should become AskUser — regardless of whether tool
            # calls accompanied it. Instead of executing the original tools
            # (which may depend on the answer) or treating the turn as an
            # empty round (which would bury the question and queue the user's
            # input), we REPLACE tool_uses with a single AskUser tool call.
            # The normal tool execution loop then handles AskUser naturally,
            # pausing until the user responds.
            #
            # Detection logic uses strict=True only: semantic intent OR trailing
            # `?`/`？` triggers auto-ask. Implementation tools (Read/Write/Grep/
            # Bash/etc.) are excluded — a question before file operations is
            # unlikely to need user input.
            from onecode.agent.question_detect import looks_like_question

            _IMPLEMENTATION_TOOLS = {
                "Read", "Write", "Edit", "Glob", "Grep", "Bash", "Search",
                "WebFetch", "Run", "Execute", "Tool", "Task", "TodoWrite",
                "TodoClear", "TodoSet", "SlotSet", "ContextGet", "ContextSet",
            }
            _tool_names = {tu.get("name") for tu in tool_uses}
            _has_impl_tools = bool(_tool_names & _IMPLEMENTATION_TOOLS)

            _is_auto_ask = bool(
                clean_text and
                looks_like_question(clean_text, strict=True) and
                not _has_impl_tools
            )

            if _is_auto_ask:
                _ask_id = f"auto-ask-{self._tool_id_counter}"
                self._tool_id_counter += 1
                # Show the trailing question sentence in the dialog instead of
                # dumping the whole preamble into the AskUser widget.
                from onecode.agent.question_detect import compact_question
                _ask_question = compact_question(clean_text)
                tool_uses = [{
                    "id": _ask_id,
                    "name": "AskUser",
                    "input": {"question": _ask_question},
                }]

            # Add assistant response to context with proper content blocks.
            # Persist thinking blocks so they survive session reload — the
            # TUI replays them as collapsible Thought widgets.
            if tool_uses or thinking_blocks:
                assistant_blocks: list = []
                for tb in thinking_blocks:
                    assistant_blocks.append({"type": "thinking", "thinking": tb})
                if clean_text:
                    assistant_blocks.append({"type": "text", "text": clean_text})
                for tu in tool_uses:
                    assistant_blocks.append({
                        "type": "tool_use",
                        "id": tu["id"],
                        "name": tu["name"],
                        "input": tu["input"],
                    })
                self.context.add_assistant(assistant_blocks)
            else:
                self.context.add_assistant(clean_text)

            self.iterations += 1
            self._ctx_err_retries = 0

            # Always yield text content as TEXT_DELTA, regardless of tool uses.
            # Without this, subagent text is consumed silently when it also
            # emits tool calls — the text goes to context but never reaches
            # _spawn_subagent_async_streaming / the subagent_chunk stream.
            if not self._streaming_used and clean_text.strip():
                for i in range(0, len(clean_text), 12):
                    yield StreamEvent.text_delta(clean_text[i:i + 12])

            if not tool_uses:
                # ── Store conversation in long-term memory ──
                if self._session:
                    try:
                        conv_id = self._session.id
                        input_str = user_input if isinstance(user_input, str) else str(user_input)
                        self._memory.remember(
                            MemoryLayer.L0_CONVERSATION,
                            f"user: {input_str}\nassistant: {clean_text}",
                            {"conversation_id": conv_id},
                        )
                    except Exception as e:
                        logger.warning("Memory store failed: %s", e)

                # ── Force continuation if todos remain ──
                # After subagents complete, the LLM may stop calling tools
                # because the structured output strongly signals "done".
                # If there are still pending/in-progress todos, inject a
                # forceful continuation nudge and loop again instead of
                # exiting the turn loop.
                self._empty_tool_turns += 1
                max_empty_turns = getattr(self._cfg.agent, 'max_empty_turns', 10)
                if self._has_pending_todos():
                    if self._empty_tool_turns >= max_empty_turns:
                        pending_count = sum(
                            1 for t in self._todo_manager.list_todos()
                            if t.get("status") in ("pending", "in_progress")
                        )
                        logger.warning(
                            "LLM produced %d consecutive empty turns with %d "
                            "remaining todos — pausing for user input",
                            self._empty_tool_turns, pending_count,
                        )
                        yield StreamEvent.text_delta(
                            f"\n\n*Pausing: {self._empty_tool_turns} empty turns with {pending_count} pending todos. "
                            "Type 'continue' to proceed or 'stop' to end.*\n\n"
                        )
                        return
                    open_count = sum(
                        1 for t in self._todo_manager.list_todos()
                        if t.get("status") in ("pending", "in_progress")
                    )
                    logger.info(
                        "LLM stopped calling tools but %d pending todos remain — "
                        "injecting FORCE_CONTINUE nudge (empty_tool_turns=%d)",
                        open_count, self._empty_tool_turns,
                    )
                    next_todo = None
                    for t in self._todo_manager.list_todos():
                        if t.get("status") == "pending":
                            next_todo = t
                            break
                    if next_todo:
                        lines = [
                            "# Continue working",
                            "",
                            f"The next pending todo is `{next_todo['id']}`: "
                            f"{next_todo.get('subject', '')}",
                            "",
                            "Execute it now. Do NOT summarise or stop.",
                        ]
                        self._inject_nudge(lines)
                    else:
                        lines = [
                            "<!-- FORCE_CONTINUE -->",
                            "## CRITICAL: Unfinished todos detected",
                            "You stopped without completing all planned todos.",
                            "You MUST continue working:",
                        "1. Mark any finished work as complete.",
                        "2. Then Spawn or execute the next pending todo.",
                        "3. Repeat until ALL todos are Done.",
                            "Do NOT stop. Do NOT summarise. Keep executing.",
                        ]
                        self._inject_nudge(lines)
                    continue
                # All todos completed — end session immediately
                all_todos = self._todo_manager.list_todos()
                if all_todos and all(t.get("status") == "completed" for t in all_todos):
                    logger.info("All %d todo(s) completed, ending session", len(all_todos))
                    break
                if self._empty_tool_turns >= max_empty_turns:
                    logger.warning(
                        "LLM produced %d consecutive empty turns with no pending todos — breaking loop",
                        self._empty_tool_turns,
                    )
                    break
                # No pending todos and no tool calls: work appears done.
                if not all_todos:
                    break

            # Emit ToolEvents (Clawd-Code pattern) and StreamEvents for TUI
            for tu in tool_uses:
                self._notify_event(ToolEvent(
                    kind="tool_use",
                    tool_name=tu["name"],
                    tool_input=tu["input"],
                    tool_use_id=tu["id"],
                ))
                yield StreamEvent.tool_call_start(tu["name"], tu["id"])
            for tu in tool_uses:
                yield StreamEvent.tool_call_complete(tu["id"], tu["name"], tu["input"])

            for tu in tool_uses:
                if self._cancelled:
                    self._cleanup_injected_messages()
                    yield StreamEvent.text_delta("\n\n*Turn cancelled*\n\n")
                    return
                logger.info(f"Executing tool: {tu['name']} (id={tu['id']})")

                # ── Plan mode guard ──
                # In plan mode (edit=DENY && bash=DENY), reject any tool not
                # marked as read-only UNLESS the permission system explicitly
                # allows it (e.g. TodoCreate/TodoUpdate, which are the plan
                # artifact and are ALLOWed for the plan agent). Returns a
                # clear message telling the LLM to switch to Build mode
                # instead of silently failing.
                if self._is_plan_mode():
                    spec = self._tool_registry.get(tu["name"])
                    if spec and not spec.spec().is_read_only:
                        denied = self._check_tool_permission(tu["name"], tu["input"])
                        if denied is not None:
                            self._plan_denial_count += 1
                            self._register_tool_denial(tu["name"])
                            result = {
                                "tool_use_id": tu["id"],
                                "is_error": True,
                                "category": "mode",
                                "content": json.dumps({
                                    "success": False,
                                    "error": (
                                        f"Tool '{tu['name']}' is not available in Plan mode. "
                                        "Plan mode is read-only: you may use Read/Glob/Grep/WebFetch/"
                                        "WebSearch for analysis, AskUser for questions, and "
                                        "TodoCreate/TodoUpdate to build the task list. "
                                        "Writing files, running shell commands, or any "
                                        "other mutation requires switching to Build mode."
                                    ),
                                }),
                            }
                            if self._plan_denial_count >= 3:
                                self.context.insert_system_before_non_system(
                                    "<!-- PLAN_MODE_DENIED -->\n"
                                    "## CRITICAL: Repeated write attempts in Plan mode\n"
                                    "You have repeatedly attempted write operations in Plan mode.\n"
                                    "This will NEVER succeed. Stop trying and use only read/planning tools.\n"
                                    "To execute changes, the user must switch to Build mode first."
                                )
                            else:
                                self.context.insert_system_before_non_system(
                                    "<!-- PLAN_MODE_DENIED -->\n"
                                    f"You attempted to use '{tu['name']}' which requires write access.\n"
                                    "Plan mode is read-only. Do NOT call write-capable tools again.\n"
                                    "Switch to Build mode if you need to execute changes."
                                )
                            # Emit tool result event before continuing to next tool
                            result_str = str(result.get("content", ""))
                            is_error = result.get("is_error", False)
                            _cat = result.get("category", "unknown")
                            from onecode.models.messages import ToolCategory as MsgToolCategory
                            try:
                                result_cat = MsgToolCategory(_cat)
                            except ValueError:
                                result_cat = MsgToolCategory.UNKNOWN
                            self._notify_event(ToolEvent(
                                kind="tool_result",
                                tool_name=tu["name"],
                                tool_use_id=tu["id"],
                                tool_output=result_str,
                                is_error=is_error,
                            ))
                            yield StreamEvent.tool_result(
                                call_id=tu["id"],
                                content=result_str,
                                is_error=is_error,
                                category=result_cat,
                            )
                            if is_anthropic:
                                self.context.add_tool_result(tu["id"], result_str, is_error)
                            else:
                                self.context.add_message(
                                    "tool",
                                    [{"type": "tool_result", "tool_use_id": tu["id"],
                                      "content": result_str, "is_error": is_error}],
                                    name=tu["id"],
                                )
                            continue

                # Spawn tool: forward subagent text deltas to the TUI as
                # subagent_chunk events so the SubAgent widget actually has
                # content to render.  The Spawn tool's spec is (agent_type,
                # prompt); we read them from the tool input.
                if tu["name"] == "Spawn":
                    # Permission check
                    denied = self._check_tool_permission("Spawn", tu["input"])
                    if denied:
                        result = {
                            "tool_use_id": tu["id"],
                            "is_error": True,
                            "category": "task",
                            "content": denied,
                        }
                    else:
                        subagent_type = tu["input"].get("agent_type", "general")
                        subagent_prompt = tu["input"].get("prompt", "")
                        _sp_id = tu["id"]
                        _sp_bytes_fwd = 0
                        _sp_chunk_count = 0
                        logger.debug(
                            "[SPAWN-PARENT %s] start subagent_type=%s prompt_len=%d "
                            "tool_id=%s cancelled=%s",
                            _sp_id, subagent_type, len(subagent_prompt),
                            _sp_id, self._cancelled,
                        )
                        is_failed = False
                        error_msg = ""
                        yield StreamEvent.subagent_start(subagent_type, tu["id"], subagent_prompt)
                        accumulated: list[str] = []
                        try:
                            async for sub_event, sub_text in self._spawn_subagent_async_streaming(
                                subagent_type, subagent_prompt, subagent_id=tu["id"]
                            ):
                                _sp_chunk_count += 1
                                if self._cancelled:
                                    logger.debug(
                                        "[SPAWN-PARENT %s] cancelled mid-iter "
                                        "chunk=%d → break", _sp_id, _sp_chunk_count)
                                    break
                                if sub_event.type == StreamEventType.SUBAGENT_END:
                                    if hasattr(sub_event, "subagent_status") and sub_event.subagent_status == "failed":
                                        is_failed = True
                                        error_msg = sub_event.subagent_error or ""
                                    logger.debug(
                                        "[SPAWN-PARENT %s] recv SUBAGENT_END "
                                        "status=%s → continue",
                                        _sp_id, getattr(sub_event, "subagent_status", "?"),
                                    )
                                    continue  # 修复 Bug 1: 不 append final combined text（避免文本重复）
                                if sub_event.type == StreamEventType.SUBAGENT_THINKING:
                                    yield StreamEvent.subagent_thinking(tu["id"], sub_text)
                                    continue
                                # Structured subagent tool events: forward as-is
                                # (they already carry subagent_id=tu["id"]) so the
                                # ACP emits tool_call/tool_call_update sessionUpdates
                                # tagged with subagentId and the TUI renders real
                                # ToolCall cards inside the SubAgent widget.
                                if sub_event.type in (
                                    StreamEventType.SUBAGENT_TOOL_CALL,
                                    StreamEventType.SUBAGENT_TOOL_RESULT,
                                ):
                                    yield sub_event
                                    continue
                                if not sub_text:
                                    continue
                                accumulated.append(sub_text)
                                _sp_bytes_fwd += len(sub_text)
                                if _sp_chunk_count <= 5 or _sp_chunk_count % 50 == 0:
                                    logger.debug(
                                        "[SPAWN-PARENT %s] fwd chunk#%d bytes=%d "
                                        "total=%d",
                                        _sp_id, _sp_chunk_count, len(sub_text),
                                        _sp_bytes_fwd,
                                    )
                                yield StreamEvent.subagent_chunk(tu["id"], sub_text)
                        except asyncio.CancelledError:
                            logger.debug(
                                "[SPAWN-PARENT %s] CancelledError → subagent_end "
                                "failed=cancelled + re-raise", _sp_id)
                            yield StreamEvent.subagent_end(
                                tu["id"],
                                agent_type=subagent_type,
                                status="failed",
                                error="cancelled",
                            )
                            raise
                        logger.debug(
                            "[SPAWN-PARENT %s] subagent done fwd_chunks=%d "
                            "bytes_fwd=%d is_failed=%s err=%r → yield subagent_end",
                            _sp_id, _sp_chunk_count, _sp_bytes_fwd, is_failed,
                            error_msg[:80],
                        )
                        yield StreamEvent.subagent_end(
                            tu["id"],
                            agent_type=subagent_type,
                            status="failed" if is_failed else "completed",
                            error=error_msg,
                        )
                        raw_output = "".join(accumulated)
                        logger.debug(
                            "[SPAWN-PARENT %s] formatting result raw_len=%d "
                            "is_failed=%s", _sp_id, len(raw_output), is_failed,
                        )
                        formatted = self._format_subagent_output(
                            subagent_type, subagent_prompt, raw_output
                        ) if not is_failed else (
                            f"SUMMARY:\nSub-agent failed with error: {error_msg}\n\n"
                            "CHANGES:\nNone.\n\nEVIDENCE:\nNone.\n\nRISKS:\nNone.\n\n"
                            f"BLOCKERS:\n{error_msg}"
                        )
                        result = {
                            "tool_use_id": tu["id"],
                            "is_error": is_failed,  # 修复 Bug 2: 子智能体失败时 is_error=True
                            "category": "task",
                            "content": formatted,
                            "raw_content": raw_output,
                        }
                        # Auto-advance todo after subagent completes
                        if not is_failed:
                            self._auto_advance_after_spawn(subagent_prompt)
                elif (self._plan_gate_mode != "off"
                      and not self._has_pending_todos()
                      and tu["name"] in _EXECUTION_TOOLS):
                    if self._plan_gate_mode == "hard":
                        result = {
                            "tool_use_id": tu["id"],
                            "is_error": True,
                            "category": "todo",
                            "content": json.dumps({
                                "success": False,
                                "error": (
                                    "Plan required. You are in plan mode (ReAct: Thought → Action → Observation). "
                                    "Before using execution tools, output a step-by-step plan as "
                                    "Markdown for user review, and only then proceed to execute."
                                ),
                            }),
                        }
                    else:
                        # Soft gate: execute but inject a routing reminder for next turn
                        self.context.insert_system_before_non_system(
                            "<!-- PLAN_REMINDER -->\n"
                            "## Routing Decision\n"
                            "Output a step-by-step plan as Markdown before executing.\n"
                            "Then route EXECUTION by complexity:\n\n"
                            "**Simple / single-step** → execute directly with "
                            "`Read`/`Edit`/`Bash`.\n\n"
                            "**Complex / multi-step / needs isolated context** → "
                            "`Spawn(agent_type, prompt)` delegates to a focused subagent.\n"
                        )
                        result = await self._execute_tool(tu)
                        if self._just_exited_plan_mode:
                            spec = self._tool_registry.get(tu["name"])
                            if spec and not spec.spec().is_read_only:
                                self._just_exited_plan_mode = False
                else:
                    result = await self._execute_tool(tu)
                    # Reset _just_exited_plan_mode once real work begins
                    if self._just_exited_plan_mode:
                        spec = self._tool_registry.get(tu["name"])
                        if spec and not spec.spec().is_read_only:
                            self._just_exited_plan_mode = False
                    # Routing: track direct execution tool use → nudge routing decision
                    if tu["name"] in _EXECUTION_TOOLS:
                        self._direct_execution_count += 1
                        if self._direct_execution_count >= 2:
                            self.context.insert_system_before_non_system(
                                "<!-- ROUTING_REMINDER -->\n"
                                "You've used direct execution tools repeatedly. Pause and decide:\n"
                                "- Is this work part of a plan? If not, output a plan as Markdown first.\n"
                                "- If the task is a single-step trivial change → continue directly.\n"
                                "- If this work involves >1 tool call, multiple files, or "
                                "research → STOP direct execution and delegate via "
                                "`Spawn(agent_type=\"general\", prompt=\"...\")` instead."
                            )
                result_str = str(result.get("content", ""))
                is_error = result.get("is_error", False)
                category = result.get("category", "unknown")
                # For Spawn tools, use raw subagent output for TUI display
                # (no SUMMARY/CHANGES/… structured wrapper)
                tui_content = str(result.get("raw_content", result_str))

                # Handle SendMessage — user-visible only, skip from LLM context
                if tu["name"] == "SendMessage":
                    try:
                        parsed = json.loads(result_str) if result_str else {}
                        msg = parsed.get("message", "") if isinstance(parsed, dict) else ""
                        if msg:
                            self._last_user_msg = msg
                            yield StreamEvent.text_delta(f"\n💬 {msg}\n")
                    except (json.JSONDecodeError, ValueError):
                        pass
                    self._notify_event(ToolEvent(
                        kind="tool_result",
                        tool_name="SendMessage",
                        tool_use_id=tu["id"],
                        tool_output={"message": self._last_user_msg},
                    ))
                    continue

                # Handle AskUser — trigger user interaction dialog, don't add to LLM context yet
                if tu["name"] == "AskUser":
                    parsed = json.loads(result_str) if result_str else {}
                    question = parsed.get("question", "") if isinstance(parsed, dict) else ""
                    context = parsed.get("context", "") if isinstance(parsed, dict) else ""
                    options = parsed.get("options", []) if isinstance(parsed, dict) else []
                    questions = parsed.get("questions", []) if isinstance(parsed, dict) else []
                    plan_submit = bool(parsed.get("plan_submit", False)) if isinstance(parsed, dict) else False

                    # Plan submission: persist the plan document so it survives
                    # compaction and can be re-read by the execution agent.
                    plan_path = None
                    if plan_submit:
                        plan_path = self._save_plan_document(
                            context or question or result_str
                        )
                        if plan_path:
                            self._approved_plan_path = plan_path
                            suffix = f"\n\nPlan saved to: {plan_path}"
                            if context:
                                context = f"{context}{suffix}"
                            elif question:
                                question = f"{question}{suffix}"

                    # Check for auto-default on single question + single option
                    if not questions and not plan_submit and len(options) == 1 and options[0].get("default"):
                        default_val = options[0]["value"]
                        self._pending_approval = None
                        yield StreamEvent.tool_result(
                            call_id=tu["id"],
                            content=json.dumps({"answer": default_val}),
                        )
                        continue

                    # Auto-default for multi-question: skip questions that have
                    # a single option with default=true
                    if questions and not plan_submit:
                        auto_answers = {}
                        remaining = []
                        for i, q in enumerate(questions):
                            qopts = q.get("options", [])
                            if len(qopts) == 1 and qopts[0].get("default"):
                                auto_answers[str(i)] = qopts[0]["value"]
                            else:
                                remaining.append(q)
                        if not remaining:
                            self._pending_approval = None
                            yield StreamEvent.tool_result(
                                call_id=tu["id"],
                                content=json.dumps({"answers": auto_answers}),
                            )
                            continue
                        questions = remaining

                    has_questions = bool(questions)
                    self._pending_approval = {
                        "tool_call": tu,
                        "category": category,
                        "ask_user": True,
                        "plan_submit": plan_submit,
                        "plan_path": plan_path,
                    }
                    if has_questions:
                        yield StreamEvent.ask_user(
                            call_id=tu["id"],
                            action="AskUser",
                            question="",  # not used when questions is present
                            context=result_str,
                            options=[],
                            questions=questions,
                            action_type="ask_user",
                            plan_submit=plan_submit,
                        )
                    else:
                        yield StreamEvent.ask_user(
                            call_id=tu["id"],
                            action="AskUser",
                            question=question,
                            context=result_str,
                            options=options,
                            action_type="ask_user",
                            plan_submit=plan_submit,
                        )
                    continue

                # Detect ASK permission denial
                requires_approval = False
                try:
                    parsed = json.loads(result_str) if result_str else {}
                    requires_approval = isinstance(parsed, dict) and parsed.get("requires_approval", False)
                except (json.JSONDecodeError, ValueError):
                    pass

                if requires_approval:
                    checkpoint_id = ""
                    tool_input = tu.get("input", {})
                    affected_files = self._get_affected_files(tu["name"], tool_input)
                    should_ckpt, reason = self._checkpoint_manager.should_checkpoint(
                        tu["name"], tool_input, affected_files
                    )
                    if should_ckpt:
                        checkpoint_id = self._checkpoint_manager.create(
                            agent=self.current_agent.name,
                            reason=reason,
                            files=affected_files,
                            tool_call_id=tu["id"],
                            description=f"{tu['name']} requires approval",
                        )
                    self._pending_approval = {
                        "tool_call": tu,
                        "category": category,
                        "checkpoint_id": checkpoint_id,
                    }
                    self._notify_event(ToolEvent(
                        kind="tool_result",
                        tool_name=tu["name"],
                        tool_use_id=tu["id"],
                        is_error=True,
                        error="Requires approval",
                    ))
                    yield StreamEvent.ask_user(
                        call_id=tu["id"],
                        action=tu["name"],
                        question=f"Approve {tu['name']} operation?",
                        context=result_str,
                        action_type=tu["name"].lower(),
                        path=tu["input"].get("path", ""),
                        command=tu["input"].get("command", "")[:200],
                        checkpoint_id=checkpoint_id,
                    )
                    # Generator resumes here after approval. The approved tool
                    # may have mutated todos (e.g. TodoUpdate via resolve_approval),
                    # flushing _plan_dirty so the TUI stays in sync.
                    if self._plan_dirty:
                        for event in self._emit_plan_update():
                            yield event
                        self._plan_dirty = False
                else:
                    from onecode.models.messages import ToolCategory as MsgToolCategory
                    try:
                        result_cat = MsgToolCategory(category)
                    except ValueError:
                        result_cat = MsgToolCategory.UNKNOWN
                    self._last_tool_results[tu["id"]] = result_str
                    self._notify_event(ToolEvent(
                        kind="tool_result",
                        tool_name=tu["name"],
                        tool_output=result_str,
                        tool_use_id=tu["id"],
                        is_error=is_error,
                    ))
                    yield StreamEvent.tool_result(
                        call_id=tu["id"],
                        content=tui_content,
                        is_error=is_error,
                        category=result_cat,
                    )
                    # Add structured tool_result to LLM context
                    if is_anthropic:
                        self.context.add_tool_result(tu["id"], result_str, is_error)
                    else:
                        self.context.add_message(
                            "tool",
                            [{"type": "tool_result", "tool_use_id": tu["id"], "content": result_str, "is_error": is_error}],
                            name=tu["id"],
                        )
                    # Mid-turn compaction: tool results can add significant
                    # context; compress immediately if we're over threshold.
                    self.context.set_model(self.app.current_model)
                    if self.context.should_compact():
                        try:
                            level = self.context.compact()
                            if level not in ("none",):
                                logger.info(
                                    "Mid-turn compaction at turn %d after tool %s: %s",
                                    turn + 1, tu["name"], level,
                                )
                        except Exception as e:
                            logger.error(
                                "Mid-turn compaction failed at turn %d after tool %s: %s",
                                turn + 1, tu["name"], e,
                            )
                    # Emit plan update when tasks/todos changed.  Any
                    # mutating path through TodoManager flips
                    # ``_plan_dirty`` via the ``on_change`` callback, so we
                    # do not need to enumerate tool names here.
                    if self._plan_dirty:
                        for event in self._emit_plan_update():
                            yield event
                        self._plan_dirty = False

            # Tools were called this turn — reset the empty-turn counter
            self._empty_tool_turns = 0

            # L2: Run verification loop if applicable
            verification_retry = False
            if self._verification_loop is not None:
                from onecode.agent.turn_record import TurnRecord
                for tu in tool_uses:
                    if self._verification_loop.should_verify(tu["name"]):
                        result_str = self._last_tool_results.get(tu["id"], "")
                        turn_record = TurnRecord(
                            turn_number=turn,
                            thought=clean_text,
                            tool_name=tu["name"],
                            tool_input=tu.get("input"),
                            tool_output=result_str,
                        )
                        agg_result = await self._verification_loop.run_gates(turn_record)
                        turn_record.add_verification(agg_result.to_dict())
                        evt_type = StreamEventType.VERIFICATION_PASSED if agg_result.passed else StreamEventType.VERIFICATION_FAILED
                        yield StreamEvent(
                            type=evt_type,
                            text="passed" if agg_result.passed else f"failed: {', '.join(agg_result.failed_gates)}",
                            verification_passed=agg_result.passed,
                            verification_failed_gates=list(agg_result.failed_gates),
                        )
                        if not agg_result.passed:
                            self._verification_fail_count += 1
                            logger.warning(
                                "Verification failed (attempt %d/3): %s",
                                self._verification_fail_count, agg_result.failed_gates,
                            )
                            self._turn_events.append({
                                "turn": turn + 1,
                                "kind": "verify_fail",
                                "gates": list(agg_result.failed_gates),
                                "attempt": self._verification_fail_count,
                            })
                            if self._verification_fail_count <= 3:
                                lines = [
                                    "<!-- VERIFY_FAIL -->",
                                    f"## Verification failed: {', '.join(agg_result.failed_gates)}",
                                    f"Attempt {self._verification_fail_count}/3 — fix the issues above and retry.",
                                    "Do NOT stop. Fix the code and re-run verification tools.",
                                ]
                                self.context.insert_system_before_non_system("\n".join(lines))
                                if self._event_bridge is not None:
                                    self._event_bridge.on_verification_failed(agg_result)
                                verification_retry = True
                                break
                            else:
                                logger.warning(
                                    "Verification failed after %d retries, stopping execution",
                                    self._verification_fail_count,
                                )
                                self._turn_events.append({
                                    "turn": turn + 1,
                                    "kind": "verify_fail_exhausted",
                                    "gates": list(agg_result.failed_gates),
                                })
                                yield StreamEvent.text_delta(
                                    f"\n⚠️ Verification failed after 3 retries: {', '.join(agg_result.failed_gates)}\n"
                                )
                                if self._event_bridge is not None:
                                    self._event_bridge.on_verification_failed(agg_result)
                                self._cleanup_injected_messages()
                                return
                        else:
                            self._verification_fail_count = 0
                            if self._event_bridge is not None:
                                self._event_bridge.on_verification_passed()
            if verification_retry:
                continue

            if self._cancelled:
                self._cleanup_injected_messages()
                yield StreamEvent.text_delta("\n\n*Turn cancelled*\n\n")
                return

        self._cleanup_injected_messages()
        usage_summary = ", ".join(
            f"turn {i+1}: {u.get('total_tokens', '?')} tokens"
            for i, u in enumerate(self._turn_usages) if u
        )
        logger.info(f"Chat stream complete after {self.iterations} round(s). Usage: [{usage_summary}]")

        # ── Session end: clear todos if all completed ──
        # When every todo has reached "completed" status, wipe the todo list
        # so the next session starts clean instead of inheriting a stale plan.
        try:
            final_todos = self._todo_manager.list_todos()
            if final_todos and all(t.get("status") == "completed" for t in final_todos):
                logger.info(
                    "Session end: all %d todo(s) completed, clearing todo list",
                    len(final_todos),
                )
                self._todo_manager.clear_todos()
        except Exception as e:
            logger.warning("Session-end todo cleanup failed: %s", e, exc_info=True)

    def has_pending_approval(self) -> bool:
        """Check if there's a pending approval request from ASK permission."""
        return self._pending_approval is not None

    async def resolve_approval(self, approved: bool, answer: str = "") -> dict | None:
        """Execute the pending action if approved, or return denial.

        For AskUser, ``answer`` is the user's free-text response.

        Returns the tool result dict, or None if no pending approval.
        """
        from onecode.agent.agents.types import AgentPermission
        if not self._pending_approval:
            return None
        
        tc = self._pending_approval["tool_call"]
        is_ask_user = self._pending_approval.get("ask_user", False)
        plan_submit = self._pending_approval.get("plan_submit", False)
        plan_path = self._pending_approval.get("plan_path")
        checkpoint_id = self._pending_approval.get("checkpoint_id", "")
        self._pending_approval = None

        # Handle AskUser — return user's answer as tool result
        if is_ask_user:
            if not approved:
                return {
                    "tool_use_id": tc["id"],
                    "content": json.dumps({"answer": "", "error": "User cancelled"}),
                    "is_error": True,
                    "category": tc.get("category", "unknown"),
                }
            # Plan approved → hand off to the execution agent (keeps todos).
            if plan_submit:
                self._plan_handoff(plan_path)
            # answer is a JSON string when multi-question, plain text otherwise
            try:
                parsed = json.loads(answer)
                is_structured = isinstance(parsed, dict) or isinstance(parsed, list)
            except (json.JSONDecodeError, TypeError):
                is_structured = False
            if is_structured:
                return {
                    "tool_use_id": tc["id"],
                    "content": json.dumps({"answers": parsed}),
                    "is_error": False,
                    "category": tc.get("category", "unknown"),
                }
            return {
                "tool_use_id": tc["id"],
                "content": json.dumps({"answer": answer}),
                "is_error": False,
                "category": tc.get("category", "unknown"),
            }
        
        if not approved:
            return {
                "tool_use_id": tc["id"],
                "content": json.dumps({"success": False, "error": "User denied the operation"}),
                "is_error": True,
                "category": tc.get("category", "unknown"),
            }

        if answer == "__rollback__" and checkpoint_id:
            self._checkpoint_manager.restore(checkpoint_id)
            return {
                "tool_use_id": tc["id"],
                "content": json.dumps({"success": False, "error": "Rolled back to checkpoint"}),
                "is_error": True,
                "category": tc.get("category", "unknown"),
            }
        
        perm_key = self._TOOL_NAME_TO_PERM_KEY.get(tc["name"])
        if perm_key is None:
            return await self._execute_tool(tc)

        attr_name = f"permission_{perm_key}"
        saved = getattr(self.current_agent, attr_name)
        try:
            setattr(self.current_agent, attr_name, AgentPermission.ALLOW)
            return await self._execute_tool(tc)
        finally:
            setattr(self.current_agent, attr_name, saved)

    async def rollback_to_checkpoint(self, checkpoint_id: str) -> bool:
        """Restore files to a previous checkpoint state."""
        return self._checkpoint_manager.restore(checkpoint_id)

    def get_checkpoint_diff(self, checkpoint_id: str, file_path: str) -> str:
        """Get diff between checkpoint and current state for a file."""
        return self._checkpoint_manager.get_diff(checkpoint_id, file_path)

    def list_checkpoints(self, limit: int = 10) -> list[dict]:
        """List recent checkpoints."""
        return self._checkpoint_manager.list(limit=limit)

    def _reset_react_state(self) -> None:
        """Reset ReAct loop state for a fresh cycle."""
        self._react_phase = "thought"
        self._direct_execution_count = 0
        self._empty_tool_turns = 0
        self._plan_denial_count = 0
        self._verification_fail_count = 0
        self._last_tool_results.clear()
        self._cleanup_injected_messages()
        self.context.remove_system_by_marker("<!-- PLAN_MODE_DENIED -->")
        for name in list(self._tool_denial_count):
            self.context.remove_system_by_marker(f"<!-- TOOL_DENIED_{name} -->")
        self._tool_denial_count.clear()
        self.context.remove_system_by_marker("<!-- VERIFY_FAIL -->")
        self._last_emitted_plan = ()
        self.context.remove_system_by_marker("<!-- REACT_PHASE -->")
        self.context.remove_system_by_marker("<!-- ROUTING_REMINDER -->")
        self.context.remove_system_by_marker("<!-- PENDING_TODOS -->")

    def reset(self):
        self.context.reset()
        self.iterations = 0
        self.total_tokens = 0
        self._turn_usages = []
        self._turn_events = []
        self._skills_loaded = False
        self._project_context_loaded = False
        self._ctx_crisis = False
        self._skill_loader.invalidate_cache()
        self._reset_react_state()

    def status(self) -> str:
        return (
            f"Agent: {self.current_agent.name}\n"
            f"Iterations: {self.iterations}\n"
            f"Total tokens: {self.total_tokens}\n"
            f"Context: {self.context.info()}"
        )

    def read_file(self, path: str, offset: int = 0, limit: int = 0) -> str:
        if self.current_agent.permission_read == AgentPermission.DENY:
            return "Read denied"
        return self.file_ops.read(path, offset, limit)

    def write_file(self, path: str, content: str) -> dict:
        if self.current_agent.permission_edit == AgentPermission.DENY:
            return {"success": False, "error": "Edit denied"}
        if self.current_agent.permission_edit == AgentPermission.ASK:
            return {"success": False, "error": "Edit requires approval", "requires_approval": True}
        return self.file_ops.write(path, content)

    def edit_file(self, path: str, old: str, new: str) -> dict:
        if self.current_agent.permission_edit == AgentPermission.DENY:
            return {"success": False, "error": "Edit denied"}
        if self.current_agent.permission_edit == AgentPermission.ASK:
            return {"success": False, "error": "Edit requires approval", "requires_approval": True}
        return self.file_ops.edit(path, old, new)

    def glob_files(self, pattern: str) -> list[str]:
        return self.file_ops.glob(pattern)

    def grep_files(self, pattern: str, include: str = None) -> list[str]:
        return self.file_ops.grep(pattern, include)

    def list_dir(self, path: str = ".") -> list[dict]:
        return self.file_ops.list(path)

    def exec_shell(self, cmd: str, timeout: int = 60) -> dict:
        if self.current_agent.permission_bash == AgentPermission.DENY:
            return {"success": False, "error": "Bash denied"}
        if self.current_agent.permission_bash == AgentPermission.ASK:
            return {"success": False, "error": "Bash requires approval", "requires_approval": True}
        return self.shell.exec(cmd, timeout=timeout)

    def web_fetch(self, url: str, prompt: str = None) -> str:
        if self.current_agent.permission_webfetch == AgentPermission.DENY:
            return "WebFetch denied"
        from onecode.agent.tools.web_tools import webfetch
        return webfetch(url, prompt)

    def web_search(self, query: str, num_results: int = 5) -> str:
        if self.current_agent.permission_websearch == AgentPermission.DENY:
            return "WebSearch denied"
        from onecode.agent.tools.web_tools import websearch
        return websearch(query, num_results)

    async def _spawn_subagent_async(self, agent_type: str, prompt: str) -> str:
        """Spawn a sub-agent with streaming-like output.

        Uses chat_stream to get structured output that the ChatPanel
        can parse for professional rendering.
        """
        parts: list[str] = []
        async for _event, text in self._spawn_subagent_async_streaming(agent_type, prompt):
            parts.append(text)
        result = "".join(parts)
        return self._format_subagent_output(agent_type, prompt, result)

    async def _spawn_subagent_async_streaming(
        self, agent_type: str, prompt: str, subagent_id: str = ""
    ) -> AsyncIterator[tuple[StreamEvent, str]]:
        """Streaming variant of :meth:`_spawn_subagent_async`.

        Yields ``(event, text)`` pairs so the caller (typically the Task-tool
        path in :meth:`chat_stream`) can forward each text delta as a
        ``subagent_chunk`` notification on the ACP wire.

        Inherits project context and skills from the parent
        engine so the subagent does not start from a blank slate.
        """
        # Depth check: limit from config (default 1 = leaf nodes only).
        depth_limit = getattr(self.app.config.agent, 'max_subagent_depth', _MAX_SUBAGENT_DEPTH)
        subagent_timeout = getattr(self.app.config.agent, 'max_subagent_timeout', _SUBAGENT_TIMEOUT)
        if self._subagent_depth >= depth_limit:
            err = f"Subagent cannot spawn nested subagents (max depth={depth_limit})"
            yield (StreamEvent.subagent_end(
                "", agent_type=agent_type, status="failed", error=err,
            ), err)
            return

        if self.current_agent.name == "plan" and agent_type not in ("explore", "scout"):
            err = f"PlanAgent can only spawn read-only agents (explore, scout), not '{agent_type}'"
            yield (StreamEvent.subagent_end(
                "", agent_type=agent_type, status="failed", error=err,
            ), err)
            return

        sub_engine = AgentEngine(self.app, project_dir=self._project_dir, perm_store=self._perm_store)

        sub_engine._subagent_depth = self._subagent_depth + 1

        # Inherit parent context: project info (but NOT full skill content,
        # which contains Master Orchestrator instructions that conflict with
        # the subagent role). The subagent's own _load_skills() will load
        # only non-conflicting reference info via its own SkillLoader.
        sub_engine._project_context_loaded = self._project_context_loaded
        sub_engine._project_config = dict(self._project_config)
        sub_engine._skills_loaded = False

        # Inherit the parent's already-built codebase engine so the subagent
        # does NOT re-run the full project index (CodebaseIndexer.index()
        # is a synchronous chunk loop that would otherwise block the event
        # loop for the duration of indexing and freeze streaming/cancel).
        # Sharing the instance also avoids duplicate SQLite writes.
        sub_engine._codebase_engine = self._codebase_engine
        logger.debug(
            "[SA-STREAM %s] inheriting codebase_engine from parent: %s",
            agent_type, "shared" if self._codebase_engine is not None else "none",
        )

        # CRITICAL: disable codebase auto-retrieval + memory recall inside
        # the subagent.  Production logs prove that every Spawn hung here:
        # the subagent's ``chat_stream`` re-ran ``CodebaseIndexer.index()``
        # (a 2.3–2.6s synchronous loop, no await yield points) and then
        # ``CodebaseRetriever._retrieve_embedding()`` issued one ``httpx``
        # POST per chunk (30s timeout each, no effective cap), so a 148-
        # chunk project could block the event loop for ~minutes — during
        # which ``on_text_chunk`` never fires (no stream output) and
        # ``CancelledError`` injected by ``prompt_task.cancel()`` cannot
        # propagate (cannot be stopped).  A subagent executes a specific
        # prompt handed down by the parent; it does not need project-level
        # codebase seeding or memory recall.
        sub_engine._disable_retrieval = True
        logger.debug(
            "[SA-STREAM %s] set _disable_retrieval=True (subagent skips "
            "codebase auto-retrieval + memory recall)", agent_type,
        )

        # Do NOT propagate parent TUI-facing callbacks to the sub_engine.
        # - on_tool_call_delta: would fire the ACP's _on_tool_call_delta for
        #   the subagent's inner tools (Read/Bash/...), leaking their NAMES
        #   into the MAIN conversation as orphaned in_progress cards while
        #   the RESULT only reaches the SubAgent widget via the stream path
        #   below (tool_call_start/tool_result -> text_delta -> subagent_chunk).
        # - on_thinking: would append subagent thinking into the PARENT's
        #   _pending_thinking_blocks, polluting the parent's persisted session.
        # The subagent's tool calls/thinking are already relayed to the
        # SubAgent widget via SUBAGENT_CHUNK / SUBAGENT_THINKING (see the
        # consumer loop below). on_event is left propagated: the ACP does
        # not wire it, so it is None on the parent and a no-op here.
        if self.on_event is not None:
            sub_engine.on_event = self.on_event

        # Apply the requested agent_type's config (role description,
        # response-style / <thinking> tags, tool allow/deny list, REACT_CYCLE)
        # as the AGENT_CONFIG system section.
        sub_engine.set_agent(agent_type)

        # Track child so parent cancellation cascades
        self._child_engines.append(sub_engine)

        # ── Real-time streaming via asyncio.Queue ──
        # on_text_chunk puts provider tokens into the queue as they arrive,
        # and a background task puts chat_stream events into the same queue.
        # The main loop reads from the queue and yields (event, text) pairs,
        # giving the TUI live subagent output instead of "等待输出".
        _queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue(maxsize=1000)
        _sa_log_prefix = f"[SA-STREAM {agent_type} depth={self._subagent_depth + 1}]"
        _sa_total_bytes = 0
        _sa_chunk_count = 0
        _sa_text_count = 0
        _sa_first_byte_logged = False

        def _on_subagent_text(text: str) -> None:
            nonlocal _sa_total_bytes, _sa_text_count, _sa_first_byte_logged
            try:
                _queue.put_nowait(("text", text))
            except asyncio.QueueFull:
                logger.warning(
                    "%s on_text_chunk queue full (maxsize=1000) — dropping text chunk "
                    "of %d bytes. Consider increasing max_subagent_timeout to allow "
                    "faster processing.",
                    _sa_log_prefix, len(text),
                )
                return
            _sa_text_count += 1
            _sa_total_bytes += len(text)
            if not _sa_first_byte_logged:
                _sa_first_byte_logged = True
                logger.debug(
                    "%s on_text_chunk FIRST token bytes=%d (text_count so far=%d)",
                    _sa_log_prefix, len(text), _sa_text_count,
                )
            if _sa_text_count % 20 == 0:
                logger.debug(
                    "%s on_text_chunk progress text_calls=%d total_bytes=%d "
                    "queued=%d",
                    _sa_log_prefix, _sa_text_count, _sa_total_bytes,
                    _queue.qsize(),
                )

        sub_engine.on_text_chunk = _on_subagent_text
        logger.debug("%s wiring on_text_chunk → queue (sub_engine id=%x)",
                     _sa_log_prefix, id(sub_engine))

        async def _run_chat_stream() -> None:
            logger.debug("%s _run_chat_stream task started", _sa_log_prefix)
            try:
                async for chunk in sub_engine.chat_stream(prompt):
                    await _queue.put(("event", chunk))
            except asyncio.CancelledError:
                logger.debug("%s _run_chat_stream CancelledError → queue(cancelled)",
                             _sa_log_prefix)
                await _queue.put(("cancelled", None))
            except Exception as e:
                logger.exception("%s _run_chat_stream exception: %s", _sa_log_prefix, e)
                await _queue.put(("error", e))
            finally:
                logger.debug(
                    "%s _run_chat_stream finally → queue(done) text=%d bytes=%d "
                    "chunk_events=%d",
                    _sa_log_prefix, _sa_text_count, _sa_total_bytes, _sa_chunk_count,
                )
                await _queue.put(("done", None))

        _stream_task = asyncio.create_task(_run_chat_stream())
        logger.debug("%s created _stream_task id=%x cancelled_flag=%s",
                     _sa_log_prefix, id(_stream_task), self._cancelled)

        parts: list[str] = []
        _streamed_via_text = False  # True once on_text_chunk has delivered tokens

        try:
            logger.debug("%s entering queue.get() consumer loop", _sa_log_prefix)
            _sa_deadline = subagent_timeout
            while True:
                if self._cancelled:
                    logger.debug("%s cancelled — breaking consumer loop", _sa_log_prefix)
                    yield (StreamEvent.subagent_end(
                        "", agent_type=agent_type, status="failed", error="cancelled",
                    ), "")
                    return
                try:
                    item_type, item = await asyncio.wait_for(
                        _queue.get(),
                        timeout=min(1.0, _sa_deadline),
                    )
                    _sa_deadline = subagent_timeout  # reset on each item
                except asyncio.TimeoutError:
                    _sa_deadline -= 1.0
                    if _sa_deadline <= 0:
                        logger.warning(
                            "%s subagent timed out after %ds — cancelling",
                            _sa_log_prefix, subagent_timeout,
                        )
                        yield (StreamEvent.subagent_end(
                            "", agent_type=agent_type, status="failed",
                            error=f"timed out after {subagent_timeout}s",
                        ), "")
                        return
                    continue
                _sa_chunk_count += 1
                if _sa_chunk_count <= 5 or _sa_chunk_count % 50 == 0:
                    logger.debug(
                        "%s queue.get() #%d type=%s cancelled_flag=%s qsize=%d "
                        "text=%d bytes=%d",
                        _sa_log_prefix, _sa_chunk_count, item_type,
                        self._cancelled, _queue.qsize(), _sa_text_count,
                        _sa_total_bytes,
                    )

                if item_type == "text":
                    _streamed_via_text = True
                    parts.append(item)
                    yield (StreamEvent.text_delta(item), item)

                elif item_type == "event":
                    chunk = item
                    if isinstance(chunk, StreamEvent):
                        if chunk.type == StreamEventType.TEXT_DELTA and chunk.text:
                            # Skip TEXT_DELTA if tokens were already streamed
                            # in real-time via on_text_chunk (avoids doubles).
                            if not _streamed_via_text:
                                if _sa_chunk_count <= 5:
                                    logger.debug(
                                        "%s TEXT_DELTA via event path (no "
                                        "streamed_via_text) bytes=%d",
                                        _sa_log_prefix, len(chunk.text),
                                    )
                                parts.append(chunk.text)
                                yield (chunk, chunk.text)
                            else:
                                if _sa_chunk_count <= 3:
                                    logger.debug(
                                        "%s TEXT_DELTA skipped (already "
                                        "streamed_via_text) bytes=%d",
                                        _sa_log_prefix, len(chunk.text),
                                    )
                        elif chunk.type == StreamEventType.THINKING and chunk.thinking:
                            logger.debug("%s THINKING event bytes=%d",
                                         _sa_log_prefix, len(chunk.thinking))
                            yield (chunk, chunk.thinking)
                        elif chunk.type == StreamEventType.TOOL_CALL_START:
                            logger.debug("%s TOOL_CALL_START tool=%s",
                                         _sa_log_prefix, chunk.tool_name)
                            yield (StreamEvent.subagent_tool_call(
                                subagent_id, "start", chunk.tool_id,
                                chunk.tool_name, chunk.tool_category,
                            ), "")
                        elif chunk.type == StreamEventType.TOOL_CALL_COMPLETE:
                            logger.debug("%s TOOL_CALL_COMPLETE tool=%s",
                                         _sa_log_prefix, chunk.tool_name)
                            yield (StreamEvent.subagent_tool_call(
                                subagent_id, "complete", chunk.tool_id,
                                chunk.tool_name, chunk.tool_category,
                                chunk.tool_args,
                            ), "")
                        elif chunk.type == StreamEventType.TOOL_RESULT:
                            logger.debug("%s TOOL_RESULT tool=%s",
                                         _sa_log_prefix, chunk.tool_name)
                            yield (StreamEvent.subagent_tool_result(
                                subagent_id, chunk.tool_id, chunk.tool_name,
                                chunk.result_content, chunk.result_is_error,
                                chunk.result_category,
                            ), "")
                        elif chunk.type == StreamEventType.ERROR:
                            logger.debug("%s ERROR event msg=%s",
                                         _sa_log_prefix, chunk.error_message)
                            text = f"\n[Error: {chunk.error_message}]\n"
                            yield (StreamEvent.text_delta(text), text)
                    else:
                        if chunk:
                            parts.append(chunk)

                elif item_type == "done":
                    logger.debug("%s queue.get()=done → break loop", _sa_log_prefix)
                    break

                elif item_type == "cancelled":
                    logger.debug(
                        "%s queue.get()=cancelled → yield subagent_end "
                        "failed=cancelled", _sa_log_prefix)
                    yield (StreamEvent.subagent_end(
                        "", agent_type=agent_type, status="failed", error="cancelled",
                    ), "")
                    return

                elif item_type == "error":
                    logger.exception("%s queue.get()=error: %s", _sa_log_prefix, item)
                    err_text = (
                        f"SUMMARY:\nSub-agent failed with error: {item}\n\n"
                        "CHANGES:\nNone.\n\nEVIDENCE:\nNone.\n\nRISKS:\nNone.\n\n"
                        f"BLOCKERS:\n{item}"
                    )
                    yield (StreamEvent.subagent_end(
                        "", agent_type=agent_type, status="failed", error=str(item),
                    ), err_text)
                    return

        except asyncio.CancelledError:
            logger.debug("%s consumer loop CancelledError → subagent_end", _sa_log_prefix)
            # Parent cancelled — emit subagent_end so the TUI widget
            # transitions out of "running", then re-raise.
            yield (StreamEvent.subagent_end(
                "", agent_type=agent_type, status="failed", error="cancelled",
            ), "")
            raise
        finally:
            logger.debug(
                "%s consumer finally: stream_task.done=%s cancelled_flag=%s "
                "text=%d bytes=%d chunk_events=%d",
                _sa_log_prefix, _stream_task.done(), self._cancelled,
                _sa_text_count, _sa_total_bytes, _sa_chunk_count,
            )
            if not _stream_task.done():
                logger.debug("%s finally: cancelling _stream_task (still running)",
                             _sa_log_prefix)
                _stream_task.cancel()
                try:
                    logger.debug("%s finally: awaiting _stream_task ...",
                                 _sa_log_prefix)
                    await _stream_task
                    logger.debug("%s finally: await _stream_task returned cleanly",
                                 _sa_log_prefix)
                except asyncio.CancelledError:
                    logger.debug("%s finally: await _stream_task CancelledError",
                                 _sa_log_prefix)
                except Exception as e:
                    logger.debug("%s finally: await _stream_task exception=%s",
                                 _sa_log_prefix, e)
            if sub_engine in self._child_engines:
                self._child_engines.remove(sub_engine)
            logger.debug(
                "%s finally done text=%d bytes=%d chunk_events=%d",
                _sa_log_prefix, _sa_text_count, _sa_total_bytes, _sa_chunk_count,
            )

        # Normal completion
        yield (StreamEvent.subagent_end(
            "", agent_type=agent_type, status="completed",
        ), "".join(parts))

    _SUBAGENT_SECTION_RE = re.compile(
        r'^(SUMMARY|CHANGES|EVIDENCE|RISKS|BLOCKERS):\s*$',
        re.IGNORECASE | re.MULTILINE,
    )

    def _format_subagent_output(self, agent_type: str, prompt: str, result: str) -> str:
        """Format sub-agent output in DeepSeek-TUI structured contract format.
        
        Output contract:
        SUMMARY: one paragraph; what you did and what happened
        CHANGES: files modified, with one-line descriptions; "None." if read-only
        EVIDENCE: path:line-range citations and key findings; one bullet each
        RISKS: what could go wrong / what the parent should double-check
        BLOCKERS: what stopped you; "None." if you finished cleanly
        """
        # Detect structured sections via line-start regex, not substring match
        has_sections = self._SUBAGENT_SECTION_RE.search(result) is not None

        if has_sections:
            return result

        return (
            f"SUMMARY:\n{agent_type.capitalize()} agent completed task: {prompt[:200]}\n\n"
            f"CHANGES:\nNone detected.\n\n"
            f"EVIDENCE:\n- See detailed output below\n\n"
            f"RISKS:\nNone identified.\n\n"
            f"BLOCKERS:\nNone.\n\n"
            f"--- Raw Output ---\n{result}"
        )

    def spawn_subagent(self, agent_type: str, prompt: str) -> dict:
        if self.current_agent.permission_task == AgentPermission.DENY:
            return {"success": False, "error": "Subagent denied"}
        import asyncio
        try:
            result = asyncio.run(self._spawn_subagent_async(agent_type, prompt))
        except Exception as e:
            logger.exception(f"Subagent error: {e}")
            return {"success": False, "error": safe_error_msg(e)}
        return {
            "success": True,
            "agent_type": agent_type,
            "response": result,
            "iterations": 1,
        }

    def tool_task(self, agent_type: str, prompt: str) -> str:
        result = self.spawn_subagent(agent_type, prompt)
        if result["success"]:
            return result["response"]
        return f"Error: {result.get('error') or 'Unknown error'}"

    def attach_session(self, session: AgentSession) -> None:
        self._session = session
        if session.messages:
            self.context.load_from_session(session.messages)
        if session.todos:
            self._todo_manager.reload_from_dict({
                "todos": session.todos,
                "id_counter": len(session.todos),
            })
        # Restore context usage stats
        self._restore_session_stats(session)

    def save_session(self) -> None:
        if self._session:
            try:
                self._session.messages = self.context.to_session_format()
                tm_data = self._todo_manager.to_dict()
                self._session.todos = tm_data.get("todos", [])
                # Persist context usage stats so they survive session reload
                self._session.update_state("stats", {
                    "total_tokens": self.total_tokens,
                    "iterations": self.iterations,
                    "turn_usages": [
                        {k: v for k, v in u.items() if isinstance(v, (int, float))}
                        for u in self._turn_usages
                    ],
                })
                self._session.save()
            except Exception as e:
                logger.exception("Failed to save session: %s", e)

    def load_session(self, session_id: str) -> bool:
        session = AgentSession(session_id)
        if not session.load():
            return False
        self._session = session
        self.context.load_from_session(session.messages)
        if session.todos:
            self._todo_manager.reload_from_dict({
                "todos": session.todos,
                "id_counter": len(session.todos),
            })
            self._inject_loaded_tasks_into_context()
        # Restore context usage stats
        self._restore_session_stats(session)
        return True

    def _inject_loaded_tasks_into_context(self) -> None:
        """Surface loaded todos to the LLM so it can continue them.

        Todos loaded from a previous session are not automatically visible
        in the LLM context — without this nudge the agent would re-create
        them on every fresh turn instead of resuming pending work.
        """
        all_todos = self._todo_manager.list_todos()
        pending = [t for t in all_todos if t.get("status") in ("pending", "in_progress")]
        if not pending:
            return

        lines = ["# Resumed todos from previous session", ""]
        lines.append("## Todos")
        for t in pending:
            status = t.get("status", "pending")
            marker = {"in_progress": "[~]", "pending": "[ ]"}.get(status, "[?]")
            subject = t.get("subject") or t.get("description", "")
            desc = t.get("description") or ""
            if desc and desc != subject:
                lines.append(f"- {marker} (id={t.get('id')}) {subject} — {desc}")
            else:
                lines.append(f"- {marker} (id={t.get('id')}) {subject}")
        lines.append("")

        lines.append(
            "Continue working on any in_progress or pending todos above. "
            "Use TodoList/TodoGet to inspect details and TodoUpdate to "
            "advance status. Do NOT recreate todos that already exist."
        )
        marker = "<!-- loaded_todos_resume -->"
        body = f"{marker}\n" + "\n".join(lines)
        if not self.context.replace_system_section(marker, body):
            self.context.add_system(body)

    def _restore_session_stats(self, session: AgentSession) -> None:
        """Restore context usage stats from session lifecycle_state."""
        stats = session.get_state("stats", {})
        if not stats:
            return
        self.total_tokens = int(stats.get("total_tokens", self.total_tokens))
        self.iterations = int(stats.get("iterations", self.iterations))
        restored_turns = stats.get("turn_usages", [])
        if restored_turns and isinstance(restored_turns, list):
            self._turn_usages = list(restored_turns)

    def save_todos_to_project(self) -> None:
        """Save todos to .cdh/todos.json — uses find_cdh_dir_for_todos
        so sub-projects never overwrite a parent project's todos."""
        from onecode.agent.cdh_loader import CdhProjectLoader
        cdh_dir = CdhProjectLoader.find_cdh_dir_for_todos(self._project_dir)
        if cdh_dir is None:
            cdh_dir = self._project_dir / CdhProjectLoader.CDH_DIRNAME
            try:
                cdh_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.warning("Failed to create .cdh directory: %s", e)
                return
        try:
            tm_data = self._todo_manager.to_dict()
            CdhProjectLoader.save_todos(cdh_dir, tm_data)
        except Exception as e:
            logger.warning("Failed to save todos to .cdh: %s", e)

    def load_todos_from_project(self) -> None:
        """Restore todos from .cdh/todos.json — uses find_cdh_dir_for_todos
        so sub-projects never accidentally load a parent project's todos.
        If todos are found, the ``<!-- NEW_SESSION_HINT -->`` marker is
        removed from the system context (it only applies to blank sessions)."""
        from onecode.agent.cdh_loader import CdhProjectLoader
        cdh_dir = CdhProjectLoader.find_cdh_dir_for_todos(self._project_dir)
        if cdh_dir is None:
            return
        try:
            data = CdhProjectLoader.load_todos(cdh_dir)
            if data and (data.get("tasks") or data.get("todos")):
                self._todo_manager.reload_from_dict(data)
                self.context.remove_system_by_marker("<!-- NEW_SESSION_HINT -->")
        except Exception as e:
            logger.warning("Failed to load todos from .cdh: %s", e)

    def get_session(self) -> Optional[AgentSession]:
        return self._session