from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

import httpx
import yaml

from onecode.config import ONECODE_DIR
from onecode.mcp.client import MCPClient, MCPTool

logger = logging.getLogger("onecode.mcp")


class MCPSSEClient:
    """SSE-based MCP client (Clawd-Code pattern)."""

    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url
        self._client = httpx.AsyncClient(timeout=30)
        self._session_id: Optional[str] = None
        self._tools: list[MCPTool] = []
        self._running = False

    async def start(self) -> bool:
        try:
            async with self._client.stream("GET", self.url) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        if isinstance(data, dict) and "sessionId" in data:
                            self._session_id = data["sessionId"]
                            self._running = True
                            break
            if self._running:
                await self._list_tools()
            return self._running
        except Exception as e:
            logger.error(f"MCP SSE start failed: {e}")
            return False

    async def _list_tools(self) -> list[MCPTool]:
        try:
            resp = await self._client.post(
                self.url,
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
            )
            data = resp.json()
            tools_data = data.get("result", {}).get("tools", [])
            self._tools = [
                MCPTool(name=t["name"], description=t.get("description", ""), input_schema=t.get("inputSchema", {}))
                for t in tools_data
            ]
        except Exception as e:
            logger.error("MCP list_tools failed: %s", e)
        return self._tools

    async def call_tool(self, name: str, args: dict) -> Any:
        try:
            resp = await self._client.post(
                self.url,
                json={"jsonrpc": "2.0", "method": "tools/call", "params": {"name": name, "arguments": args}, "id": 2},
            )
            data = resp.json()
            return data.get("result")
        except Exception as e:
            return {"error": str(e)}

    async def stop(self):
        self._running = False
        await self._client.aclose()

    def is_running(self) -> bool:
        return self._running

    def get_tools(self) -> list[MCPTool]:
        return self._tools


class MCPHTTPClient:
    """HTTP-based MCP client (Streamable HTTP transport).

    Sends JSON-RPC requests as HTTP POST and receives JSON-RPC responses.
    Used by services like TCB CloudBase hosted mode.
    """

    def __init__(self, name: str, url: str, headers: Optional[dict[str, str]] = None):
        self.name = name
        self.url = url
        self._headers = headers or {}
        self._client = httpx.AsyncClient(timeout=30)
        self._tools: list[MCPTool] = []
        self._running = False

    async def start(self) -> bool:
        try:
            await self.list_tools()
            self._running = True
            return True
        except Exception as e:
            logger.error(f"MCP HTTP start failed: {e}")
            return False

    async def list_tools(self) -> list[MCPTool]:
        resp = await self._client.post(
            self.url,
            headers=self._headers,
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
        )
        resp.raise_for_status()
        data = resp.json()
        tools_data = data.get("result", {}).get("tools", [])
        self._tools = [
            MCPTool(name=t["name"], description=t.get("description", ""), input_schema=t.get("inputSchema", {}))
            for t in tools_data
        ]
        return self._tools

    async def call_tool(self, name: str, args: dict) -> Any:
        try:
            resp = await self._client.post(
                self.url,
                headers=self._headers,
                json={"jsonrpc": "2.0", "method": "tools/call", "params": {"name": name, "arguments": args}, "id": 2},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("result")
        except Exception as e:
            return {"error": str(e)}

    async def stop(self):
        self._running = False
        await self._client.aclose()

    def is_running(self) -> bool:
        return self._running

    def get_tools(self) -> list[MCPTool]:
        return self._tools


class MCPManager:
    def __init__(self):
        self.config_dir = ONECODE_DIR / "mcps"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / "mcps.yaml"
        self._data: dict = {}
        self._clients: dict[str, Any] = {}
        if self.config_path.exists():
            self._data = yaml.safe_load(self.config_path.read_text()) or {}

    def add(self, name: str, url: str, transport: str = "sse"):
        self._data[name] = {"url": url, "transport": transport, "enabled": True}
        self._save()

    def add_stdio(self, name: str, command: str, args: Optional[list[str]] = None, env: Optional[dict[str, str]] = None):
        entry: dict[str, Any] = {"command": command, "args": args or [], "transport": "stdio", "enabled": True}
        if env:
            entry["env"] = env
        self._data[name] = entry
        self._save()

    def add_http(self, name: str, url: str, headers: Optional[dict[str, str]] = None):
        entry: dict[str, Any] = {"url": url, "transport": "http", "enabled": True}
        if headers:
            entry["headers"] = headers
        self._data[name] = entry
        self._save()

    def list(self) -> list[dict]:
        return [
            {"name": name, **cfg} for name, cfg in self._data.items()
        ]

    def get(self, name: str) -> Optional[dict]:
        """Get an MCP server config by name."""
        return self._data.get(name)

    def enable(self, name: str, enabled: bool = True) -> Optional[str]:
        """Enable or disable an MCP server.

        Returns error message or None on success.
        """
        if name not in self._data:
            return f"MCP server '{name}' not found"
        self._data[name]["enabled"] = enabled
        self._save()
        return None

    def remove(self, name: str):
        self._data.pop(name, None)
        if name in self._clients:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._clients[name].stop())
            except Exception as e:
                logger.warning("Failed to stop MCP client '%s': %s", name, e)
            del self._clients[name]
        self._save()

    async def connect(self, name: str) -> bool:
        cfg = self._data.get(name, {})
        if not cfg.get("enabled"):
            return False
        transport = cfg.get("transport", "sse")

        client: Any = None
        if transport == "stdio":
            client = MCPClient(
                name=name,
                command=cfg["command"],
                args=cfg.get("args", []),
                env=cfg.get("env", {}),
            )
        elif transport == "sse":
            client = MCPSSEClient(name=name, url=cfg["url"])
        elif transport == "http":
            client = MCPHTTPClient(name=name, url=cfg["url"], headers=cfg.get("headers", {}))
        else:
            logger.warning(f"Unknown MCP transport: {transport}")
            return False

        success = await client.start()
        if success:
            self._clients[name] = client
        return success

    async def connect_all(self) -> list[str]:
        connected = []
        for name in list(self._data.keys()):
            if await self.connect(name):
                connected.append(name)
        return connected

    async def disconnect(self, name: str) -> None:
        if name in self._clients:
            await self._clients[name].stop()
            del self._clients[name]

    async def disconnect_all(self) -> None:
        for name in list(self._clients.keys()):
            await self.disconnect(name)

    async def list_tools(self, name: str) -> list[MCPTool]:
        if name in self._clients:
            return await self._clients[name].list_tools()
        return []

    async def call_tool(self, name: str, tool_name: str, args: dict) -> Any:
        if name in self._clients:
            return await self._clients[name].call_tool(tool_name, args)
        return None

    def get_client(self, name: str) -> Optional[Any]:
        return self._clients.get(name)

    def is_connected(self, name: str) -> bool:
        client = self._clients.get(name)
        return client.is_running() if client else False

    def cancel_all(self) -> None:
        """Cancel all in-flight MCP requests across all clients."""
        for client in self._clients.values():
            try:
                if hasattr(client, 'cancel_all'):
                    client.cancel_all()
            except Exception as e:
                logger.warning("MCP cancel_all failed for %s: %s", getattr(client, 'name', '?'), e)

    def _save(self):
        self.config_path.write_text(yaml.dump(self._data, default_flow_style=False))
