from __future__ import annotations

from typing import Any, Optional

from cdh.agent.tools.protocol import ToolResult
from cdh.agent.tools.registry import ToolSpec
from cdh.agent.tools.web_tools import webfetch, websearch


class WebFetchTool:
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="WebFetch",
            description="Fetch a URL and extract information.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "prompt": {"type": "string", "description": "What to extract from the page"},
                },
                "required": ["url"],
            },
            is_read_only=True,
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        url = tool_input.get("url", "")
        prompt = tool_input.get("prompt")
        content = webfetch(url, prompt)
        is_error = str(content).startswith("Error:")
        return ToolResult(name="WebFetch", output=str(content), is_error=is_error)


class WebSearchTool:
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="WebSearch",
            description="Search the web and return results.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "num_results": {"type": "integer", "description": "Number of results", "default": 5},
                },
                "required": ["query"],
            },
            is_read_only=True,
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        query = tool_input.get("query", "")
        num_results = tool_input.get("num_results", 5)
        content = websearch(query, num_results)
        is_error = "Error" in str(content) and str(content).startswith("Error")
        return ToolResult(name="WebSearch", output=str(content), is_error=is_error)
