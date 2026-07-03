from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional


class HookEvent(Enum):
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    PRE_MODEL_CALL = "pre_model_call"
    POST_MODEL_CALL = "post_model_call"
    PRE_AGENT_START = "pre_agent_start"
    POST_AGENT_END = "post_agent_end"


@dataclass
class HookContext:
    agent_name: str
    tool_name: str
    args: dict[str, Any]
    session_id: Optional[str] = None
    iteration: int = 0


@dataclass
class HookResult:
    allowed: bool = True
    modified_args: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    data: Any = None


PreToolHook = Callable[[HookContext], HookResult]
PostToolHook = Callable[[HookContext, Any], HookResult]


class HookManager:
    def __init__(self):
        self._pre_tool_hooks: list[PreToolHook] = []
        self._post_tool_hooks: list[PostToolHook] = []
        self._global_hooks: dict[HookEvent, list] = {
            HookEvent.PRE_TOOL_USE: [],
            HookEvent.POST_TOOL_USE: [],
            HookEvent.PRE_MODEL_CALL: [],
            HookEvent.POST_MODEL_CALL: [],
            HookEvent.PRE_AGENT_START: [],
            HookEvent.POST_AGENT_END: [],
        }

    def register_pre_tool(self, hook: PreToolHook) -> None:
        self._pre_tool_hooks.append(hook)
        self._global_hooks[HookEvent.PRE_TOOL_USE].append(hook)

    def register_post_tool(self, hook: PostToolHook) -> None:
        self._post_tool_hooks.append(hook)
        self._global_hooks[HookEvent.POST_TOOL_USE].append(hook)

    def register(self, event: HookEvent, handler: Callable) -> None:
        self._global_hooks[event].append(handler)

    def unregister(self, event: HookEvent, handler: Callable) -> None:
        if handler in self._global_hooks[event]:
            self._global_hooks[event].remove(handler)

    def run_pre_tool(self, ctx: HookContext) -> HookResult:
        for hook in self._pre_tool_hooks:
            result = hook(ctx)
            if not result.allowed:
                return result
            if result.modified_args:
                ctx.args = result.modified_args
        return HookResult(allowed=True)

    def run_post_tool(self, ctx: HookContext, tool_result: Any) -> Any:
        for hook in self._post_tool_hooks:
            result = hook(ctx, tool_result)
            if result.data is not None:
                return result.data
        return tool_result

    def clear(self) -> None:
        self._pre_tool_hooks.clear()
        self._post_tool_hooks.clear()
        for event in self._global_hooks:
            self._global_hooks[event].clear()