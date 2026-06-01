from __future__ import annotations

import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import AsyncIterator, Optional

from dataclasses import dataclass
from typing import Callable

from cdha.agent.context import ContextManager
from cdha.models.provider import ContentBlockType, ProviderRegistry

from cdha.agent.session import AgentSession
from cdha.models.messages import StreamEvent

logger = logging.getLogger("cdha.agent.engine")


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

THINKING_RE = re.compile(
    r'<thinking>(.*?)</thinking>',
    re.DOTALL,
)


_TASK_STATUSES = {"pending", "in_progress", "completed"}


class TaskManager:
    """V2 task manager with dependency tracking (Clawd-Code style).

    Tasks have: id, subject, description, status, owner, blocks, blockedBy, metadata, output.
    Supports dependency tracking for multi-agent coordination.
    """

    def __init__(self):
        self._tasks: dict[str, dict] = {}  # id -> task dict
        self._todos: list[dict] = []
        self._plan: list[str] = []
        self._id_counter = 0

    def _next_id(self) -> str:
        return uuid.uuid4().hex[:12]

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
        return task

    def get_task(self, task_id: str) -> dict | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[dict]:
        """List all tasks sorted by id."""
        return sorted(self._tasks.values(), key=lambda t: t["id"])

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

    # ── Todo Management (unchanged API) ──

    def add_todo(self, text: str) -> str:
        tid = self._next_id()
        self._todos.append({"text": text, "done": False, "id": tid})
        return tid

    def complete_todo(self, todo_id: str) -> bool:
        for t in self._todos:
            if t["id"] == todo_id:
                t["done"] = True
                return True
        return False

    def remove_todo(self, todo_id: str) -> bool:
        before = len(self._todos)
        self._todos = [t for t in self._todos if t["id"] != todo_id]
        return len(self._todos) < before

    def list_todos(self) -> list[dict]:
        return self._todos

    def clear_todos(self) -> None:
        self._todos = []

    def set_plan(self, plan: list[str]) -> None:
        self._plan = plan

    def get_plan(self) -> list[str]:
        return self._plan


