from __future__ import annotations

from typing import Any, Callable

from onecode.agent.tools.protocol import ToolResult
from onecode.agent.tools.registry import Tool, ToolSpec
from onecode.mcp.manager import MCPManager


class MCPTool(Tool):
    """Call a tool from a connected MCP server (Clawd-Code pattern)."""

    def __init__(self, mcp_manager: MCPManager):
        self._mcp = mcp_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="MCPTool",
            description="Call a tool on an MCP server. Requires an active MCP connection.",
            input_schema={
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "MCP server name"},
                    "tool": {"type": "string", "description": "Tool name on the MCP server"},
                    "arguments": {"type": "object", "description": "Tool arguments"},
                },
                "required": ["server", "tool"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        import asyncio
        server = tool_input.get("server", "")
        tool_name = tool_input.get("tool", "")
        args = tool_input.get("arguments", {})
        if not self._mcp.is_connected(server):
            return ToolResult(
                name="MCPTool",
                output={"error": f"MCP server '{server}' is not connected"},
                is_error=True,
            )
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._mcp.call_tool(server, tool_name, args), loop
                )
                result = future.result(timeout=60)
            else:
                result = asyncio.run(self._mcp.call_tool(server, tool_name, args))
            return ToolResult(name="MCPTool", output=result or {"error": "no response"})
        except Exception as e:
            return ToolResult(
                name="MCPTool",
                output={"error": str(e)},
                is_error=True,
            )

    async def run_async(
        self, tool_input: dict[str, Any],
        cancel_check: Callable[[], bool] | None = None,
    ) -> ToolResult:
        server = tool_input.get("server", "")
        tool_name = tool_input.get("tool", "")
        args = tool_input.get("arguments", {})
        if not self._mcp.is_connected(server):
            return ToolResult(
                name="MCPTool",
                output={"error": f"MCP server '{server}' is not connected"},
                is_error=True,
            )
        try:
            result = await self._mcp.call_tool(server, tool_name, args)
            return ToolResult(name="MCPTool", output=result or {"error": "no response"})
        except Exception as e:
            return ToolResult(
                name="MCPTool",
                output={"error": str(e)},
                is_error=True,
            )



class MCPResourcesTool(Tool):
    """Access resources from a connected MCP server."""

    def __init__(self, mcp_manager: MCPManager):
        self._mcp = mcp_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="MCPResources",
            description="List or read resources from a connected MCP server. Provides access to external data sources.",
            input_schema={
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "MCP server name"},
                    "action": {
                        "type": "string",
                        "enum": ["list", "read"],
                        "description": "List available resources or read a specific resource",
                    },
                    "uri": {
                        "type": "string",
                        "description": "Resource URI to read (required for action='read')",
                    },
                },
                "required": ["server", "action"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        import asyncio
        server = tool_input.get("server", "")
        action = tool_input.get("action", "list")
        uri = tool_input.get("uri", "")
        if not self._mcp.is_connected(server):
            return ToolResult(
                name="MCPResources",
                output={"error": f"MCP server '{server}' is not connected"},
                is_error=True,
            )
        client = self._mcp.get_client(server)
        if not client:
            return ToolResult(name="MCPResources", output={"error": "client not found"}, is_error=True)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                if action == "list":
                    future = asyncio.run_coroutine_threadsafe(
                        client.list_resources(), loop
                    )
                else:
                    future = asyncio.run_coroutine_threadsafe(
                        client.read_resource(uri), loop
                    )
                result = future.result(timeout=60)
            else:
                if action == "list":
                    result = asyncio.run(client.list_resources())
                else:
                    result = asyncio.run(client.read_resource(uri))
            return ToolResult(name="MCPResources", output=result or {"error": "no response"})
        except Exception as e:
            return ToolResult(
                name="MCPResources",
                output={"error": str(e)},
                is_error=True,
            )

    async def run_async(
        self, tool_input: dict[str, Any],
        cancel_check: Callable[[], bool] | None = None,
    ) -> ToolResult:
        server = tool_input.get("server", "")
        action = tool_input.get("action", "list")
        uri = tool_input.get("uri", "")
        if not self._mcp.is_connected(server):
            return ToolResult(
                name="MCPResources",
                output={"error": f"MCP server '{server}' is not connected"},
                is_error=True,
            )
        client = self._mcp.get_client(server)
        if not client:
            return ToolResult(name="MCPResources", output={"error": "client not found"}, is_error=True)
        try:
            if action == "list":
                result = await client.list_resources()
            else:
                result = await client.read_resource(uri)
            return ToolResult(name="MCPResources", output=result or {"error": "no response"})
        except Exception as e:
            return ToolResult(
                name="MCPResources",
                output={"error": str(e)},
                is_error=True,
            )

