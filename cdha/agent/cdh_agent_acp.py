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
from cdha.agent.session import AgentSession
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


_DEFAULT_MODES = {
    "currentModeId": "agent",
    "availableModes": [
        {"id": "agent", "name": "Agent", "description": "Full development agent with all tools enabled"},
        {"id": "plan",  "name": "Plan",  "description": "Read-only planning and analysis. Edits and shell commands require approval."},
        {"id": "solo",  "name": "Solo",  "description": "Independent mode with plan-first workflow. Edits allowed, shell commands require approval."},
    ],
}


def _create_engine(cwd: str) -> AgentEngine:
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
    return AgentEngine(MinimalApp(), project_dir=project_dir)


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

    def send_session_update(self, update: dict):
        """Send a session/update notification with proper ACP protocol format."""
        self.send_notification("session/update", {
            "sessionId": self.session_id,
            "update": update,
        })

    async def initialize(self, protocol_version: int, client_capabilities: dict, client_info: dict):
        """Handle ACP initialize."""
        return {
            "protocolVersion": 1,
            "agentCapabilities": {
                "loadSession": True,
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
        cfg = load_config()
        self.agent = _create_engine(cwd)
        self.agent.set_agent(cfg.default_mode)

        session = AgentSession()
        session.name = "New Session"
        session.mode = cfg.default_mode
        session.project = str(Path(cwd).resolve() if cwd else Path.cwd())
        session.model = cfg.default_model
        session.provider = cfg.default_provider
        session.save()
        self.agent.attach_session(session)
        self.session_id = session.id

        return {
            "sessionId": self.session_id,
            "modes": {
                "currentModeId": cfg.default_mode,
                "availableModes": _DEFAULT_MODES["availableModes"],
            },
        }

    async def session_load(self, cwd: str, mcp_servers: list, session_id: str):
        """Load existing session."""
        self.agent = _create_engine(cwd)
        self.session_id = session_id

        loaded = self.agent.load_session(session_id)
        cfg = load_config()
        self.agent.set_agent(cfg.default_mode)
        if not loaded:
            return {"modes": _DEFAULT_MODES}

        for msg in self.agent._session.messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                self.send_session_update({
                    "sessionUpdate": "user_message_chunk",
                    "content": {"type": "text", "text": content},
                })
            elif role == "assistant":
                self.send_session_update({
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": content},
                })

        return {
            "modes": {
                "currentModeId": cfg.default_mode,
                "availableModes": _DEFAULT_MODES["availableModes"],
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
                text = event.text
                if text.lstrip().startswith("```thinking"):
                    self.send_session_update({
                        "sessionUpdate": "agent_thought_chunk",
                        "content": {"type": "text", "text": text},
                    })
                else:
                    self.send_session_update({
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": text},
                    })
            elif event.type == StreamEventType.TOOL_CALL_START:
                self.tool_calls[event.tool_id] = {
                    "sessionUpdate": "tool_call",
                    "toolCallId": event.tool_id,
                    "title": event.tool_name,
                    "input": event.tool_args,
                }
                self.send_session_update(self.tool_calls[event.tool_id])
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
                self.send_session_update(self.tool_calls[event.tool_id])
            elif event.type == StreamEventType.ERROR:
                self.send_session_update({
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": f"Error: {event.error_message}"},
                })
                self.agent.save_session()
                return {"stopReason": "error", "message": event.error_message}
            elif event.type == StreamEventType.PLAN:
                self.send_session_update({
                    "sessionUpdate": "plan",
                    "entries": event.plan_entries,
                })

        self.agent.save_session()
        return {"stopReason": "stop"}

    async def session_cancel(self, session_id: str, _meta: dict):
        """Cancel current session."""
        if self.agent:
            await self.agent.cancel()
        return {}

    async def session_set_mode(self, session_id: str, mode_id: str):
        """Set session mode — propagates to engine and notifies TUI."""
        if self.agent:
            self.agent.set_agent(mode_id)
            self.send_session_update({
                "sessionUpdate": "current_mode_update",
                "currentModeId": mode_id,
            })
        return {"modeId": mode_id}


class JSONRPCServer:
    def __init__(self, adapter: CDHACPAdapter):
        self.adapter = adapter
        self.methods = {
            "initialize": self._handle_initialize,
            "session/new": self._handle_session_new,
            "session/load": self._handle_session_load,
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

    async def _handle_session_load(self, params: dict):
        return await self.adapter.session_load(
            params.get("cwd", "."),
            params.get("mcpServers", []),
            params.get("sessionId"),
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