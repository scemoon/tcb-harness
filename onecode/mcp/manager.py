from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import random
from typing import Any, Optional

import httpx

from onecode.mcp.client import MCPClient, MCPTool
from onecode.mcp.config import (
    MCPServerConfig,
    MCPConfigFile,
    resolve_mapping,
)

logger = logging.getLogger("onecode.mcp")

# Default config for MCP connections
_MCP_TIMEOUT = 60
_MCP_HEARTBEAT_INTERVAL = 15
_MCP_RECONNECT_BASE_DELAY = 1.0
_MCP_RECONNECT_MAX_DELAY = 30.0
_MCP_RECONNECT_JITTER = 0.5
_MCP_RECONNECT_MAX_ATTEMPTS = 10


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
        self._stream_connected = False
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
                        self._stream_connected = True
                        if not self._connected.is_set():
                            self._connected.set()
                            await self._list_tools()
                logger.info("MCP SSE stream ended for '%s', reconnecting...", self.name)
            except asyncio.CancelledError:
                return
            except Exception as e:
                if self._running:
                    logger.warning("MCP SSE error for '%s': %s", self.name, e)
            finally:
                if resp is not None:
                    await resp.aclose()
                self._stream_connected = False
                if not self._connected.is_set() and self._session_id:
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
            tools_data = (data.get("result") or {}).get("tools", [])
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
        return self._running and self._stream_connected

    def is_initialized(self) -> bool:
        return self._session_id is not None

    def get_tools(self) -> list[MCPTool]:
        return self._tools


