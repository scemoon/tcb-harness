from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from onecode.agent.tools.errors import ToolInputError, ToolPermissionError
from onecode.agent.tools.protocol import ToolCall, ToolResult
from onecode.agent.tools.schema_validation import validate_json_schema


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Mapping[str, Any]
    aliases: tuple[str, ...] = ()
    is_read_only: bool = False
    is_destructive: bool = False
    max_result_size_chars: int = 20_000


class Tool(ABC):
    @abstractmethod
    def spec(self) -> ToolSpec: ...

    @abstractmethod
    def run(self, tool_input: dict[str, Any]) -> ToolResult: ...

    async def run_async(
        self, tool_input: dict[str, Any],
        cancel_check: Callable[[], bool] | None = None,
    ) -> ToolResult:
        return self.run(tool_input)


class ToolRegistry:
    def __init__(
        self,
        tools: Iterable[Tool] | None = None,
    ) -> None:
        self._tools: list[Tool] = []
        self._by_name: dict[str, Tool] = {}
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

    def make_openai_schemas(self, exclude: set[str] | None = None) -> list[dict]:
        """Build OpenAI-style function schemas for every registered tool.

        When *exclude* is provided, tools whose names appear in it are
        omitted entirely so the LLM never sees (and never attempts) tools
        that the current agent's permissions would deny at runtime.
        """
        exclude = exclude or set()
        schemas = []
        for spec in self.list_specs():
            if spec.name in exclude:
                continue
            schemas.append({
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": dict(spec.input_schema),
                },
            })
        return schemas

    async def dispatch_async(
        self,
        call: ToolCall,
        cancel_check: Callable[[], bool] | None = None,
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
            validate_json_schema(call.input, spec.input_schema, tool_name=call.name)
            result = await tool.run_async(call.input, cancel_check=cancel_check)
            max_chars = spec.max_result_size_chars
            if max_chars > 0 and isinstance(result.output, str) and len(result.output) > max_chars:
                result = ToolResult(
                    name=result.name,
                    output=result.output[:max_chars]
                    + f"\n\n[Output truncated to {max_chars} characters]",
                    is_error=result.is_error,
                    tool_use_id=result.tool_use_id or call.tool_use_id,
                    content_type=result.content_type,
                )
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

    def dispatch(
        self,
        call: ToolCall,
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

            # Schema validation
            validate_json_schema(call.input, spec.input_schema, tool_name=call.name)

            # Execute
            result = tool.run(call.input)

            # Enforce max result size — truncate oversized output so the
            # context window is not flooded by a single tool result.
            max_chars = spec.max_result_size_chars
            if max_chars > 0 and isinstance(result.output, str) and len(result.output) > max_chars:
                result = ToolResult(
                    name=result.name,
                    output=result.output[:max_chars]
                    + f"\n\n[Output truncated to {max_chars} characters]",
                    is_error=result.is_error,
                    tool_use_id=result.tool_use_id or call.tool_use_id,
                    content_type=result.content_type,
                )

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