class AgentEngine:
    def __init__(self, app, project_dir: Path | None = None):
        from cdha.agent.tools.file_ops import ToolFactory, Permission
        from cdha.agent.agents.types import BuildAgent
        from cdha.lifecycle.manager import LifecycleManager
        from cdha.agent.hooks import HookManager
        from cdha.agent.permissions import PermissionChecker, create_safe_permission_set
        from cdha.skills.loader import SkillLoader
        from cdha.mcp.manager import MCPManager
        from cdha.agent.tools.cron_tools import CronScheduler
        from cdha.agent.tools.lsp_tools import LSPTool
        from cdha.agent.tools.config_tool import ConfigReadTool, ConfigWriteTool
        from cdha.agent.tools.communication_tools import SendMessageTool
        self.app = app
        self._project_dir = (project_dir or Path.cwd()).resolve()
        self.context = ContextManager()
        self.file_ops = ToolFactory.create_file_ops(self._project_dir)
        self.shell = ToolFactory.create_shell(self._project_dir, Permission.ALLOW)
        self.current_agent: AgentConfig = BuildAgent()
        self.iterations = 0
        self.total_tokens = 0
        self._skills_loaded = False
        self._pipeline = LifecycleManager()
        self._session: Optional[AgentSession] = None
        self._hooks = HookManager()
        self._permissions = PermissionChecker(create_safe_permission_set())
        self._task_manager = TaskManager()
        self._project_config: dict = {}
        self._harness_mode = False
        self._project_context_loaded = False
        self._pending_approval: dict | None = None  # {tool_call, result_key}
        self._last_user_msg: str | None = None  # Last SendMessage visible to user

        # Clawd-Code subsystems
        self._skill_loader = SkillLoader(
            workspace_skills_dir=Path(__file__).parent.parent.parent / "skills"
        )
        self._mcp = MCPManager()
        self._cron_scheduler = CronScheduler()
        self._lsp_tool = LSPTool()
        app_config = getattr(app, 'config', None)
        self._config_tool_read = ConfigReadTool(app_config) if app_config else None
        self._config_tool_write = ConfigWriteTool(app_config) if app_config else None

        # Tool registry (Clawd-Code pattern)
        self._tool_registry = self._build_tool_registry()
        self._send_message_tool = SendMessageTool()

        # Per-turn usage tracking (Clawd-Code style)
        self._turn_usages: list[dict[str, int]] = []

        # Event callbacks
        self.on_event: ToolEventHandler | None = None
        self.on_text_chunk: Callable[[str], None] | None = None

    def _build_tool_registry(self) -> ToolRegistry:
        from cdha.agent.tools.registry import ToolRegistry
        from cdha.agent.tools.file_tools import ReadTool, WriteTool, EditTool, InsertTool, UndoEditTool, GlobTool, GrepTool, ListTool
        from cdha.agent.tools.bash_tool import BashTool
        from cdha.agent.tools.web_tools import WebFetchTool, WebSearchTool
        from cdha.agent.tools.communication_tools import SendMessageTool, AskUserTool, ToolSearchTool
        from cdha.agent.tools.task_tools import (TaskCreateTool, TaskGetTool, TaskListTool, TaskUpdateTool,
            TaskOutputTool, TaskStopTool, TodoCreateTool, TodoListTool, TodoCompleteTool)
        from cdha.agent.tools.agent_tools import AgentTool, TaskTool
        from cdha.agent.tools.skill_tools import SkillTool
        from cdha.agent.tools.mcp_tools import MCPTool as MCPToolTool, MCPResourcesTool
        from cdha.agent.tools.cron_tools import CronCreateTool, CronListTool, CronRemoveTool
        from cdha.agent.tools.git_tools import WorktreeTool
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
        registry.register(AgentTool(registry))
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
        registry.register(WorktreeTool())

        # Config tools (Clawd-Code pattern)
        if self._config_tool_read:
            registry.register(self._config_tool_read)
        if self._config_tool_write:
            registry.register(self._config_tool_write)
        return registry

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

    @property
    def _workspace(self) -> Path:
        return self._project_dir

    def _detect_harness_mode(self) -> bool:
        """Detect if any harness projects exist in workspace."""
        projects_dir = self._workspace / "projects"
        if projects_dir.exists():
            for d in projects_dir.iterdir():
                if d.is_dir() and (d / ".harness").exists():
                    return True
        return False

    def _load_project_config(self, project_name: str) -> dict:
        """Load project config into memory."""
        base = self._workspace / "projects" / project_name / ".harness"
        config_path = base / "config.json"
        if config_path.exists():
            try:
                self._project_config = json.loads(config_path.read_text(encoding="utf-8"))
                return self._project_config
            except Exception:
                pass
        state_path = base / "state.json"
        if state_path.exists():
            try:
                return json.loads(state_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _auto_init_harness(self) -> str:
        """Auto-initialize harness mode if project detected but not initialized."""
        if self._detect_harness_mode():
            self._harness_mode = True
            return ""
        ws = self._workspace
        projects_dir = ws / "projects"
        if projects_dir.exists() and any(projects_dir.iterdir()):
            self._harness_mode = True
            # Projects exist but none is set as current — user should switch
            return "Projects exist. Use `/harness switch <name>` to select one."
        has_code = any(ws.glob("*.json")) or any(ws.glob("*.py")) or any(ws.glob("*.js"))
        if has_code:
            self._harness_mode = True
            return "Project detected. Run `/harness init <name> --platform <mp|web|oa|hybrid>` to initialize harness mode."
        return ""

    def set_agent(self, agent_type: str) -> None:
        from cdha.agent.agents.types import create_agent, PLAN_INSTRUCTIONS, TOOL_DESCRIPTIONS
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

        if agent_type in ("plan", "solo"):
            system_parts.append(PLAN_INSTRUCTIONS)

        if self._harness_mode:
            system_parts.append(
                "\n## Harness Mode Active\n"
                "You are in harness development mode. Follow the pipeline:\n"
                "1. **Init**: Project scaffold, cloud environment config\n"
                "2. **Spec**: EARS requirements, validate with spec guide\n"
                "3. **Design**: UI components, API contracts, data models\n"
                "4. **Coding**: TDD cycle (RED → GREEN → REFACTOR)\n"
                "5. **Testing**: Generate test cases, verify coverage ≥80%\n"
                "6. **Deploy**: Deploy to cloud, verify all components\n"
                "Use `/harness status` to check current phase.\n"
            )

        system_parts.append(TOOL_DESCRIPTIONS)

        self.context.add_system("\n".join(system_parts))

    def get_available_tools(self) -> str:
        from cdha.agent.agents.types import TOOL_DESCRIPTIONS
        return TOOL_DESCRIPTIONS

    def _load_skills(self) -> None:
        if self._skills_loaded:
            return
        self._skills_loaded = True

        for skill in self._skill_loader.get_enabled():
            self.context.add_system(skill.content)

        # Also load harness skill if applicable
        from cdha.agent.harness_skill import HarnessSkill
        harness_content = HarnessSkill.load_skill_for_project(
            self._workspace,
            getattr(self.app, "current_project", None) or "",
        )
        if harness_content:
            self.context.add_system(harness_content)

    def _inject_project_context(self, project_name: str) -> None:
        from cdha.lifecycle.manager import LifecycleManager
        if not project_name:
            self._auto_init_harness()
            return
        if self._project_context_loaded:
            return

        self._project_context_loaded = True
        self._harness_mode = True
        self._pipeline = LifecycleManager(project_name, workspace=self._workspace)
        self._project_config = self._load_project_config(project_name)

        pipeline_info = self._pipeline.get_pipeline_summary()
        self.context.add_system(f"\n## Development Pipeline\n{pipeline_info}\n")

        info = self._pipeline._config
        state = self._pipeline._state

        context_parts = [
            f"Project: {project_name}",
            f"Platform: {info.get('platform', 'unknown')}",
            f"Phase: {state.get('phase', 'init')}",
        ]

        env_id = info.get("cloudbase", {}).get("envId", "")
        if env_id:
            context_parts.append(f"TCB EnvId: {env_id}")

        agents_md_path = Path.cwd() / "AGENTS.md"
        if agents_md_path.exists():
            try:
                content = agents_md_path.read_text(encoding="utf-8")
                context_parts.append(f"\n--- AGENTS.md ---\n{content[:2000]}")
            except Exception:
                pass

        self.context.add_system("\n".join(context_parts))

    def get_current_phase(self) -> str:
        return self._pipeline.current_phase

    def get_phase_info(self, phase: str) -> dict:
        return self._pipeline.get_phase_info(phase)

    def can_advance_phase(self) -> bool:
        next_phase = self._pipeline.get_next_phase()
        if not next_phase:
            return False
        return self._pipeline.can_advance_to(next_phase)

    async def chat(self, user_input: str) -> str:
        self._load_skills()

        project_name = getattr(self.app, "current_project", None) or ""
        if project_name:
            self._inject_project_context(project_name)

        self.context.add_user(user_input)

        if self.context.should_compact():
            self.context.compact()

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
        from cdha.models.messages import get_tool_category
        return get_tool_category(name).value

    async def _execute_tool(self, tool_call: dict) -> dict:
        from cdha.agent.tools.registry import ToolCall as RegistryToolCall
        from cdha.agent.tools.permissions import ToolPermissionContext
        from cdha.agent.agents.types import AgentPermission
        name = tool_call["name"]
        tid = tool_call["id"]
        inp = tool_call["input"]
        category = self._tool_category(name)
        base = {"tool_use_id": tid, "is_error": False, "category": category}
        try:
            # Apply agent-level permission checks for sensitive tools
            if name == "Read":
                if self.current_agent.permission_read == AgentPermission.DENY:
                    return {**base, "content": "Read denied", "is_error": True}
            elif name in ("Write", "Edit", "Insert", "UndoEdit"):
                if self.current_agent.permission_edit == AgentPermission.DENY:
                    return {**base, "content": json.dumps({"success": False, "error": "Edit denied"}), "is_error": True}
                if self.current_agent.permission_edit == AgentPermission.ASK:
                    return {**base, "content": json.dumps({"success": False, "error": "Edit requires approval", "requires_approval": True}), "is_error": True}
            elif name == "Bash":
                if self.current_agent.permission_bash == AgentPermission.DENY:
                    return {**base, "content": json.dumps({"success": False, "error": "Bash denied"}), "is_error": True}
                if self.current_agent.permission_bash == AgentPermission.ASK:
                    return {**base, "content": json.dumps({"success": False, "error": "Bash requires approval", "requires_approval": True}), "is_error": True}
            elif name in ("WebFetch",):
                if self.current_agent.permission_webfetch == AgentPermission.DENY:
                    return {**base, "content": "WebFetch denied", "is_error": True}
            elif name in ("WebSearch",):
                if self.current_agent.permission_websearch == AgentPermission.DENY:
                    return {**base, "content": "WebSearch denied", "is_error": True}
            elif name in ("Task", "Agent"):
                if self.current_agent.permission_task == AgentPermission.DENY:
                    return {**base, "content": json.dumps({"success": False, "error": "Task denied"}), "is_error": True}

            # Dispatch via ToolRegistry with permission context (Clawd-Code pattern)
            call = RegistryToolCall(name=name, input=inp, tool_use_id=tid)
            perm_ctx = ToolPermissionContext.from_iterables(
                workspace_root=str(self._workspace),
            )
            result = self._tool_registry.dispatch(call, permission_context=perm_ctx)

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

    async def chat_stream(self, user_input: str) -> AsyncIterator[StreamEvent | str]:
        self._load_skills()
        logger.info(f"chat_stream() called with user_input='{user_input[:100]}...'")

        project_name = getattr(self.app, "current_project", None) or ""
        if project_name:
            was_context_loaded = self._project_context_loaded
            self._inject_project_context(project_name)
            if not was_context_loaded:
                current_phase = self._pipeline.current_phase if self._pipeline else "init"
                phase_info = {
                    "init": "项目初始化 - 搭建项目骨架",
                    "spec": "需求规格 - 编写 EARS 需求文档",
                    "design": "设计阶段 - UI/API/数据模型设计",
                    "coding": "编码阶段 - TDD 循环开发",
                    "testing": "测试阶段 - 生成测试用例，覆盖率≥80%",
                    "deploy": "部署阶段 - 部署到云端并验证",
                    "done": "已完成",
                }
                yield StreamEvent.text_delta(
                    f"\n📋 项目: {project_name}\n📍 当前阶段: {current_phase} "
                    f"({phase_info.get(current_phase, current_phase)})\n继续开发中...\n\n"
                )
        else:
            init_msg = self._auto_init_harness()
            if init_msg:
                logger.info(f"Harness auto-init: {init_msg}")
                yield StreamEvent.text_delta(f"\n{init_msg}\n\n")

        self.context.add_user(user_input)

        if self.context.should_compact():
            self.context.compact()

        provider_name = self.app.current_provider
        model_name = self.app.current_model
        logger.info(f"Using provider='{provider_name}', model='{model_name}'")

        provider_cls = ProviderRegistry.get(provider_name)
        if not provider_cls:
            error_msg = f"Provider '{provider_name}' not available."
            logger.error(error_msg)
            yield StreamEvent.error(error_msg)
            return

        config = self.app.config.providers.get(provider_name)
        if config is None:
            error_msg = f"Provider '{provider_name}' not configured."
            logger.error(error_msg)
            yield StreamEvent.error(error_msg)
            return

        logger.info(f"Creating provider instance: {provider_cls.__name__}")
        provider = provider_cls(
            api_key=config.api_key or "",
            endpoint=config.endpoint or None,
        )

        # Reset per-turn usage tracking
        self._turn_usages = []

        # ── Agent loop (Clawd-Code style) ──
        is_anthropic = provider.is_anthropic_style()
        max_turns = self.current_agent.max_turns or 10
        for turn in range(max_turns):
            if self.context.should_compact():
                self.context.compact()

            turn_usage: dict[str, int] = {}
            response_text = ""
            tool_uses: list[dict] = []

            try:
                context_messages = self.context.get_context()
                logger.info(f"Calling provider.chat_stream_response (turn {turn+1})")
                chat_response = await provider.chat_stream_response(
                    context_messages,
                    model=model_name,
                    on_text_chunk=None,
                )
                response_text = chat_response.content
                tool_uses = chat_response.tool_uses
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
                    if model_response.usage:
                        turn_usage = model_response.usage
                except Exception as e:
                    logger.exception(f"Error during chat() fallback turn {turn+1}: {e}")
                    yield StreamEvent.error(str(e))
                    break

            # Track usage
            self._turn_usages.append(turn_usage)
            if turn_usage:
                self.total_tokens += turn_usage.get("total_tokens", 0)

            # Extract thinking blocks from response
            thinking_blocks = []
            clean_text = response_text
            for match in THINKING_RE.finditer(response_text):
                thinking_blocks.append(match.group(1))
            if thinking_blocks:
                clean_text = THINKING_RE.sub('', response_text).strip()
                for tb in thinking_blocks:
                    yield StreamEvent.text_delta(f"\n```thinking\n{tb}\n```\n")

            # Add assistant response to context with proper content blocks
            if tool_uses:
                assistant_blocks: list = [{"type": "text", "text": clean_text}] if clean_text else []
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
                result = await self._execute_tool(tu)
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

                # Detect ASK permission denial
                requires_approval = False
                try:
                    parsed = json.loads(result_str) if result_str else {}
                    requires_approval = parsed.get("requires_approval", False)
                except (json.JSONDecodeError, ValueError):
                    pass

                if requires_approval and tu["name"] in ("Write", "Edit", "Bash"):
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
                    from cdha.models.messages import ToolCategory as MsgToolCategory
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

        usage_summary = ", ".join(
            f"turn {i+1}: {u.get('total_tokens', '?')} tokens"
            for i, u in enumerate(self._turn_usages) if u
        )
        logger.info(f"Chat stream complete after {self.iterations} turn(s). Usage: [{usage_summary}]")

    def has_pending_approval(self) -> bool:
        """Check if there's a pending approval request from ASK permission."""
        return self._pending_approval is not None

    async def resolve_approval(self, approved: bool) -> dict | None:
        """Execute the pending action if approved, or return denial.

        Returns the tool result dict, or None if no pending approval.
        """
        if not self._pending_approval:
            return None
        
        tc = self._pending_approval["tool_call"]
        self._pending_approval = None
        
        if not approved:
            return {
                "tool_use_id": tc["id"],
                "content": json.dumps({"success": False, "error": "User denied the operation"}),
                "is_error": True,
                "category": tc.get("category", "unknown"),
            }
        
        # Re-execute with bypassed permission (user approved)
        saved_edit = self.current_agent.permission_edit
        saved_bash = self.current_agent.permission_bash
        try:
            if tc["name"] in ("Write", "Edit"):
                self.current_agent.permission_edit = AgentPermission.ALLOW
            elif tc["name"] == "Bash":
                self.current_agent.permission_bash = AgentPermission.ALLOW
            return await self._execute_tool(tc)
        finally:
            self.current_agent.permission_edit = saved_edit
            self.current_agent.permission_bash = saved_bash

    def reset(self):
        self.context.reset()
        self.iterations = 0
        self.total_tokens = 0
        self._turn_usages = []
        self._skills_loaded = False
        self._project_context_loaded = False
        self._skill_loader.invalidate_cache()

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
        from cdha.agent.tools.web_tools import webfetch
        return webfetch(url, prompt)

    def web_search(self, query: str, num_results: int = 5) -> str:
        if self.current_agent.permission_websearch == AgentPermission.DENY:
            return "WebSearch denied"
        from cdha.agent.tools.web_tools import websearch
        return websearch(query, num_results)

    async def _spawn_subagent_async(self, agent_type: str, prompt: str) -> str:
        """Spawn a sub-agent with streaming-like output.
        
        Uses chat_stream to get structured output that the ChatPanel 
        can parse for professional rendering.
        """
        import asyncio
        sub_engine = AgentEngine(self.app)
        sub_engine.set_agent(agent_type)
        try:
            # Accumulate full result for parent context
            parts = []
            async for chunk in sub_engine.chat_stream(prompt):
                if isinstance(chunk, StreamEvent):
                    # Extract text from stream events for sub-agent result
                    parts.append(chunk.text)
                else:
                    parts.append(chunk)
            result = "".join(parts)
            # Format as structured output (DeepSeek-TUI style contract)
            formatted = self._format_subagent_output(agent_type, prompt, result)
            return formatted
        except Exception as e:
            logger.exception(f"Subagent error: {e}")
            return f"SUMMARY:\nSub-agent failed with error: {e}\n\nCHANGES:\nNone.\n\nEVIDENCE:\nNone.\n\nRISKS:\nNone.\n\nBLOCKERS:\n{e}"
    
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

    def save_session(self) -> None:
        if self._session:
            self._session.messages = self.context.to_session_format()
            self._session.save()

    def load_session(self, session_id: str) -> bool:
        session = AgentSession(session_id)
        if session.load():
            self._session = session
            self.context.load_from_session(session.messages)
            return True
        return False

    def advance_pipeline(self) -> Optional[str]:
        return self._pipeline.advance_phase()

    def get_session(self) -> Optional[AgentSession]:
        return self._session