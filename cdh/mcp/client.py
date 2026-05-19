from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict = field(default_factory=dict)


@dataclass
class MCPClient:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    _process: Optional[subprocess.Popen] = None
    _reader: Optional[asyncio.StreamReader] = None
    _writer: Optional[asyncio.StreamWriter] = None
    _request_id: int = 0
    _pending: dict = field(default_factory=dict)
    _tools: list = field(default_factory=list)

    async def start(self) -> bool:
        try:
            self._process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self.env,
            )
            self._reader, self._writer = await asyncio.open_connection(
                fd=self._process.stdout.fileno(),
                flow_control=asyncio.StreamReader,
            )
            await self._send_init()
            return True
        except Exception:
            return False

    async def _send_init(self) -> None:
        await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "cdh", "version": "1.0.0"},
        })

    async def _send_request(self, method: str, params: dict) -> Any:
        self._request_id += 1
        req_id = self._request_id
        msg = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        self._writer.write(msg.encode())
        await self._writer.drain()

        future = asyncio.Future()
        self._pending[str(req_id)] = future

        try:
            result = await asyncio.wait_for(future, timeout=30)
            return result
        except Exception:
            return None

    async def list_tools(self) -> list[MCPTool]:
        result = await self._send_request("tools/list", {})
        if result and "result" in result:
            tools = result["result"].get("tools", [])
            self._tools = [MCPTool(name=t["name"], description=t.get("description", ""), input_schema=t.get("inputSchema", {})) for t in tools]
        return self._tools

    async def call_tool(self, name: str, args: dict) -> Any:
        result = await self._send_request("tools/call", {"name": name, "arguments": args})
        if result and "result" in result:
            return result["result"]
        return None

    async def stop(self) -> None:
        if self._process:
            self._process.terminate()
            self._process.wait()
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None