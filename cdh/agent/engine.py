from __future__ import annotations

import logging
from pathlib import Path
from typing import AsyncIterator, Optional

from cdh.agent.context import ContextManager, ContextConfig
from cdh.models.provider import Message as ProviderMessage, ProviderRegistry
from cdh.agent.tools.file_ops import FileOps, ShellTool, Permission, ToolFactory
from cdh.agent.pipeline import PipelineManager, get_pipeline_for_agent
from cdh.agent.agents.types import (
    AgentConfig, BuildAgent, PlanAgent, create_agent,
    get_system_prompt, TOOL_DESCRIPTIONS, BUILT_IN_AGENTS, AgentPermission
)

from cdh.agent.session import AgentSession
from cdh.agent.hooks import HookManager, HookContext, HookResult
from cdh.agent.permissions import PermissionChecker, PermissionSet, create_safe_permission_set

logger = logging.getLogger("cdh.agent.engine")


class AgentEngine:
    def __init__(self, app):
        self.app = app
        self.context = ContextManager()
        self.file_ops = ToolFactory.create_file_ops(Path.cwd())
        self.shell = ToolFactory.create_shell(Path.cwd(), Permission.ALLOW)
        self.current_agent: AgentConfig = BuildAgent()
        self.iterations = 0
        self.total_tokens = 0
        self._skills_loaded = False
        self._pipeline = PipelineManager()
        self._session: Optional[AgentSession] = None
        self._hooks = HookManager()
        self._permissions = PermissionChecker(create_safe_permission_set())

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
            return

        self._pipeline = PipelineManager(project_name)

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

    async def chat_stream(self, user_input: str) -> AsyncIterator[str]:
        self._load_skills()
        logger.info(f"chat_stream() called with user_input='{user_input[:100]}...'")

        project_name = getattr(self.app, "current_project", None) or ""
        if project_name:
            self._inject_project_context(project_name)

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
        logger.info(f"Provider config - api_key: {'Yes' if config.api_key else 'No'}, endpoint: {config.endpoint}")

        full_content = []
        chunk_count = 0
        try:
            context_messages = self.context.get_context()
            logger.info(f"Sending {len(context_messages)} messages to provider")
            async for chunk in provider.chat_stream(
                context_messages,
                model=model_name,
            ):
                chunk_count += 1
                full_content.append(chunk)
                yield chunk
                if chunk_count == 1:
                    logger.info(f"First chunk received: '{chunk[:50]}...'")

            logger.info(f"Stream complete. Total chunks: {chunk_count}, total chars: {len(full_content)}")
        except Exception as e:
            logger.exception(f"Error during chat_stream: {e}")
            yield f"Error: {e}"
            return

        self.context.add_assistant("".join(full_content))
        self.iterations += 1

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

    def spawn_subagent(self, agent_type: str, prompt: str) -> dict:
        if self.current_agent.permission_task == AgentPermission.DENY:
            return {"success": False, "error": "Subagent denied"}
        sub_agent = create_agent(agent_type)
        sub_engine = AgentEngine(self.app)
        sub_engine.set_agent(agent_type)
        sub_engine.context.add_user(prompt)

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            sub_engine.chat(prompt)
        )
        return {
            "success": True,
            "agent_type": agent_type,
            "response": result,
            "iterations": sub_engine.iterations,
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

    def get_session(self) -> Optional[AgentSession]:
        return self._session


from cdh.agent.agents.types import AgentPermission