from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

from onecode.agent.tools.registry import ToolResult, ToolSpec

if TYPE_CHECKING:
    from onecode.codebase import CodebaseEngine


class CodebaseSearchTool:
    def __init__(self, engine_factory: Callable[[], Optional[CodebaseEngine]]):
        self._engine_factory = engine_factory

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="codebase_search",
            description="Search the indexed codebase for code relevant to a query. "
                        "Returns code chunks with file paths and line numbers. "
                        "Use this to find relevant code before making changes.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query describing what you're looking for",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (1-20)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
            is_read_only=True,
        )

    async def run(self, tool_input: dict) -> ToolResult:
        query = tool_input.get("query", "")
        top_k = min(max(int(tool_input.get("top_k", 5)), 1), 20)
        if not query:
            return ToolResult(content="Please provide a search query.")
        try:
            engine = self._engine_factory()
            if engine is None:
                return ToolResult(content="Codebase engine not available. Is it enabled in config?")
            chunks = await engine.retrieve(query, top_k=top_k)
            if not chunks:
                return ToolResult(content="No results found. Try a different query.")
            parts: list[str] = []
            for i, c in enumerate(chunks, 1):
                parts.append(
                    f"[{i}] {c.file_path}:{c.start_line}-{c.end_line}\n"
                    f"```\n{c.content}\n```"
                )
            return ToolResult(content="\n\n".join(parts))
        except Exception as e:
            return ToolResult(content=f"Search failed: {e}", is_error=True)
