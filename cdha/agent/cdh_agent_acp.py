#!/usr/bin/env python3
"""CDH ACP Adapter - Allows CDH Agent to communicate via ACP protocol.

This adapter runs as a subprocess and translates JSONRPC calls from A2TUI
into CDH AgentEngine calls.
"""

import asyncio
import json
import sys
from pathlib import Path

from cdha.agent.engine import AgentEngine
from cdha.config import load_config
from cdha.models.provider import ProviderRegistry
from cdha.models.registry import ModelRegistry
from cdha.models.messages import StreamEventType

from cdha.models.providers.minimaxi_provider import MiniMaxiProvider
from cdha.models.providers.minimax_provider import MiniMaxProvider
from cdha.models.providers.anthropic_provider import AnthropicProvider
from cdha.models.providers.openai_provider import OpenAIProvider
from cdha.models.providers.deepseek_provider import DeepSeekProvider
from cdha.models.providers.glm_provider import GLMProvider
from cdha.models.providers.ollama_provider import OllamaProvider


class CDHACPAdapter:
    """Adapter that translates ACP protocol to CDH AgentEngine."""

    def __init__(self):
        self.agent = None
        self.session_id = None
        self.tool_calls = {}

    def send_notification(self, method: str, params: dict):
        """Send a JSONRPC notification to A2TUI."""
        notification = {"jsonrpc": "2.0", "method": method, "params": params}
        print(json.dumps(notification), flush=True)

    async def initialize(self, protocol_version: int, client_capabilities: dict, client_info: dict):
        """Handle ACP initialize."""
        return {
            "protocolVersion": 1,
            "agentCapabilities": {
                "loadSession": False,
                "promptCapabilities": {
                    "audio": False,
                    "embeddedContent": False,
                    "image": False,
                },
            },
            "authMethods": [],
            "serverInfo": {
                "name": "cdh-agent",
                "title": "CDH Agent",
                "version": "1.0.0",
            },
        }

    async def session_new(self, cwd: str, mcp_servers: list):
        """Create new session."""
        import os
        from pathlib import Path
        self.session_id = f"cdh-session-{os.getpid()}"
        cfg = load_config()

        ModelRegistry.initialize()
        provider_cls = ProviderRegistry.get(cfg.default_provider)
        if provider_cls is None:
            provider_cls = ProviderRegistry.get("minimaxi")

        class MinimalApp:
            config = cfg
            current_provider = cfg.default_provider
            current_model = cfg.default_model

        project_dir = Path(cwd).resolve() if cwd else Path.cwd()
        self.agent = AgentEngine(MinimalApp(), project_dir=project_dir)

        return {
            "sessionId": self.session_id,
            "modes": {
                "currentModeId": cfg.default_mode,
                "availableModes": [
                    {"id": "agent", "name": "Agent", "description": "Standard agent mode"},
                    {"id": "plan", "name": "Plan", "description": "Planning mode"},
                    {"id": "solo", "name": "Solo", "description": "Solo mode"},
                ],
            },
        }

    async def session_prompt(self, prompt: list, session_id: str):
        """Send prompt to agent and stream results."""
        if self.agent is None:
            return {"stopReason": "error", "message": "No agent initialized"}

        user_message = ""
        for block in prompt:
            if block.get("type") == "text":
                user_message = block.get("text", "")

        async for event in self.agent.chat_stream(user_message):
            if event.type == StreamEventType.TEXT_DELTA:
                self.send_notification("session/update", {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": event.text},
                })
            elif event.type == StreamEventType.TOOL_CALL_START:
                self.tool_calls[event.tool_id] = {
                    "sessionUpdate": "tool_call",
                    "toolCallId": event.tool_id,
                    "title": event.tool_name,
                    "input": event.tool_args,
                }
                self.send_notification("session/update", self.tool_calls[event.tool_id])
            elif event.type == StreamEventType.TOOL_RESULT:
                if event.tool_id in self.tool_calls:
                    self.tool_calls[event.tool_id].update({
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": event.tool_id,
                        "result": event.result_content,
                        "status": "error" if event.result_is_error else "success",
                    })
                else:
                    self.tool_calls[event.tool_id] = {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": event.tool_id,
                        "result": event.result_content,
                        "status": "error" if event.result_is_error else "success",
                    }
                self.send_notification("session/update", self.tool_calls[event.tool_id])

        return {"stopReason": "stop"}

    async def session_cancel(self, session_id: str, _meta: dict):
        """Cancel current session."""
        if self.agent:
            await self.agent.cancel()
        return {}

    async def session_set_mode(self, session_id: str, mode_id: str):
        """Set session mode."""
        return {}


class JSONRPCServer:
    def __init__(self, adapter: CDHACPAdapter):
        self.adapter = adapter
        self.methods = {
            "initialize": self._handle_initialize,
            "session/new": self._handle_session_new,
            "session/prompt": self._handle_session_prompt,
            "session/cancel": self._handle_session_cancel,
            "session/set_mode": self._handle_session_set_mode,
        }

    async def handle_request(self, request: dict):
        """Handle a JSONRPC request."""
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")

        handler = self.methods.get(method)
        if handler is None:
            return {"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Method not found: {method}"}, "id": req_id}

        try:
            result = await handler(params)
            return {"jsonrpc": "2.0", "result": result, "id": req_id}
        except Exception as e:
            return {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}, "id": req_id}

    async def _handle_initialize(self, params: dict):
        return await self.adapter.initialize(
            params.get("protocolVersion"),
            params.get("clientCapabilities", {}),
            params.get("clientInfo", {}),
        )

    async def _handle_session_new(self, params: dict):
        return await self.adapter.session_new(
            params.get("cwd", "."),
            params.get("mcpServers", []),
        )

    async def _handle_session_prompt(self, params: dict):
        return await self.adapter.session_prompt(
            params.get("prompt", []),
            params.get("sessionId"),
        )

    async def _handle_session_cancel(self, params: dict):
        return await self.adapter.session_cancel(
            params.get("sessionId"),
            params.get("_meta", {}),
        )

    async def _handle_session_set_mode(self, params: dict):
        return await self.adapter.session_set_mode(
            params.get("sessionId"),
            params.get("modeId"),
        )


async def _main():
    adapter = CDHACPAdapter()
    server = JSONRPCServer(adapter)

    while True:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            break

        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        if isinstance(request, dict):
            response = await server.handle_request(request)
            if response.get("id") is not None:
                print(json.dumps(response), flush=True)
        elif isinstance(request, list):
            for req in request:
                if isinstance(req, dict) and req.get("id") is not None:
                    response = await server.handle_request(req)
                    if response.get("id") is not None:
                        print(json.dumps(response), flush=True)


def main():
    asyncio.run(_main())

if __name__ == "__main__":
    main()