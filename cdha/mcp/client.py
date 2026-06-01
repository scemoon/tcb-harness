from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("cdha.mcp")


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict = field(default_factory=dict)


@dataclass
class MCPResource:
    uri: str
    name: str = ""
    description: str = ""


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
    _resources: list = field(default_factory=list)
    _read_task: Optional[asyncio.Task] = None

    async def start(self) -> bool:
        try:
            self._process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**self.env} if self.env else None,
            )
            loop = asyncio.get_event_loop()
            self._reader, self._writer = await asyncio.open_connection(
                fd=self._process.stdout.fileno(),
                # Use a loop.create_connection approach for pipe-based fd
            )
            # Proper way: create StreamReader/StreamWriter from pipe
            self._reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(self._reader)
            await loop.connect_read_pipe(
                lambda: protocol,
                self._process.stdout,
            )
            self._writer_transport, self._writer_protocol = await loop.connect_write_pipe(
                lambda: asyncio.StreamReaderProtocol(asyncio.StreamReader()),
                self._process.stdin,
            )

            # Start background reader task
            self._read_task = asyncio.create_task(self._read_loop())
            await self._send_init()
            return True
        except Exception as e:
            logger.error(f"MCP start failed: {e}")
            return False

    async def _read_loop(self) -> None:
        """Continuously read JSON-RPC responses from stdout."""
        try:
            while self._process and self._process.poll() is None:
                if self._reader is None:
                    await asyncio.sleep(0.1)
                    continue
                line = await self._reader.readline()
                if not line:
                    await asyncio.sleep(0.05)
                    continue
                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue
                try:
                    msg = json.loads(line_str)
                    req_id = str(msg.get("id", ""))
                    if req_id in self._pending:
                        future = self._pending.pop(req_id)
                        if not future.done():
                            future.set_result(msg)
                    # Handle notifications (no id)
                    if "method" in msg:
                        await self._handle_notification(msg)
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            logger.debug(f"MCP read loop ended: {e}")

    async def _handle_notification(self, msg: dict) -> None:
        method = msg.get("method", "")
        if method == "tools/list_changed":
            await self.list_tools()
        elif method == "resources/list_changed":
            await self.list_resources()

    async def _send_init(self) -> None:
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "cdh", "version": "1.0.0"},
        })
        if result and "result" in result:
            server_caps = result["result"].get("capabilities", {})
            if server_caps.get("tools"):
                await self.list_tools()
            if server_caps.get("resources"):
                await self.list_resources()

    async def _send_request(self, method: str, params: dict) -> Any:
        self._request_id += 1
        req_id = self._request_id
        msg = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        if self._writer_transport:
            self._writer_transport.write((msg + "\n").encode())
        elif self._writer:
            self._writer.write((msg + "\n").encode())
            await self._writer.drain()

        future = asyncio.Future()
        self._pending[str(req_id)] = future

        try:
            result = await asyncio.wait_for(future, timeout=30)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(str(req_id), None)
            return None

    async def list_tools(self) -> list[MCPTool]:
        result = await self._send_request("tools/list", {})
        if result and "result" in result:
            tools_data = result["result"].get("tools", [])
            self._tools = [
                MCPTool(
                    name=t["name"],
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                )
                for t in tools_data
            ]
        return self._tools

    async def list_resources(self) -> list[MCPResource]:
        result = await self._send_request("resources/list", {})
        if result and "result" in result:
            resources_data = result["result"].get("resources", [])
            self._resources = [
                MCPResource(uri=r["uri"], name=r.get("name", ""), description=r.get("description", ""))
                for r in resources_data
            ]
        return self._resources

    async def call_tool(self, name: str, args: dict) -> Any:
        result = await self._send_request("tools/call", {"name": name, "arguments": args})
        if result and "result" in result:
            return result["result"]
        return None

    async def stop(self) -> None:
        if self._read_task:
            self._read_task.cancel()
            self._read_task = None
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def get_tools(self) -> list[MCPTool]:
        return self._tools

    def get_resources(self) -> list[MCPResource]:
        return self._resources
