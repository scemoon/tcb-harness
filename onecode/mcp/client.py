from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("onecode.mcp")

_READLINE_TIMEOUT = 30.0

# asyncio.StreamReader default limit is 64KB; MCP responses (e.g. a big
# tools/list with dozens of schemas) routinely exceed that, which would
# crash the read loop with LimitOverrunError. Use a generous limit.
_STREAM_LIMIT = 64 * 1024 * 1024


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
    timeout: float = 30.0
    cwd: Optional[str] = None
    _process: Optional[subprocess.Popen] = None
    _reader: Optional[asyncio.StreamReader] = None
    _writer_transport: Any = None
    _request_id: int = 0
    _pending: dict = field(default_factory=dict)
    _tools: list = field(default_factory=list)
    _resources: list = field(default_factory=list)
    _read_task: Optional[asyncio.Task] = None
    _stderr_task: Optional[asyncio.Task] = None
    _initialized: bool = False

    async def start(self) -> bool:
        try:
            self._process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, **self.env} if self.env else None,
                cwd=self.cwd,
            )
            loop = asyncio.get_event_loop()

            self._reader = asyncio.StreamReader(limit=_STREAM_LIMIT)
            protocol = asyncio.StreamReaderProtocol(self._reader)
            await loop.connect_read_pipe(
                lambda: protocol,
                self._process.stdout,
            )
            self._writer_transport, _ = await loop.connect_write_pipe(
                lambda: asyncio.StreamReaderProtocol(asyncio.StreamReader()),
                self._process.stdin,
            )

            self._read_task = asyncio.create_task(self._read_loop())
            self._stderr_task = asyncio.create_task(self._drain_stderr())
            await self._send_init()
            return True
        except Exception as e:
            logger.error(f"MCP start failed: {e}")
            self._cleanup_process()
            return False

    def _cleanup_process(self) -> None:
        """Terminate a spawned subprocess without touching asyncio state."""
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

    async def _drain_stderr(self) -> None:
        """Drain the subprocess stderr pipe so it never blocks the child."""
        if self._process is None or self._process.stderr is None:
            return
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader(limit=_STREAM_LIMIT)
        protocol = asyncio.StreamReaderProtocol(reader)
        try:
            transport, _ = await loop.connect_read_pipe(lambda: protocol, self._process.stderr)
        except Exception as e:
            logger.debug("MCP %s: stderr pipe unavailable: %s", self.name, e)
            return
        try:
            while self._process and self._process.poll() is None:
                line = await reader.readline()
                if not line:
                    break
                logger.debug("MCP %s stderr: %s", self.name, line.decode("utf-8", errors="replace").rstrip())
        except (asyncio.CancelledError, Exception):
            pass

    async def _read_loop(self) -> None:
        try:
            while self._process and self._process.poll() is None:
                if self._reader is None:
                    await asyncio.sleep(0.1)
                    continue
                try:
                    line = await asyncio.wait_for(
                        self._reader.readline(),
                        timeout=_READLINE_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    logger.debug("MCP %s: readline timed out, checking liveness", self.name)
                    if self._process.poll() is not None:
                        break
                    continue
                except asyncio.LimitOverrunError:
                    logger.warning("MCP %s: oversized line, discarding chunk", self.name)
                    try:
                        await self._reader.read(2 * 1024 * 1024)
                    except Exception:
                        pass
                    continue
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
                        future = self._pending.pop(req_id, None)
                        if future is not None and not future.done():
                            future.set_result(msg)
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
            self._initialized = True
            self._send_notification("notifications/initialized")
            server_caps = result["result"].get("capabilities", {})
            if server_caps.get("tools"):
                await self.list_tools()
            if server_caps.get("resources"):
                await self.list_resources()

    def _send_notification(self, method: str) -> None:
        if not self._writer_transport:
            logger.warning("MCP %s: cannot send notification '%s', transport not ready", self.name, method)
            return
        msg = json.dumps({"jsonrpc": "2.0", "method": method})
        self._writer_transport.write((msg + "\n").encode())

    async def _send_request(self, method: str, params: dict) -> Any:
        if not self._writer_transport:
            logger.warning("MCP %s: cannot send request '%s', transport not ready", self.name, method)
            return None
        self._request_id += 1
        req_id = self._request_id
        msg = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        self._writer_transport.write((msg + "\n").encode())

        future = asyncio.Future()
        self._pending[str(req_id)] = future

        try:
            result = await asyncio.wait_for(future, timeout=self.timeout)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(str(req_id), None)
            return None
        except asyncio.CancelledError:
            self._pending.pop(str(req_id), None)
            raise

    async def list_tools(self) -> list[MCPTool]:
        result = await self._send_request("tools/list", {})
        if result and "result" in result:
            tools_data = (result["result"] or {}).get("tools", [])
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
            resources_data = (result["result"] or {}).get("resources", [])
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

    async def read_resource(self, uri: str) -> Any:
        result = await self._send_request("resources/read", {"uri": uri})
        if result and "result" in result:
            return result["result"]
        return None

    def cancel_all(self) -> None:
        """Cancel all pending requests — releases callers blocked on _send_request."""
        for req_id, future in list(self._pending.items()):
            if not future.done():
                future.cancel()
        self._pending.clear()

    async def stop(self) -> None:
        self.cancel_all()
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except (asyncio.CancelledError, Exception):
                pass
            self._read_task = None
        if self._stderr_task:
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except (asyncio.CancelledError, Exception):
                pass
            self._stderr_task = None
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
            self._process = None

    def stop_sync(self) -> None:
        """Best-effort synchronous teardown for contexts without an event loop."""
        self.cancel_all()
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def is_initialized(self) -> bool:
        return self._initialized

    def get_tools(self) -> list[MCPTool]:
        return self._tools

    def get_resources(self) -> list[MCPResource]:
        return self._resources