class MCPHTTPClient:
    """HTTP-based MCP client (Streamable HTTP transport).

    Sends JSON-RPC requests as HTTP POST and receives JSON-RPC responses.
    Used by services like TCB CloudBase hosted mode. Per the streamable
    HTTP spec, the client must POST ``initialize`` first, then attach the
    ``Mcp-Session-Id`` returned by the server to subsequent requests.
    """

    _MCP_PROTOCOL_VERSION = "2024-11-05"
    _PROTOCOL_HEADER = "mcp-protocol-version"
    _SESSION_HEADER = "mcp-session-id"

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
        self._session_id: Optional[str] = None
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))
        self._tools: list[MCPTool] = []
        self._running = False

    async def start(self) -> bool:
        try:
            init_result = await self._post_json({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": self._MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "cdh", "version": "1.0.0"},
                },
            })
            if "result" not in init_result:
                logger.error("MCP HTTP %s: initialize rejected: %s", self.name, str(init_result)[:200])
                return False
            server_caps = init_result.get("result", {}).get("capabilities", {})
            await self._post_json({"jsonrpc": "2.0", "method": "notifications/initialized"})
            if server_caps.get("tools"):
                await self.list_tools()
            self._running = True
            return True
        except Exception as e:
            logger.error(f"MCP HTTP start failed: {e}")
            return False

    async def _post_json(self, payload: dict, extra_headers: Optional[dict[str, str]] = None) -> Any:
        """POST a JSON-RPC payload, tolerating both JSON and SSE responses."""
        headers = {
            **self._headers,
            self._PROTOCOL_HEADER: self._MCP_PROTOCOL_VERSION,
        }
        if self._session_id:
            headers[self._SESSION_HEADER] = self._session_id
        if extra_headers:
            headers.update(extra_headers)
        resp = await self._client.post(
            self.url,
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        session_id = resp.headers.get(self._SESSION_HEADER)
        if session_id:
            self._session_id = session_id
        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return await self._read_sse(resp, payload.get("id"))
        return resp.json()

    async def _read_sse(self, resp, request_id: Any) -> Any:
        """Read an SSE stream, returning the event matching our request id.

        Guards against servers that keep the stream open with unrelated
        events (progress / logging notifications) by bounding the number
        of lines read.
        """
        data: Any = {}
        lines_read = 0
        async for line in resp.aiter_lines():
            lines_read += 1
            if lines_read > 10000:
                break
            if not line.startswith("data:"):
                continue
            try:
                data = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("id") == request_id:
                break
        return data

    async def list_tools(self) -> list[MCPTool]:
        data = await self._post_json({"jsonrpc": "2.0", "method": "tools/list", "id": 1})
        tools_data = (data.get("result") or {}).get("tools", [])
        self._tools = [
            MCPTool(name=t["name"], description=t.get("description", ""), input_schema=t.get("inputSchema", {}))
            for t in tools_data
        ]
        return self._tools

    async def call_tool(self, name: str, args: dict) -> Any:
        try:
            data = await self._post_json(
                {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": name, "arguments": args}, "id": 2}
            )
            return data.get("result")
        except Exception as e:
            return {"error": str(e)}

    async def stop(self):
        self._running = False
        await self._client.aclose()

    def is_running(self) -> bool:
        return self._running

    def is_initialized(self) -> bool:
        return self._session_id is not None

    def get_tools(self) -> list[MCPTool]:
        return self._tools


class MCPManager:
    def __init__(
        self,
        timeout: float = _MCP_TIMEOUT,
        heartbeat_interval: float = _MCP_HEARTBEAT_INTERVAL,
        *,
        config_path: Optional[Any] = None,
        legacy_config_path: Optional[Any] = None,
    ):
        self._timeout = timeout
        self._heartbeat_interval = heartbeat_interval
        self._config_file = MCPConfigFile(
            path=config_path,
            legacy_path=legacy_config_path,
        )
        self.config_dir = self._config_file.path.parent
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self._config_file.path
        self._servers: dict[str, MCPServerConfig] = {}
        self._data: dict[str, dict[str, Any]] = {}  # legacy-shaped in-memory cache
        self._clients: dict[str, Any] = {}
        self._reconnect_tasks: dict[str, asyncio.Task] = {}
        self._load()

    def _load(self) -> None:
        """Load servers from JSON (with YAML fallback) and populate the cache."""
        self._servers = self._config_file.load()
        self._data = {name: cfg.to_legacy() for name, cfg in self._servers.items()}

    def _refresh_from_cache(self) -> None:
        """Sync ``_data`` from ``_servers`` after in-place mutation."""
        self._data = {name: cfg.to_legacy() for name, cfg in self._servers.items()}

    def add(self, name: str, url: str, transport: str = "sse"):
        cfg = MCPServerConfig(
            name=name,
            type="remote",
            url=url,
            enabled=True,
        )
        if transport == "http":
            cfg.headers = {}
        self._servers[name] = cfg
        self._refresh_from_cache()
        self._save()

    def add_stdio(self, name: str, command: str, args: Optional[list[str]] = None, env: Optional[dict[str, str]] = None):
        cmd_list = [command] + list(args or []) if args else [command]
        cfg = MCPServerConfig(
            name=name,
            type="local",
            command=cmd_list,
            environment=dict(env) if env else {},
            enabled=True,
        )
        self._servers[name] = cfg
        self._refresh_from_cache()
        self._save()

    def add_http(self, name: str, url: str, headers: Optional[dict[str, str]] = None):
        cfg = MCPServerConfig(
            name=name,
            type="remote",
            url=url,
            headers=dict(headers) if headers else {},
            enabled=True,
        )
        self._servers[name] = cfg
        self._refresh_from_cache()
        self._save()

    def add_server(self, name: str, cfg: MCPServerConfig) -> None:
        """Add or replace an MCP server from a typed config object."""
        cfg.name = name
        self._servers[name] = cfg
        self._refresh_from_cache()
        self._save()

    def list(self) -> list[dict]:
        return [
            {"name": name, **cfg.to_legacy()} for name, cfg in self._servers.items()
        ]

    def get(self, name: str) -> Optional[dict]:
        """Get an MCP server config by name (legacy shape)."""
        cfg = self._servers.get(name)
        return cfg.to_legacy() if cfg else None

    def get_server(self, name: str) -> Optional[MCPServerConfig]:
        """Get the typed MCPServerConfig for a server."""
        return self._servers.get(name)

    def all_servers(self) -> dict[str, MCPServerConfig]:
        return dict(self._servers)

    def enable(self, name: str, enabled: bool = True) -> Optional[str]:
        """Enable or disable an MCP server.

        Returns error message or None on success.
        """
        cfg = self._servers.get(name)
        if not cfg:
            return f"MCP server '{name}' not found"
        cfg.enabled = bool(enabled)
        self._refresh_from_cache()
        self._save()
        return None

    def remove(self, name: str):
        self._servers.pop(name, None)
        self._refresh_from_cache()
        self._cancel_reconnect(name)
        if name in self._clients:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._clients[name].stop())
                elif hasattr(self._clients[name], "stop_sync"):
                    self._clients[name].stop_sync()
            except Exception as e:
                logger.warning("Failed to stop MCP client '%s': %s", name, e)
            del self._clients[name]
        self._save()

    def is_globally_disabled(self, name: str) -> bool:
        """Return True if a server matches any ``mcp.disabled`` glob in onecode.config.yaml."""
        try:
            from onecode.config import load_config
            cfg = load_config()
            patterns = list(getattr(cfg.mcp, "disabled", []) or [])
        except Exception:
            patterns = []
        for pat in patterns:
            if fnmatch.fnmatch(name, pat):
                return True
        return False

    async def connect(self, name: str, auto_reconnect: bool = True) -> bool:
        cfg = self._servers.get(name)
        if not cfg:
            return False
        if not cfg.enabled:
            return False
        if self.is_globally_disabled(name):
            logger.info("MCP '%s' is disabled by mcp.disabled glob", name)
            return False

        # Resolve {env:VAR} and {file:...} templates at connect time so
        # changes to the environment (e.g. after `cdh cloudbase init`)
        # are picked up without restarting the agent.
        env = resolve_mapping(cfg.environment or cfg.env)
        headers = resolve_mapping(cfg.headers)

        client: Any = None
        if cfg.type == "local":
            cmd = cfg.command or []
            client = MCPClient(
                name=name,
                command=cmd[0] if cmd else "",
                args=list(cmd[1:]),
                env=env,
                cwd=cfg.cwd,
                timeout=cfg.timeout or self._timeout,
            )
        elif cfg.type == "remote":
            # If headers are configured, prefer the HTTP transport; else SSE.
            if headers:
                client = MCPHTTPClient(
                    name=name,
                    url=cfg.url or "",
                    headers=headers,
                    timeout=cfg.timeout or self._timeout,
                )
            else:
                client = MCPSSEClient(
                    name=name,
                    url=cfg.url or "",
                    timeout=cfg.timeout or self._timeout,
                    heartbeat_interval=self._heartbeat_interval,
                )
        else:
            logger.warning("MCP '%s' has unknown type: %s", name, cfg.type)
            return False

        success = await client.start()
        if success:
            self._clients[name] = client
        else:
            # Avoid leaking the half-started client (e.g. a spawned stdio
            # subprocess) when startup fails.
            try:
                await client.stop()
            except Exception as e:
                logger.warning("MCP client '%s' cleanup after failed start: %s", name, e)
            if auto_reconnect:
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
        failures = 0
        while self._data.get(name, {}).get("enabled"):
            try:
                await asyncio.sleep(delay)
                if name in self._clients and self._clients[name].is_running():
                    self._reconnect_tasks.pop(name, None)
                    return
                if failures >= _MCP_RECONNECT_MAX_ATTEMPTS:
                    logger.warning(
                        "MCP '%s' still unreachable after %d attempts; giving up (re-enable or restart to retry)",
                        name,
                        failures,
                    )
                    self._reconnect_tasks.pop(name, None)
                    return
                logger.info("Auto-reconnecting MCP '%s'...", name)
                success = await self.connect(name, auto_reconnect=False)
                if success:
                    logger.info("MCP '%s' reconnected successfully", name)
                    self._reconnect_tasks.pop(name, None)
                    return
                failures += 1
                delay = min(delay * 2, _MCP_RECONNECT_MAX_DELAY)
                delay += random.random() * _MCP_RECONNECT_JITTER * delay
            except asyncio.CancelledError:
                self._reconnect_tasks.pop(name, None)
                return
            except Exception as e:
                logger.warning("MCP reconnect failed for '%s': %s", name, e)
                failures += 1
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
        if not client or not client.is_running():
            return False
        if hasattr(client, "is_initialized"):
            return client.is_initialized()
        return True

    def _save(self):
        self._config_file.save(self._servers)
