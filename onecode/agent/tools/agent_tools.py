from __future__ import annotations

from typing import Any

from onecode.agent.tools.protocol import ToolResult
from onecode.agent.tools.registry import Tool, ToolRegistry, ToolSpec


class AgentTool(Tool):
    def __init__(self, registry: ToolRegistry, permission_checker=None):
        self._registry = registry
        self._permission_checker = permission_checker

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="Agent",
            description="Execute a sequence of tool calls as a single atomic agent step.",
            input_schema={
                "type": "object",
                "properties": {
                    "calls": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Tool name"},
                                "input": {"type": "object", "description": "Tool input arguments"},
                            },
                            "required": ["name", "input"],
                        },
                    },
                    "stop_on_error": {
                        "type": "boolean",
                        "description": "Stop execution on first error",
                    },
                },
                "required": ["calls"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        calls = tool_input.get("calls", [])
        stop_on_error = bool(tool_input.get("stop_on_error", True))
        if not isinstance(calls, list):
            return ToolResult(name="Agent", output={"error": "calls must be an array"}, is_error=True)
        results = []
        any_error = False
        for idx, call in enumerate(calls):
            if not isinstance(call, dict):
                return ToolResult(name="Agent", output={"error": f"calls[{idx}] must be an object"}, is_error=True)
            sub_name = call.get("name", "")
            if sub_name == "Agent":
                results.append({"name": sub_name, "is_error": True, "output": "Agent tool cannot be nested"})
                any_error = True
                if stop_on_error:
                    break
                continue
            sub_input = call.get("input", {})
            if self._permission_checker:
                denied = self._permission_checker(sub_name, sub_input)
                if denied:
                    results.append({"name": sub_name, "is_error": True, "output": denied})
                    any_error = True
                    if stop_on_error:
                        break
                    continue
            from onecode.agent.tools.protocol import ToolCall
            sub_result = self._registry.dispatch(ToolCall(name=sub_name, input=sub_input, tool_use_id=f"agent_{idx}"))
            sub_error = sub_result.is_error
            results.append({"name": sub_name, "is_error": sub_error, "output": sub_result.output})
            any_error = any_error or sub_error
            if sub_error and stop_on_error:
                break
        return ToolResult(name="Agent", output={"results": results}, is_error=any_error)



class TaskTool(Tool):
    VALID_AGENT_TYPES: tuple[str, ...] = (
        "general", "explore", "scout",
        "build", "plan", "solo",
    )

    def __init__(self, spawn_fn):
        self._spawn = spawn_fn

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="Spawn",
            description="Delegate a subtask to a specialized subagent. Use for complex multi-step work or work that benefits from an isolated context.",
            input_schema={
                "type": "object",
                "properties": {
                    "agent_type": {
                        "type": "string",
                        "enum": list(self.VALID_AGENT_TYPES),
                        "description": "general (implementation) | explore (code search) | scout (research) | build (full dev) | plan (analysis) | solo (autonomous). Default: general. Choose based on subtask nature.",
                    },
                    "prompt": {"type": "string", "description": "Detailed task description for the subagent. Include context, goals, and expected output format."},
                },
                "required": ["prompt"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        agent_type = tool_input.get("agent_type", "general")
        prompt = tool_input.get("prompt", "")
        if agent_type not in self.VALID_AGENT_TYPES:
            return ToolResult(
                name="Spawn",
                output={
                    "error": (
                        f"Unknown agent_type '{agent_type}'. "
                        f"Valid types: {', '.join(self.VALID_AGENT_TYPES)}"
                    ),
                },
                is_error=True,
            )
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._spawn(agent_type, prompt), loop
                )
                result = future.result(timeout=300)
            else:
                result = asyncio.run(self._spawn(agent_type, prompt))
        except Exception as e:
            return ToolResult(name="Spawn", output={"error": str(e)}, is_error=True)
        return ToolResult(name="Spawn", output=str(result))

