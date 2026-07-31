from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any, Optional

import httpx
import yaml

from onecode.config import ONECODE_DIR
from onecode.mcp.client import MCPClient, MCPTool

logger = logging.getLogger("onecode.mcp")

# Default config for MCP connections
_MCP_TIMEOUT = 60
_MCP_HEARTBEAT_INTERVAL = 15
_MCP_RECONNECT_BASE_DELAY = 1.0
_MCP_RECONNECT_MAX_DELAY = 30.0
_MCP_RECONNECT_JITTER = 0.5


class MCPSSEClient:
    """SSE-based MCP client with persistent connection and auto-reconnect.

    A single background loop owns the SSE connection and automatically
    reconnects with exponential back-off when the connection drops.
    """

    def __init__(
        self,
        name: str,
        url: str,
        timeout: float = _MCP_TIMEOUT,
        heartbeat_interval: float = _MCP_HEARTBEAT_INTERVAL,
    ):
        self.name = name
        self.url = url
        self._timeout = timeout
        self._heartbeat_interval = heartbeat_interval
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))
        self._session_id: Optional[str] = None
        self._tools: list[MCPTool] = []
        self._running = False
        self._sse_task: Optional[asyncio.Task] = None
        self._connected = asyncio.Event()
        self._reconnect_delay = _MCP_RECONNECT_BASE_DELAY

    async def start(self) -> bool:
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(self._timeout))
        self._sse_task = asyncio.create_task(self._run_sse_loop())
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=self._timeout)
            return True
        except (asyncio.TimeoutError, Exception):
            logger.error(f"MCP SSE start timed out for '{self.name}'")
            self._running = False
            return False

    async def _run_sse_loop(self) -> None:
        """Background task: own the SSE connection, reconnect on drop."""
        self._running = True
        while self._running:
            resp = None
            try:
                resp = await self._client.send(
                    httpx.Request("GET", self.url),
                    stream=True,
                )
                resp.raise_for_status()
                self._reconnect_delay = _MCP_RECONNECT_BASE_DELAY

                has_tools = False
                async for line in resp.aiter_lines():
                    if not self._running:
                        return
                    if not line.startswith("data: "):
                        continue
                    try:
                        data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(data, dict):
                        continue
                    if "sessionId" in data:
                        self._session_id = data["sessionId"]
                        if not self._connected.is_set():
                            self._connected.set()
                            await self._list_tools()
                            has_tools = True
                logger.info("MCP SSE stream ended for '%s', reconnecting...", self.name)
            except asyncio.CancelledError:
                return
            except Exception as e:
                if self._running:
                    logger.warning("MCP SSE error for '%s': %s", self.name, e)
            finally:
                if resp is not None:
                    await resp.aclose()
                if not self._connected.is_set():
                    self._connected.set()

            if not self._running:
                return
            await self._backoff_wait()

    async def _backoff_wait(self) -> None:
        delay = self._reconnect_delay + random.random() * _MCP_RECONNECT_JITTER * self._reconnect_delay
        if delay > _MCP_RECONNECT_MAX_DELAY:
            delay = _MCP_RECONNECT_MAX_DELAY
        self._reconnect_delay = min(self._reconnect_delay * 2, _MCP_RECONNECT_MAX_DELAY)
        logger.info("MCP SSE reconnect in %.1fs for '%s'", delay, self.name)
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise

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
        if self._sse_task:
            self._sse_task.cancel()
            try:
                await self._sse_task
            except (asyncio.CancelledError, Exception):
                pass
            self._sse_task = None
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

    def __init__(
        self,
        name: str,
        url: str,
        headers: Optional[dict[str, str]] = None,
        timeout: float = _MCP_TIMEOUT,
    ):
        self.name = name
        self.url = url
        self._headers = headers or {}
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))
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
    def __init__(
        self,
        timeout: float = _MCP_TIMEOUT,
        heartbeat_interval: float = _MCP_HEARTBEAT_INTERVAL,
    ):
        self._timeout = timeout
        self._heartbeat_interval = heartbeat_interval
        self.config_dir = ONECODE_DIR / "mcps"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / "mcps.yaml"
        self._data: dict = {}
        self._clients: dict[str, Any] = {}
        self._reconnect_tasks: dict[str, asyncio.Task] = {}
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
        self._cancel_reconnect(name)
        if name in self._clients:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._clients[name].stop())
            except Exception as e:
                logger.warning("Failed to stop MCP client '%s': %s", name, e)
            del self._clients[name]
        self._save()

    async def connect(self, name: str, auto_reconnect: bool = True) -> bool:
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
                timeout=self._timeout,
            )
        elif transport == "sse":
            client = MCPSSEClient(
                name=name,
                url=cfg["url"],
                timeout=self._timeout,
                heartbeat_interval=self._heartbeat_interval,
            )
        elif transport == "http":
            client = MCPHTTPClient(
                name=name,
                url=cfg["url"],
                headers=cfg.get("headers", {}),
                timeout=self._timeout,
            )
        else:
            logger.warning(f"Unknown MCP transport: {transport}")
            return False

        success = await client.start()
        if success:
            self._clients[name] = client
        elif auto_reconnect:
            self._schedule_reconnect(name)
        return success

    async def connect_all(self) -> list[str]:
        connected = []
        for name in list(self._data.keys()):
            if await self.connect(name):
                connected.append(name)
        return connected

    def _schedule_reconnect(self, name: str) -> None:
        """Schedule a reconnection task for a failed MCP connection."""
        if name in self._reconnect_tasks:
            return
        self._reconnect_tasks[name] = asyncio.create_task(self._reconnect_loop(name))

    def _cancel_reconnect(self, name: str) -> None:
        task = self._reconnect_tasks.pop(name, None)
        if task and not task.done():
            task.cancel()

    async def _reconnect_loop(self, name: str) -> None:
        delay = _MCP_RECONNECT_BASE_DELAY
        cfg = self._data.get(name, {})
        if not cfg.get("enabled"):
            self._reconnect_tasks.pop(name, None)
            return
        while self._data.get(name, {}).get("enabled"):
            try:
                await asyncio.sleep(delay)
                if name in self._clients and self._clients[name].is_running():
                    self._reconnect_tasks.pop(name, None)
                    return
                logger.info("Auto-reconnecting MCP '%s'...", name)
                success = await self.connect(name, auto_reconnect=False)
                if success:
                    logger.info("MCP '%s' reconnected successfully", name)
                    self._reconnect_tasks.pop(name, None)
                    return
                delay = min(delay * 2, _MCP_RECONNECT_MAX_DELAY)
                delay += random.random() * _MCP_RECONNECT_JITTER * delay
            except asyncio.CancelledError:
                self._reconnect_tasks.pop(name, None)
                return
            except Exception as e:
                logger.warning("MCP reconnect failed for '%s': %s", name, e)
        self._reconnect_tasks.pop(name, None)

    def cancel_all(self) -> None:
        """Cancel all in-flight MCP requests across all clients."""
        for client in self._clients.values():
            try:
                if hasattr(client, 'cancel_all'):
                    client.cancel_all()
            except Exception as e:
                logger.warning("MCP cancel_all failed for %s: %s", getattr(client, 'name', '?'), e)

    async def disconnect(self, name: str) -> None:
        self._cancel_reconnect(name)
        if name in self._clients:
            await self._clients[name].stop()
            del self._clients[name]

    async def disconnect_all(self) -> None:
        for name in list(self._reconnect_tasks.keys()):
            self._cancel_reconnect(name)
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
