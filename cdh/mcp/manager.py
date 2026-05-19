from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

import yaml

from cdh.config import CLOUD_DEV_HARNESS_DIR
from cdh.mcp.client import MCPClient, MCPTool


class MCPManager:
    def __init__(self):
        self.config_dir = CLOUD_DEV_HARNESS_DIR / "mcps"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / "mcps.yaml"
        self._data: dict = {}
        self._clients: dict[str, MCPClient] = {}
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
            asyncio.create_task(self._clients[name].stop())
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
        else:
            return False
        success = await client.start()
        if success:
            self._clients[name] = client
        return success

    async def disconnect(self, name: str) -> None:
        if name in self._clients:
            await self._clients[name].stop()
            del self._clients[name]

    async def list_tools(self, name: str) -> list[MCPTool]:
        if name in self._clients:
            return await self._clients[name].list_tools()
        return []

    async def call_tool(self, name: str, tool_name: str, args: dict) -> Any:
        if name in self._clients:
            return await self._clients[name].call_tool(tool_name, args)
        return None

    def get_client(self, name: str) -> Optional[MCPClient]:
        return self._clients.get(name)

    def is_connected(self, name: str) -> bool:
        client = self._clients.get(name)
        return client.is_running() if client else False

    def _save(self):
        self.config_path.write_text(yaml.dump(self._data, default_flow_style=False))
