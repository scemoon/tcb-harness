from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import AsyncIterator, Optional

from cdh.agent.context import ContextManager, ContextConfig
from cdh.models.provider import Message as ProviderMessage, ProviderRegistry
from cdh.agent.tools.file_ops import FileOps, ShellTool, Permission, ToolFactory
from cdh.agent.pipeline import PipelineManager, get_pipeline_for_agent
from cdh.agent.agents.types import (
    AgentConfig, BuildAgent, PlanAgent, create_agent,
    get_system_prompt, TOOL_DESCRIPTIONS, BUILT_IN_AGENTS, AgentPermission, PLAN_INSTRUCTIONS
)

from cdh.agent.session import AgentSession
from cdh.agent.hooks import HookManager, HookContext, HookResult
from cdh.agent.permissions import PermissionChecker, PermissionSet, create_safe_permission_set
from cdh.agent.tools.schemas import TOOLS_SCHEMA

logger = logging.getLogger("cdh.agent.engine")

TOOL_CALL_RE = re.compile(
    r'<tool_call\s+name=["\']([^"\']+)["\']\s+id=["\']([^"\']+)["\']>(.*?)</tool_call>',
    re.DOTALL,
)


class TaskManager:
    def __init__(self):
        self._tasks: list[dict] = []
        self._todos: list[dict] = []
        self._plan: list[str] = []
        self._next_id = 1

    def add_task(self, name: str, status: str = "todo") -> int:
        tid = self._next_id
        self._next_id += 1
        self._tasks.append({"name": name, "status": status, "id": tid})
        return tid

    def update_task(self, task_id: int, status: str) -> bool:
        for t in self._tasks:
            if t["id"] == task_id:
                t["status"] = status
                return True
        return False

    def list_tasks(self) -> list[dict]:
        return self._tasks

    def clear_tasks(self) -> None:
        self._tasks = []

    def add_todo(self, text: str) -> int:
        tid = self._next_id
        self._next_id += 1
        self._todos.append({"text": text, "done": False, "id": tid})
        return tid

    def complete_todo(self, todo_id: int) -> bool:
        for t in self._todos:
            if t["id"] == todo_id:
                t["done"] = True
                return True
        return False

    def remove_todo(self, todo_id: int) -> bool:
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
    def __init__(self, app):
        self.app = app
        self.context = ContextManager()
        ws = Path(app.config.default_workspace).expanduser() if app.config.default_workspace else Path.cwd()
        self.file_ops = ToolFactory.create_file_ops(ws)
        self.shell = ToolFactory.create_shell(ws, Permission.ALLOW)
        self.current_agent: AgentConfig = BuildAgent()
        self.iterations = 0
        self.total_tokens = 0
        self._skills_loaded = False
        self._pipeline = PipelineManager()
        self._session: Optional[AgentSession] = None
        self._hooks = HookManager()
        self._permissions = PermissionChecker(create_safe_permission_set())
        self._task_manager = TaskManager()
        self._project_config: dict = {}
        self._harness_mode = False

    def _detect_harness_mode(self) -> bool:
        """Detect if current workspace is a harness project."""
        ws = Path(self.app.config.default_workspace).expanduser() if self.app.config.default_workspace else Path.cwd()
        harness_dir = ws / ".harness"
        if harness_dir.exists() and (harness_dir / "config.json").exists():
            return True
        projects_dir = ws / "projects"
        if projects_dir.exists():
            for d in projects_dir.iterdir():
                if d.is_dir() and (d / ".harness").exists():
                    return True
        return False

    def _load_project_config(self, project_name: str) -> dict:
        """Load project config into memory."""
        ws = Path(self.app.config.default_workspace).expanduser() if self.app.config.default_workspace else Path.cwd()
        config_path = ws / "projects" / project_name / ".harness" / "config.json"
        if config_path.exists():
            try:
                self._project_config = json.loads(config_path.read_text(encoding="utf-8"))
                return self._project_config
            except Exception:
                pass
        state_path = ws / "projects" / project_name / ".harness" / "state.json"
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
        ws = Path(self.app.config.default_workspace).expanduser() if self.app.config.default_workspace else Path.cwd()
        has_code = any(ws.glob("*.json")) or any(ws.glob("*.py")) or any(ws.glob("*.js"))
        if has_code:
            self._harness_mode = True
            return "Project detected. Run `/harness init <name> --platform <mp|web|oa|hybrid>` to initialize harness mode."
        return ""

    def set_agent(self, agent_type: str) -> None:
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
        return TOOL_DESCRIPTIONS

    def _load_skills(self) -> None:
        if self._skills_loaded:
            return
        self._skills_loaded = True

        from cdh.agent.skills import load_all_enabled_skills

        for name, content in load_all_enabled_skills():
            self.context.add_system(content)

    def _inject_project_context(self, project_name: str) -> None:
        if not project_name:
            self._auto_init_harness()
            return

        self._harness_mode = True
        self._pipeline = PipelineManager(project_name)
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

    async def _execute_tool(self, tool_call: dict) -> dict:
        name = tool_call["name"]
        tid = tool_call["id"]
        inp = tool_call["input"]
        try:
            if name == "Read":
                path = inp.get("path", "")
                offset = inp.get("offset", 0)
                limit = inp.get("limit", 0)
                content = self.read_file(path, offset, limit)
                return {"tool_use_id": tid, "content": str(content), "is_error": False}
            elif name == "Write":
                path = inp.get("path", "")
                result = self.write_file(path, inp.get("content", ""))
                warning = self._validate_edit(path)
                output = json.dumps(result)
                if warning:
                    output += f"\n{warning}"
                return {"tool_use_id": tid, "content": output, "is_error": not result.get("success", True)}
            elif name == "Edit":
                path = inp.get("path", "")
                result = self.edit_file(path, inp.get("old_string", ""), inp.get("new_string", ""))
                warning = self._validate_edit(path)
                output = json.dumps(result)
                if warning:
                    output += f"\n{warning}"
                return {"tool_use_id": tid, "content": output, "is_error": not result.get("success", True)}
            elif name == "Glob":
                result = self.glob_files(inp.get("pattern", ""))
                return {"tool_use_id": tid, "content": str(result), "is_error": False}
            elif name == "Grep":
                result = self.grep_files(inp.get("pattern", ""), inp.get("include"))
                return {"tool_use_id": tid, "content": str(result), "is_error": False}
            elif name == "List":
                result = self.list_dir(inp.get("path", "."))
                return {"tool_use_id": tid, "content": str(result), "is_error": False}
            elif name == "Bash":
                result = self.exec_shell(inp.get("command", ""), inp.get("timeout", 60))
                return {"tool_use_id": tid, "content": str(result), "is_error": False}
            elif name == "WebFetch":
                result = self.web_fetch(inp.get("url", ""), inp.get("prompt"))
                return {"tool_use_id": tid, "content": str(result), "is_error": False}
            elif name == "WebSearch":
                result = self.web_search(inp.get("query", ""), inp.get("num_results", 5))
                return {"tool_use_id": tid, "content": str(result), "is_error": False}
            elif name == "Task":
                result = await self._spawn_subagent_async(inp.get("agent_type", "general"), inp.get("prompt", ""))
                return {"tool_use_id": tid, "content": str(result), "is_error": False}
            elif name == "TaskCreate":
                title = inp.get("title", "")
                description = inp.get("description", "")
                task_id = self._task_manager.add_task(title)
                return {"tool_use_id": tid, "content": f"Task created: id={task_id}, title={title}", "is_error": False}
            elif name == "TaskList":
                tasks = self._task_manager.list_tasks()
                if not tasks:
                    return {"tool_use_id": tid, "content": "No tasks.", "is_error": False}
                lines = [f"  {t['id']}. [{t['status']}] {t['name']}" for t in tasks]
                return {"tool_use_id": tid, "content": "\n".join(lines), "is_error": False}
            elif name == "TaskUpdate":
                task_id = inp.get("id", 0)
                status = inp.get("status", "todo")
                ok = self._task_manager.update_task(task_id, status)
                return {"tool_use_id": tid, "content": f"Task {task_id} updated to {status}" if ok else f"Task {task_id} not found", "is_error": not ok}
            elif name == "TodoCreate":
                text = inp.get("text", "")
                todo_id = self._task_manager.add_todo(text)
                return {"tool_use_id": tid, "content": f"Todo created: id={todo_id}, text={text}", "is_error": False}
            elif name == "TodoList":
                todos = self._task_manager.list_todos()
                if not todos:
                    return {"tool_use_id": tid, "content": "No todos.", "is_error": False}
                lines = [f"  {t['id']}. [{'done' if t['done'] else 'todo'}] {t['text']}" for t in todos]
                return {"tool_use_id": tid, "content": "\n".join(lines), "is_error": False}
            elif name == "TodoComplete":
                todo_id = inp.get("id", 0)
                ok = self._task_manager.complete_todo(todo_id)
                return {"tool_use_id": tid, "content": f"Todo {todo_id} completed" if ok else f"Todo {todo_id} not found", "is_error": not ok}
            else:
                return {"tool_use_id": tid, "content": f"Unknown tool: {name}", "is_error": True}
        except Exception as e:
            logger.exception(f"Tool execution error: {e}")
            return {"tool_use_id": tid, "content": f"Error: {e}", "is_error": True}

    async def chat_stream(self, user_input: str) -> AsyncIterator[str]:
        self._load_skills()
        logger.info(f"chat_stream() called with user_input='{user_input[:100]}...'")

        project_name = getattr(self.app, "current_project", None) or ""
        if project_name:
            self._inject_project_context(project_name)
        else:
            init_msg = self._auto_init_harness()
            if init_msg:
                logger.info(f"Harness auto-init: {init_msg}")

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
            yield error_msg
            return

        config = self.app.config.providers.get(provider_name)
        if config is None:
            error_msg = f"Provider '{provider_name}' not configured."
            logger.error(error_msg)
            yield error_msg
            return

        logger.info(f"Creating provider instance: {provider_cls.__name__}")
        provider = provider_cls(
            api_key=config.api_key or "",
            endpoint=config.endpoint or None,
        )

        max_turns = self.current_agent.max_turns or 10
        for turn in range(max_turns):
            if self.context.should_compact():
                self.context.compact()

            full_response = []
            chunk_count = 0
            try:
                context_messages = self.context.get_context()
                async for chunk in provider.chat_stream(
                    context_messages,
                    model=model_name,
                    tools=TOOLS_SCHEMA,
                ):
                    chunk_count += 1
                    full_response.append(chunk)
                    yield chunk

                logger.info(f"Turn {turn+1}: {chunk_count} chunks, {len(''.join(full_response))} chars")
            except Exception as e:
                logger.exception(f"Error during chat_stream turn {turn+1}: {e}")
                yield f"\n[Error: {e}]"
                break

            response_text = "".join(full_response)
            self.context.add_assistant(response_text)
            self.iterations += 1

            # Try native tool calls (from function calling API) first
            get_tc = getattr(provider, 'get_stream_tool_calls', None)
            native_tool_calls = get_tc() if get_tc else []
            if native_tool_calls:
                tool_calls = []
                for nt in native_tool_calls:
                    try:
                        inp = json.loads(nt.get("arguments", "{}"))
                    except (json.JSONDecodeError, TypeError):
                        inp = {"raw": nt.get("arguments", "")}
                    tool_calls.append({
                        "name": nt.get("name", ""),
                        "id": nt.get("id", ""),
                        "input": inp,
                    })
            else:
                # Fall back to XML parsing
                tool_calls = self._parse_tool_calls(response_text)

            if not tool_calls:
                break

            yield "\n"
            for tc in tool_calls:
                logger.info(f"Executing tool: {tc['name']} (id={tc['id']})")
                yield f'<tool_result tool_use_id="{tc["id"]}">\n'
                result = await self._execute_tool(tc)
                result_str = str(result.get("content", ""))
                if result.get("is_error"):
                    yield f"Error: {result_str}"
                else:
                    yield result_str
                yield "\n</tool_result>\n"
                self.context.add_tool_result(
                    tc["id"],
                    result_str,
                    result.get("is_error", False),
                )

        logger.info(f"Chat stream complete after {self.iterations} turn(s)")

    def reset(self):
        self.context.reset()
        self.iterations = 0
        self.total_tokens = 0
        self._skills_loaded = False

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
        from cdh.agent.tools.web_tools import webfetch
        return webfetch(url, prompt)

    def web_search(self, query: str, num_results: int = 5) -> str:
        if self.current_agent.permission_websearch == AgentPermission.DENY:
            return "WebSearch denied"
        from cdh.agent.tools.web_tools import websearch
        return websearch(query, num_results)

    async def _spawn_subagent_async(self, agent_type: str, prompt: str) -> str:
        sub_engine = AgentEngine(self.app)
        sub_engine.set_agent(agent_type)
        try:
            result = await sub_engine.chat(prompt)
            return str(result)
        except Exception as e:
            logger.exception(f"Subagent error: {e}")
            return f"Error: {e}"

    def spawn_subagent(self, agent_type: str, prompt: str) -> dict:
        if self.current_agent.permission_task == AgentPermission.DENY:
            return {"success": False, "error": "Subagent denied"}
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                result = loop.run_until_complete(
                    self._spawn_subagent_async(agent_type, prompt)
                )
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


from cdh.agent.agents.types import AgentPermission