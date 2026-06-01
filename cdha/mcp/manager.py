from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml

from cdha.config import CLOUD_DEV_HARNESS_DIR
from cdha.mcp.client import MCPClient, MCPTool

logger = logging.getLogger("cdha.mcp")


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


class MCPManager:
    def __init__(self):
        self.config_dir = CLOUD_DEV_HARNESS_DIR / "mcps"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / "mcps.yaml"
        self._data: dict = {}
        self._clients: dict[str, Any] = {}
        if self.config_path.exists():
            self._data = yaml.safe_load(self.config_path.read_text()) or {}

    def add(self, name: str, url: str, transport: str = "sse"):
        self._data[name] = {"url": url, "transport": transport, "enabled": True}
        self._save()

    def add_stdio(self, name: str, command: str, args: list[str] = None):
        self._data[name] = {"command": command, "args": args or [], "transport": "stdio", "enabled": True}
        self._save()

    def list(self) -> list[dict]:
        return [
            {"name": name, **cfg} for name, cfg in self._data.items()
        ]

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

        if transport == "stdio":
            client = MCPClient(
                name=name,
                command=cfg["command"],
                args=cfg.get("args", []),
            )
        elif transport == "sse":
            client = MCPSSEClient(name=name, url=cfg["url"])
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

    def _save(self):
        self.config_path.write_text(yaml.dump(self._data, default_flow_style=False))
