from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Protocol

from cdh.agent.tools.errors import ToolInputError, ToolPermissionError
from cdh.agent.tools.permission_handler import (
    InteractivePermissionHandler,
    PermissionDecision,
)
from cdh.agent.tools.permissions import PermissionResult, ToolPermissionContext
from cdh.agent.tools.protocol import ToolCall, ToolResult
from cdh.agent.tools.schema_validation import validate_json_schema


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Mapping[str, Any]
    aliases: tuple[str, ...] = ()
    is_read_only: bool = False
    is_destructive: bool = False
    max_result_size_chars: int = 20_000


class Tool(Protocol):
    def spec(self) -> ToolSpec: ...

    def run(self, tool_input: dict[str, Any]) -> ToolResult: ...

    def check_permissions(
        self,
        tool_input: dict[str, Any],
        permission_context: ToolPermissionContext,
    ) -> PermissionResult:
        """Check if this tool can run with the given input and context.

        Default implementation: allow. Override in tools that need
        path-aware or content-aware permission checks.
        """
        return PermissionResult.ALLOW


PermissionHandler = InteractivePermissionHandler


class ToolRegistry:
    def __init__(
        self,
        tools: Iterable[Tool] | None = None,
        permission_handler: InteractivePermissionHandler | None = None,
    ) -> None:
        self._tools: list[Tool] = []
        self._by_name: dict[str, Tool] = {}
        self._permission_handler = permission_handler or InteractivePermissionHandler()
        if tools:
            for tool in tools:
                self.register(tool)

    def register(self, tool: Tool) -> None:
        spec = tool.spec()
        key = spec.name.lower()
        if key in self._by_name:
            raise ValueError(f"duplicate tool name: {spec.name}")
        self._tools.append(tool)
        self._by_name[key] = tool
        for alias in spec.aliases:
            alias_key = alias.lower()
            if alias_key in self._by_name:
                raise ValueError(f"duplicate tool alias: {alias}")
            self._by_name[alias_key] = tool

    def list_specs(self) -> list[ToolSpec]:
        return [tool.spec() for tool in self._tools]

    def get(self, name: str) -> Tool | None:
        return self._by_name.get(name.lower())

    def dispatch(
        self,
        call: ToolCall,
        permission_context: ToolPermissionContext | None = None,
    ) -> ToolResult:
        tool = self.get(call.name)
        if tool is None:
            return ToolResult(
                name=call.name,
                output={"error": f"unknown tool: {call.name}"},
                is_error=True,
                tool_use_id=call.tool_use_id,
            )
        try:
            spec = tool.spec()

            # 1. Schema validation (Clawd-Code pattern)
            validate_json_schema(call.input, spec.input_schema, tool_name=call.name)

            # 2. Permission context check (Clawd-Code pattern)
            if permission_context is not None and permission_context.blocks_tool(call.name):
                return ToolResult(
                    name=call.name,
                    output={"error": f"tool '{call.name}' is blocked by permission context"},
                    is_error=True,
                    tool_use_id=call.tool_use_id,
                )

            # 3. Tool-level permissions check (Clawd-Code pattern)
            perm_result = tool.check_permissions(call.input, permission_context or ToolPermissionContext())
            if perm_result == PermissionResult.DENY:
                return ToolResult(
                    name=call.name,
                    output={"error": f"tool '{call.name}' denied by permission check"},
                    is_error=True,
                    tool_use_id=call.tool_use_id,
                )
            elif perm_result == PermissionResult.ASK:
                decision = self._permission_handler.handle(
                    call.name,
                    call.input,
                    question=f"Allow {call.name} with input: {str(call.input)[:200]}",
                )
                if decision.result != PermissionResult.ALLOW:
                    return ToolResult(
                        name=call.name,
                        output={"error": f"tool '{call.name}' denied by user: {decision.reason}"},
                        is_error=True,
                        tool_use_id=call.tool_use_id,
                    )

            # 4. Execute
            result = tool.run(call.input)
            if result.tool_use_id is None:
                return ToolResult(
                    name=result.name,
                    output=result.output,
                    is_error=result.is_error,
                    tool_use_id=call.tool_use_id,
                    content_type=result.content_type,
                )
            return result
        except ToolInputError as e:
            return ToolResult(
                name=call.name,
                output={"error": str(e)},
                is_error=True,
                tool_use_id=call.tool_use_id,
            )
        except ToolPermissionError as e:
            return ToolResult(
                name=call.name,
                output={"error": str(e)},
                is_error=True,
                tool_use_id=call.tool_use_id,
            )
        except Exception as e:
            return ToolResult(
                name=call.name,
                output={"error": str(e)},
                is_error=True,
                tool_use_id=call.tool_use_id,
            )
