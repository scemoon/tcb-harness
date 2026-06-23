from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import AsyncIterator, Optional

from dataclasses import dataclass
from typing import Callable

from onecode.agent.context import ContextManager
from onecode.agent.permissions_store import PermissionStore
from onecode.models.provider import ContentBlockType, ProviderRegistry

from onecode.agent.session import AgentSession
from onecode.models.messages import StreamEvent, StreamEventType

logger = logging.getLogger("onecode.agent.engine")


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


_TASK_STATUSES = {"pending", "in_progress", "completed"}


class TaskManager:
    """V2 task manager with dependency tracking (Clawd-Code style).

    Tasks have: id, subject, description, status, owner, blocks, blockedBy, metadata, output.
    Supports dependency tracking for multi-agent coordination.
    """

    def __init__(self, on_change: Callable[[], None] | None = None):
        self._tasks: dict[str, dict] = {}  # id -> task dict
        self._todos: list[dict] = []
        self._plan: list[str] = []
        self._id_counter = 0
        self._on_change = on_change

    def _mark_dirty(self) -> None:
        if self._on_change:
            self._on_change()

    def _next_id(self) -> str:
        self._id_counter += 1
        return f"t{self._id_counter}"

    # ── V2 Task Management ──

    def create_task(
        self,
        subject: str,
        description: str = "",
        active_form: str = "",
        metadata: dict | None = None,
    ) -> dict:
        """Create a task with dependency tracking support."""
        task_id = self._next_id()
        task = {
            "id": task_id,
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
        self._tasks[task_id] = task
        self._mark_dirty()
        return task

    def get_task(self, task_id: str) -> dict | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[dict]:
        """List all tasks in creation order."""
        return list(self._tasks.values())

    def update_task(self, task_id: str, **fields) -> dict | None:
        """Update task fields. Supports: subject, description, activeForm, status,
        owner, metadata, addBlocks, addBlockedBy. Returns updated task or None."""
        task = self._tasks.get(task_id)
        if task is None:
            return None

        updated = []

        # String fields
        for field in ("subject", "description", "activeForm", "owner"):
            if field in fields:
                v = fields[field]
                if isinstance(v, str) and v != task.get(field):
                    task[field] = v
                    updated.append(field)

        # Status field
        if "status" in fields:
            status = fields["status"]
            if status == "deleted":
                self._tasks.pop(task_id, None)
                self._mark_dirty()
                return {"id": task_id, "deleted": True}
            if status in _TASK_STATUSES and status != task.get("status"):
                task["status"] = status
                updated.append("status")

        # Dependency fields
        for rel_field, input_key in (("blocks", "addBlocks"), ("blockedBy", "addBlockedBy")):
            if input_key in fields:
                ids = fields[input_key]
                if isinstance(ids, list):
                    cur = list(task.get(rel_field) or [])
                    for x in ids:
                        if isinstance(x, str) and x not in cur:
                            cur.append(x)
                    if cur != task.get(rel_field):
                        task[rel_field] = cur
                        updated.append(rel_field)

        # Metadata
        if "metadata" in fields:
            md = fields["metadata"]
            if isinstance(md, dict):
                existing = dict(task.get("metadata") or {})
                for k, v in md.items():
                    if v is None:
                        existing.pop(k, None)
                    else:
                        existing[k] = v
                task["metadata"] = existing
                updated.append("metadata")

        # Output
        if "output" in fields:
            v = fields["output"]
            if isinstance(v, str):
                task["output"] = v
                updated.append("output")

        self._mark_dirty()
        return task

    def get_task_output(self, task_id: str) -> dict:
        """Get output for a task."""
        task = self._tasks.get(task_id)
        if task is None:
            return {"retrieval_status": "not_found", "task": None}
        output = str(task.get("output") or "")
        return {
            "retrieval_status": "success" if output else "not_ready",
            "task": {
                "task_id": task_id,
                "task_type": "task_list",
                "status": task.get("status"),
                "description": task.get("description"),
                "output": output,
            },
        }

    def clear_tasks(self) -> None:
        self._tasks.clear()
        self._mark_dirty()

    # ── Todo Management (unchanged API) ──

    def add_todo(self, text: str) -> str:
        tid = self._next_id()
        self._todos.append({"text": text, "done": False, "id": tid})
        self._mark_dirty()
        return tid

    def complete_todo(self, todo_id: str) -> bool:
        for t in self._todos:
            if t["id"] == todo_id:
                t["done"] = True
                self._mark_dirty()
                return True
        return False

    def remove_todo(self, todo_id: str) -> bool:
        before = len(self._todos)
        self._todos = [t for t in self._todos if t["id"] != todo_id]
        result = len(self._todos) < before
        self._mark_dirty()
        return result

    def list_todos(self) -> list[dict]:
        return self._todos

    def clear_todos(self) -> None:
        self._todos = []
        self._mark_dirty()

    def set_plan(self, plan: list[str]) -> None:
        self._plan = plan
        self._mark_dirty()

    def get_plan(self) -> list[str]:
        return self._plan

    # ── Serialization ──

    def to_dict(self) -> dict:
        """Serialize all tasks and todos for persistence."""
        return {
            "tasks": [dict(t) for t in self._tasks.values()],
            "todos": [dict(t) for t in self._todos],
            "plan": list(self._plan),
            "id_counter": self._id_counter,
        }

    @classmethod
    def from_dict(cls, data: dict, on_change: Callable[[], None] | None = None) -> TaskManager:
        """Restore task manager from saved dict."""
        tm = cls(on_change=on_change)
        tm._id_counter = data.get("id_counter", 0)
        tm._plan = list(data.get("plan", []))
        for t in data.get("tasks", []):
            tid = t.get("id", tm._next_id())
            tm._tasks[tid] = dict(t)
        for t in data.get("todos", []):
            tm._todos.append(dict(t))
        return tm


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
        self.current_agent: AgentConfig = BuildAgent()
        self.iterations = 0
        self.total_tokens = 0
        self._skills_loaded = False
        self._session: Optional[AgentSession] = None
        self._hooks = HookManager()
        self._task_manager = TaskManager(on_change=self._on_task_change)
        self._plan_dirty: bool = False
        self._project_config: dict = {}
        self._project_context_loaded = False
        self._pending_approval: dict | None = None  # {tool_call, result_key}
        self._last_user_msg: str | None = None  # Last SendMessage visible to user

        # Clawd-Code subsystems
        self._skill_loader = SkillLoader()
        self._mcp = MCPManager()
        self._cron_scheduler = CronScheduler()
        self._lsp_tool = LSPTool()
        app_config = getattr(app, 'config', None)
        self._config_tool_read = ConfigReadTool(app_config) if app_config else None
        self._config_tool_write = ConfigWriteTool(app_config) if app_config else None

        # Codebase engine (lazy init)
        self._codebase_engine: Optional["CodebaseEngine"] = None

        # Tool registry (Clawd-Code pattern)
        self._tool_registry = self._build_tool_registry()
        self._send_message_tool = SendMessageTool()

        # Per-turn usage tracking (Clawd-Code style)
        self._turn_usages: list[dict[str, int]] = []

        # Event callbacks
        self.on_event: ToolEventHandler | None = None
        self.on_text_chunk: Callable[[str], None] | None = None
        self.on_tool_call_delta: Callable[[str, str, str], None] | None = None
        self.on_thinking: Callable[[str], None] | None = None
        self._streaming_used: bool = False
        self._pending_thinking_blocks: list[str] = []

        # Cancellation support
        self._cancelled: bool = False

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
        self._plan_gate_fired: bool = False

        # ReAct state tracking
        self._react_phase: str = "thought"  # "thought" | "action" | "observation"
        self._direct_execution_count: int = 0  # Track direct tool use for Task-first routing

    def _build_tool_registry(self) -> ToolRegistry:
        from onecode.agent.tools.registry import ToolRegistry
        from onecode.agent.tools.file_tools import ReadTool, WriteTool, EditTool, InsertTool, UndoEditTool, GlobTool, GrepTool, ListTool
        from onecode.agent.tools.apply_patch_tool import ApplyPatchTool
        from onecode.agent.tools.bash_tool import BashTool
        from onecode.agent.tools.web_tools import WebFetchTool, WebSearchTool
        from onecode.agent.tools.communication_tools import SendMessageTool, AskUserTool, ToolSearchTool
        from onecode.agent.tools.task_tools import (TaskCreateTool, TaskGetTool, TaskListTool, TaskUpdateTool,
            TaskOutputTool, TaskStopTool, TodoCreateTool, TodoListTool, TodoCompleteTool)
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
        registry.register(TaskCreateTool(self._task_manager))
        registry.register(TaskGetTool(self._task_manager))
        registry.register(TaskListTool(self._task_manager))
        registry.register(TaskUpdateTool(self._task_manager))
        registry.register(TaskOutputTool(self._task_manager))
        registry.register(TaskStopTool(self._task_manager))
        registry.register(TodoCreateTool(self._task_manager))
        registry.register(TodoListTool(self._task_manager))
        registry.register(TodoCompleteTool(self._task_manager))
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

    def _plan_gate_first_turn(self) -> bool:
        """Returns True only on the first turn where no plan exists yet.
        
        Once tasks are created or the gate has fired, subsequent turns
        proceed without gate intervention.
        """
        if self._plan_gate_fired:
            return False
        self._plan_gate_fired = True
        return True

    def _notify_event(self, event: ToolEvent) -> None:
        """Emit a ToolEvent to the registered callback (Clawd-Code pattern)."""
        if self.on_event:
            try:
                self.on_event(event)
            except Exception as e:
                logger.warning("ToolEvent callback failed: %s", e)

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
        """Emit a plan update event from current tasks and todos."""
        entries = []
        for task in self._task_manager.list_tasks():
            entries.append({
                "content": task.get("subject", task.get("description", "")),
                "status": task.get("status", "pending"),
                "priority": task.get("metadata", {}).get("priority", "medium"),
            })
        for todo in self._task_manager.list_todos():
            entries.append({
                "content": todo.get("text", ""),
                "status": "completed" if todo.get("done") else "pending",
                "priority": "low",
            })
        return [StreamEvent.plan(entries)]

    def _on_task_change(self) -> None:
        """Callback invoked by TaskManager whenever tasks/todos mutate.

        Sets a dirty flag so the next opportunity in ``chat_stream`` will
        emit a fresh plan event.  Decoupling the callback from the emit
        keeps the public API synchronous and avoids re-entrancy when
        subagents mutate the same TaskManager concurrently.

        Also persists tasks to ``.cdh/tasks.json`` immediately so they
        survive a crash or Ctrl+C before the next ACP turn boundary.
        """
        self._plan_dirty = True
        self.save_tasks_to_project()

    @property
    def _workspace(self) -> Path:
        return self._project_dir

    def set_agent(self, agent_type: str) -> None:
        from onecode.agent.agents.types import (
            AgentPermission,
            create_agent,
            PLAN_INSTRUCTIONS,
            REACT_CYCLE,
            TOOL_DESCRIPTIONS,
            filter_tool_descriptions,
        )
        self.current_agent = create_agent(agent_type)
        system_parts = [self.current_agent.description]

        edit_ask = self.current_agent.should_ask_for_edit()
        bash_ask = self.current_agent.should_ask_for_bash()
        if edit_ask or bash_ask:
            restrictions = []
            if edit_ask:
                restrictions.append("- File edits require user approval")
            if bash_ask:
                restrictions.append("- Shell commands require user approval")
            system_parts.append("\n".join(restrictions))

        if self.current_agent.permission_task != AgentPermission.DENY:
            system_parts.append(REACT_CYCLE)
            system_parts.append(PLAN_INSTRUCTIONS)

        # Tell the model how to format intermediate reasoning so the TUI
        # can render it as a collapsible "thought" block instead of
        # leaking it into the visible answer.  Without these tags, the
        # model's planning prose ("I will now update X…", "X is done,
        # let me verify…") flows through as plain ``agent_message_chunk``
        # and shows up in chat interleaved with tool calls.
        system_parts.append(
            "\n## Response style\n"
            "- **Every turn must start with Chain of Thought reasoning** "
            "inside `<thinking>`. Analyze the current state, determine the "
            "next step, and decide whether to delegate via `Task`.\n"
            "- **Prefer `Task` delegation**: For any multi-step operation, "
            "file modification, or research, use `Task(agent_type, prompt)` "
            "rather than calling execution tools directly.\n"
            "- If you need to reason between tool calls, wrap your "
            "reasoning in `<thinking>...</thinking>`.  The TUI will "
            "render the wrapped block as a collapsible thought and "
            "keep it out of the main answer.\n"
            "- Do not narrate your plan in the visible answer.  Avoid "
            'phrases like "I will now…", "Let me first…", "X is done, '
            'let me verify…" — those should go inside `<thinking>`.  '
            "The visible answer is only the final user-facing summary.\n"
        )

        tool_desc = filter_tool_descriptions(
            allowlist=self.current_agent.tools or None,
            denylist=self.current_agent.disallowed_tools or None,
        )
        system_parts.append(tool_desc)

        tagged_content = "<!-- AGENT_CONFIG -->\n" + "\n".join(system_parts)
        if not self.context.replace_system_section("AGENT_CONFIG", tagged_content):
            self.context.add_system(tagged_content)

        # Re-apply user permission overrides (e.g. "allow always")
        self._perm_store.apply_to(self.current_agent)

    def get_available_tools(self) -> str:
        from onecode.agent.agents.types import TOOL_DESCRIPTIONS, filter_tool_descriptions
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
        self.context.remove_system_by_marker("<!-- CDH_PROJECT -->")
        self._skills_loaded = True

        for skill in self._skill_loader.get_enabled():
            tagged = f"<!-- SKILL:{skill.name} -->\n{skill.content}"
            self.context.add_system(tagged)

        # Load project .cdh/ state into context
        from onecode.agent.cdh_loader import CdhProjectLoader
        cdh_content = CdhProjectLoader.load_for_workspace(self._workspace)
        if cdh_content:
            self.context.add_system(f"<!-- CDH_PROJECT -->\n{cdh_content}")

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

        agents_md_path = self._workspace / "AGENTS.md"
        if agents_md_path.exists():
            try:
                content = agents_md_path.read_text(encoding="utf-8")
                context_parts.append(f"\n--- AGENTS.md ---\n{content[:2000]}")
            except Exception:
                pass

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
        self._load_skills()

        project_name = getattr(self.app, "current_project", None) or ""
        if project_name:
            self._inject_project_context(project_name)

        self.context.add_user(user_input)

        self.context.config.model = self.app.current_model
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
        "Task": "task",
        "Agent": "task",
        "Skill": "skill",
    }

    def _check_tool_permission(self, name: str, inp: dict) -> str | None:
        """Unified agent-level permission check for all tools."""
        from onecode.agent.agents.types import AgentPermission
        perm_key = self._TOOL_NAME_TO_PERM_KEY.get(name)
        if perm_key is None:
            return None
        tools_config = self.current_agent.get_tools_config()
        perm = tools_config.get(perm_key, AgentPermission.ALLOW)
        if perm == AgentPermission.DENY:
            return json.dumps({"success": False, "error": f"{name} denied"})
        if perm == AgentPermission.ASK:
            return json.dumps({"success": False, "error": f"{name} requires approval", "requires_approval": True})
        return None

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
                return {**base, "content": denied, "is_error": True}

            call = RegistryToolCall(name=name, input=inp, tool_use_id=tid)
            result = self._tool_registry.dispatch(call)

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
            return {**base, "content": f"Error: {e}", "is_error": True}

    def _format_tool_output(self, result: RegistryToolResult) -> str:
        import json
        output = result.output
        if isinstance(output, str):
            return output
        try:
            return json.dumps(output)
        except (TypeError, ValueError):
            return str(output)

    async def cancel(self):
        """Cancel the current chat_stream turn and all in-flight subagents."""
        self._cancelled = True
        for child in self._child_engines:
            child._cancelled = True

    async def chat_stream(self, user_input: str | list[dict]) -> AsyncIterator[StreamEvent | str]:
        self._load_skills()
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
        if isinstance(user_input, str) and self._should_retrieve_codebase():
            try:
                engine = await self._get_codebase_engine()
                if engine:
                    chunks = await engine.retrieve(user_input)
                    ctx_text = engine.format_context(
                        chunks, max_tokens=self.app.config.codebase.max_chunk_tokens
                    )
                    if ctx_text:
                        if not self.context.replace_system_section("CODEBASE", ctx_text):
                            self.context.add_system(f"<!-- CODEBASE -->\n{ctx_text}")
            except Exception as e:
                logger.warning("Codebase retrieval failed: %s", e)

        self.context.add_user(user_input)

        # Plan gate: activate based on agent mode, not content heuristics.
        # Gate fires reactively when agent tries execution tools without a plan.
        self._plan_gate_mode = self._resolve_plan_gate_mode()

        self.context.config.model = self.app.current_model
        if self.context.should_compact():
            level = self.context.compact()
            if level not in ("none",):
                logger.info("Context compaction at turn start: %s", level)

        provider_name = self.app.current_provider
        model_name = self.app.current_model
        logger.info(f"Using provider='{provider_name}', model='{model_name}'")
        logger.info(
            "chat_stream engine state: project=%s agent=%s tasks=%d todos=%d context_msgs=%d ctx_tokens=%d",
            project_name or "(none)",
            self.current_agent.name if self.current_agent else "None",
            len(self._task_manager.list_tasks()),
            len(self._task_manager.list_todos()),
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

        # Reset per-turn usage tracking
        self._turn_usages = []

        # Reset cancellation flag (adapter also resets it before calling)
        self._cancelled = False

        # ── Agent loop: CoT + ReAct (思考 → 行动 → 观察) ──
        is_anthropic = provider.is_anthropic_style()
        max_turns = self.current_agent.max_turns or 10

        # Initialize ReAct phase section (first turn prompt)
        cot_phase_init = (
            "<!-- REACT_PHASE -->\n"
            "## Turn 1 — Thought Phase (思考)\n"
            "Begin this turn by reasoning step by step in `<thinking>`:\n"
            "1. **Current state**: Analyze the user request and what needs to be done.\n"
            "2. **Goal**: What should I accomplish this turn?\n"
            "3. **Approach**: Should I delegate via `Task`, plan via `task_create`, "
            "or use a direct tool?\n"
            "4. **Task-first**: For any multi-step work or file modifications, "
            "prefer `Task(agent_type, prompt)` over direct execution tools.\n"
        )
        if not self.context.replace_system_section("REACT_PHASE", cot_phase_init):
            self.context.add_system(cot_phase_init)

        for turn in range(max_turns):
            if self._cancelled:
                yield StreamEvent.text_delta("\n\n*Turn cancelled*\n\n")
                return

            # ── Thought Phase: update CoT reasoning guidance for this turn ──
            # Cleanup stale reminders that may have accumulated
            self.context.remove_system_by_marker("<!-- TASK_FIRST_REMINDER -->")
            if turn > 0:
                cot_phase = (
                    f"<!-- REACT_PHASE -->\n"
                    f"## Turn {turn + 1} — Thought Phase (思考)\n"
                    "Begin this turn by reasoning step by step in `<thinking>`:\n"
                    "1. **Current state**: What just happened? What results do I have?\n"
                    "2. **Goal**: What should I accomplish this turn?\n"
                    "3. **Approach**: Should I delegate via `Task`, plan via `task_create`, "
                    "or use a direct tool?\n"
                    "4. **Task-first**: For any multi-step work or file modifications, "
                    "prefer `Task(agent_type, prompt)` over direct execution tools.\n"
                )
                self.context.replace_system_section("REACT_PHASE", cot_phase)

            self._pending_thinking_blocks = []

            self.context.config.model = self.app.current_model
            if self.context.should_compact():
                level = self.context.compact()
                if level not in ("none",):
                    logger.info("Context compaction at turn %d: %s", turn, level)

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
                        _original_cb(text)
                    stream_cb = _stream_wrapper
                else:
                    stream_cb = None
                chat_response = await provider.chat_stream_response(
                    context_messages,
                    model=model_name,
                    on_text_chunk=stream_cb,
                    on_tool_call_delta=self.on_tool_call_delta,
                    tools=self._tool_registry.make_openai_schemas(),
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
                        tools=self._tool_registry.make_openai_schemas(),
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
                except Exception as e:
                    logger.exception(f"Error during chat() fallback turn {turn+1}: {e}")
                    yield StreamEvent.error(str(e))
                    break
            except Exception as e:
                ctx_msgs = len(self.context.messages)
                ctx_tokens = self.context._token_count
                logger.exception(
                    f"Error during chat_stream_response turn {turn+1}: {e}\n"
                    f"  provider={provider_name} model={model_name} "
                    f"context_msgs={ctx_msgs} ctx_tokens={ctx_tokens}"
                )
                yield StreamEvent.error(f"Provider error (turn {turn+1}): {e}")
                break

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
            # to the onecode root logger → ~/.cdh/logs/cdh.log when
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

            if not tool_uses:
                if not self._streaming_used:
                    if clean_text.strip():
                        for i in range(0, len(clean_text), 12):
                            yield StreamEvent.text_delta(clean_text[i:i + 12])
                    elif self._last_user_msg:
                        yield StreamEvent.text_delta(self._last_user_msg)
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
                logger.info(f"Executing tool: {tu['name']} (id={tu['id']})")

                # Task tool: forward subagent text deltas to the TUI as
                # subagent_chunk events so the SubAgent widget actually has
                # content to render.  The Task tool's spec is (agent_type,
                # prompt); we read them from the tool input.
                if tu["name"] == "Task":
                    # Permission check
                    denied = self._check_tool_permission("Task", tu["input"])
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
                        yield StreamEvent.subagent_start(subagent_type, tu["id"])
                        accumulated: list[str] = []
                        async for sub_event, sub_text in self._spawn_subagent_async_streaming(
                            subagent_type, subagent_prompt
                        ):
                            if sub_text and sub_event.type == StreamEventType.SUBAGENT_END:
                                accumulated.append(sub_text)
                            elif sub_text:
                                accumulated.append(sub_text)
                                yield StreamEvent.subagent_chunk(tu["id"], sub_text)
                        yield StreamEvent.subagent_end(tu["id"])
                        formatted = self._format_subagent_output(
                            subagent_type, subagent_prompt, "".join(accumulated)
                        )
                        result = {
                            "tool_use_id": tu["id"],
                            "is_error": False,
                            "category": "task",
                            "content": formatted,
                        }
                elif (self._plan_gate_mode != "off"
                      and not self._task_manager.list_tasks()
                      and tu["name"] in _EXECUTION_TOOLS
                      and self._plan_gate_first_turn()):
                    if self._plan_gate_mode == "hard":
                        result = {
                            "tool_use_id": tu["id"],
                            "is_error": True,
                            "category": "task",
                            "content": json.dumps({
                                "success": False,
                                "error": (
                                    "Plan required. You are in plan mode (ReAct: Thought → Action → Observation). "
                                    "You MUST create a task plan using task_create() before using execution tools. "
                                    "First Think (analyze/explore), then Act by creating ALL tasks upfront "
                                    "with dependencies, present the plan for user review, "
                                    "and only then proceed to execute."
                                ),
                            }),
                        }
                    else:
                        # Soft gate: execute but inject a reminder for next turn
                        self.context.add_system(
                            "<!-- PLAN_REMINDER -->\n"
                            "Note: You used a direct execution tool without delegating via Task. "
                            "For any non-trivial operation, prefer `Task(agent_type, prompt)` "
                            "to delegate the work to a focused subagent instead. Task subagents "
                            "encapsulate multi-step logic, keep the main context clean, and "
                            "return structured SUMMARY/CHANGES/EVIDENCE/RISKS/BLOCKERS output."
                        )
                        result = await self._execute_tool(tu)
                else:
                    result = await self._execute_tool(tu)
                    # Task-first routing: track direct execution tool use
                    if tu["name"] in _EXECUTION_TOOLS:
                        self._direct_execution_count += 1
                        if self._direct_execution_count >= 2:
                            self.context.add_system(
                                "<!-- TASK_FIRST_REMINDER -->\n"
                                "Reminder: You're using direct execution tools repeatedly. "
                                "For multi-step work, delegate via `Task(agent_type, prompt)` instead. "
                                "This keeps the main context focused and work properly encapsulated."
                            )
                result_str = str(result.get("content", ""))
                is_error = result.get("is_error", False)
                category = result.get("category", "unknown")

                # Handle SendMessage — user-visible only, skip from LLM context
                if tu["name"] == "SendMessage":
                    try:
                        parsed = json.loads(result_str) if result_str else {}
                        msg = parsed.get("message", "")
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
                    question = parsed.get("question", "")
                    options = parsed.get("options", [])
                    questions = parsed.get("questions", [])

                    # Check for auto-default on single question + single option
                    if not questions and len(options) == 1 and options[0].get("default"):
                        default_val = options[0]["value"]
                        self._pending_approval = None
                        yield StreamEvent.tool_result(
                            call_id=tu["id"],
                            content=json.dumps({"answer": default_val}),
                        )
                        continue

                    # Auto-default for multi-question: skip questions that have
                    # a single option with default=true
                    if questions:
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
                    self._pending_approval = {"tool_call": tu, "category": category, "ask_user": True}
                    if has_questions:
                        yield StreamEvent.ask_user(
                            call_id=tu["id"],
                            action="AskUser",
                            question="",  # not used when questions is present
                            context=result_str,
                            options=[],
                            questions=questions,
                            action_type="ask_user",
                        )
                    else:
                        yield StreamEvent.ask_user(
                            call_id=tu["id"],
                            action="AskUser",
                            question=question,
                            context=result_str,
                            options=options,
                            action_type="ask_user",
                        )
                    continue

                # Detect ASK permission denial
                requires_approval = False
                try:
                    parsed = json.loads(result_str) if result_str else {}
                    requires_approval = parsed.get("requires_approval", False)
                except (json.JSONDecodeError, ValueError):
                    pass

                if requires_approval:
                    self._pending_approval = {"tool_call": tu, "category": category}
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
                    )
                else:
                    from onecode.models.messages import ToolCategory as MsgToolCategory
                    try:
                        result_cat = MsgToolCategory(category)
                    except ValueError:
                        result_cat = MsgToolCategory.UNKNOWN
                    self._notify_event(ToolEvent(
                        kind="tool_result",
                        tool_name=tu["name"],
                        tool_output=result_str,
                        tool_use_id=tu["id"],
                        is_error=is_error,
                    ))
                    yield StreamEvent.tool_result(
                        call_id=tu["id"],
                        content=result_str,
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
                    # Emit plan update when tasks/todos changed.  Any
                    # mutating path through TaskManager flips
                    # ``_plan_dirty`` via the ``on_change`` callback, so we
                    # do not need to enumerate tool names here.
                    if self._plan_dirty:
                        for event in self._emit_plan_update():
                            yield event
                        self._plan_dirty = False

            if self._cancelled:
                yield StreamEvent.text_delta("\n\n*Turn cancelled*\n\n")
                return

        usage_summary = ", ".join(
            f"turn {i+1}: {u.get('total_tokens', '?')} tokens"
            for i, u in enumerate(self._turn_usages) if u
        )
        logger.info(f"Chat stream complete after {self.iterations} turn(s). Usage: [{usage_summary}]")

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

    def _reset_react_state(self) -> None:
        """Reset ReAct loop state for a fresh cycle."""
        self._react_phase = "thought"
        self._direct_execution_count = 0
        self._plan_gate_fired = False
        self.context.remove_system_by_marker("<!-- REACT_PHASE -->")
        self.context.remove_system_by_marker("<!-- TASK_FIRST_REMINDER -->")

    def reset(self):
        self.context.reset()
        self.iterations = 0
        self.total_tokens = 0
        self._turn_usages = []
        self._skills_loaded = False
        self._project_context_loaded = False
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
        self, agent_type: str, prompt: str
    ) -> AsyncIterator[tuple[StreamEvent, str]]:
        """Streaming variant of :meth:`_spawn_subagent_async`.

        Yields ``(event, text)`` pairs so the caller (typically the Task-tool
        path in :meth:`chat_stream`) can forward each text delta as a
        ``subagent_chunk`` notification on the ACP wire.  The full agent text
        is also accumulated and emitted in a single ``(subagent_end, text)``
        payload at the end so callers that only care about the final output
        can ignore the intermediate chunks.

        Inherits project context and skills from the parent
        engine so the subagent does not start from a blank slate.
        """
        sub_engine = AgentEngine(self.app, project_dir=self._project_dir, perm_store=self._perm_store)

        # Inherit parent context: project info, skills
        sub_engine._project_context_loaded = self._project_context_loaded
        sub_engine._project_config = dict(self._project_config)
        sub_engine._skills_loaded = True
        for skill in self._skill_loader.get_enabled():
            if skill.content not in (m.content for m in sub_engine.context.messages if m.role == "system"):
                sub_engine.context.add_system(skill.content)

        sub_engine.set_agent(agent_type)

        # Track child so parent cancellation cascades
        self._child_engines.append(sub_engine)

        # Link the subagent's cancellation flag to the parent
        parts: list[str] = []
        try:
            async for chunk in sub_engine.chat_stream(prompt):
                if isinstance(chunk, StreamEvent):
                    if chunk.type == StreamEventType.TEXT_DELTA and chunk.text:
                        parts.append(chunk.text)
                        yield chunk, chunk.text
                else:
                    if chunk:
                        parts.append(chunk)
        except Exception as e:
            logger.exception(f"Subagent error: {e}")
            err_text = (
                f"SUMMARY:\nSub-agent failed with error: {e}\n\n"
                "CHANGES:\nNone.\n\nEVIDENCE:\nNone.\n\nRISKS:\nNone.\n\n"
                f"BLOCKERS:\n{e}"
            )
            yield StreamEvent.subagent_end(""), err_text
        else:
            yield StreamEvent.subagent_end(""), "".join(parts)
        finally:
            # Clean up completed subagent to prevent memory leak
            if sub_engine in self._child_engines:
                self._child_engines.remove(sub_engine)
    
    def _format_subagent_output(self, agent_type: str, prompt: str, result: str) -> str:
        """Format sub-agent output in DeepSeek-TUI structured contract format.
        
        Output contract:
        SUMMARY: one paragraph; what you did and what happened
        CHANGES: files modified, with one-line descriptions; "None." if read-only
        EVIDENCE: path:line-range citations and key findings; one bullet each
        RISKS: what could go wrong / what the parent should double-check
        BLOCKERS: what stopped you; "None." if you finished cleanly
        """
        # Try to detect if the result already has structured sections
        result_lower = result.lower()
        has_sections = all(
            tag.lower() in result_lower 
            for tag in ["summary", "changes", "evidence", "risks", "blockers"]
        )
        
        if has_sections:
            # Already structured — just ensure proper formatting
            return result
        else:
            # Add structured wrapper around raw result
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
        import concurrent.futures
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._spawn_subagent_async(agent_type, prompt), loop
                )
                result = future.result(timeout=300)
            else:
                result = asyncio.run(self._spawn_subagent_async(agent_type, prompt))
        except Exception as e:
            logger.exception(f"Subagent error: {e}")
            return {"success": False, "error": str(e)}
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
        return f"Error: {result.get('error', 'Unknown error')}"

    def attach_session(self, session: AgentSession) -> None:
        self._session = session
        if session.messages:
            self.context.load_from_session(session.messages)
        if session.tasks or session.todos:
            self._task_manager = TaskManager.from_dict({
                "tasks": session.tasks,
                "todos": session.todos,
                "plan": [],
                "id_counter": len(session.tasks) + len(session.todos),
            }, on_change=self._on_task_change)
        # Restore context usage stats
        self._restore_session_stats(session)

    def save_session(self) -> None:
        if self._session:
            try:
                self._session.messages = self.context.to_session_format()
                tm_data = self._task_manager.to_dict()
                self._session.tasks = tm_data.get("tasks", [])
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
        if session.load():
            self._session = session
            self.context.load_from_session(session.messages)
            if session.tasks or session.todos:
                self._task_manager = TaskManager.from_dict({
                    "tasks": session.tasks,
                    "todos": session.todos,
                    "plan": [],
                    "id_counter": len(session.tasks) + len(session.todos),
                }, on_change=self._on_task_change)
            # Restore context usage stats
            self._restore_session_stats(session)
            return True
        return False

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

    def save_tasks_to_project(self) -> None:
        """Save tasks/todos to .cdh/tasks.json in the project directory."""
        from onecode.agent.cdh_loader import CdhProjectLoader
        cdh_dir = CdhProjectLoader.find_cdh_dir(self._project_dir)
        if cdh_dir is None:
            return
        try:
            tm_data = self._task_manager.to_dict()
            CdhProjectLoader.save_tasks(cdh_dir, tm_data)
        except Exception as e:
            logger.warning("Failed to save tasks to .cdh: %s", e)

    def load_tasks_from_project(self) -> None:
        """Restore tasks/todos from .cdh/tasks.json."""
        from onecode.agent.cdh_loader import CdhProjectLoader
        cdh_dir = CdhProjectLoader.find_cdh_dir(self._project_dir)
        if cdh_dir is None:
            return
        try:
            data = CdhProjectLoader.load_tasks(cdh_dir)
            if data and (data.get("tasks") or data.get("todos")):
                self._task_manager = TaskManager.from_dict(
                    data, on_change=self._on_task_change
                )
        except Exception as e:
            logger.warning("Failed to load tasks from .cdh: %s", e)

    def get_session(self) -> Optional[AgentSession]:
        return self._session