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
from cdha.models.messages import (
    StreamEventType,
    AgentMessage,
    TextBlock,
    ThinkBlock,
    ToolCall as MsgToolCall,
    ToolResult,
    SubAgentBlock,
)

from cdha.models.providers.minimaxi_provider import MiniMaxiProvider
from cdha.models.providers.minimax_provider import MiniMaxProvider
from cdha.models.providers.anthropic_provider import AnthropicProvider
from cdha.models.providers.openai_provider import OpenAIProvider
from cdha.models.providers.deepseek_provider import DeepSeekProvider
from cdha.models.providers.glm_provider import GLMProvider
from cdha.models.providers.ollama_provider import OllamaProvider


_TOOL_KIND_MAP: dict[str, str] = {
    "Read": "read", "Write": "edit", "Edit": "edit", "Insert": "edit",
    "UndoEdit": "edit",
    "List": "read",
    "Glob": "search", "Grep": "search",
    "Bash": "execute",
    "WebFetch": "fetch", "WebSearch": "search",
    "Task": "other", "Agent": "other",
    "TaskCreate": "other", "TaskGet": "other", "TaskList": "other",
    "TaskUpdate": "other", "TaskOutput": "other", "TaskStop": "other",
    "TodoCreate": "other", "TodoList": "other", "TodoComplete": "other",
    "SendMessage": "other", "AskUser": "other",
    "SkillTool": "other", "ToolSearch": "other",
    "MCPTool": "other", "MCPResources": "other",
}


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
        self.in_thinking = False

    @staticmethod
    def _content_to_blocks(content: str | list) -> list:
        """Convert old-format message content to list of AgentBlock objects."""
        blocks: list = []
        if isinstance(content, str):
            if content.strip():
                blocks.append(TextBlock(content=content))
        elif isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type", "")
                if item_type == "text":
                    blocks.append(TextBlock(content=item.get("text", "")))
                elif item_type == "thinking":
                    blocks.append(ThinkBlock(content=item.get("thinking", "")))
                elif item_type == "tool_use":
                    blocks.append(MsgToolCall(
                        id=item.get("id", ""),
                        name=item.get("name", ""),
                        input=item.get("input", {}),
                        status=item.get("status", "completed"),
                    ))
                elif item_type == "tool_result":
                    blocks.append(ToolResult(
                        tool_use_id=item.get("tool_use_id", ""),
                        content=item.get("content", ""),
                        is_error=item.get("is_error", False),
                    ))
                elif item_type == "subagent":
                    blocks.append(SubAgentBlock(
                        id=item.get("id", ""),
                        agent_type=item.get("agent_type", "default"),
                        prompt=item.get("prompt", ""),
                        result=item.get("result", ""),
                        status=item.get("status", "completed"),
                    ))
        return blocks

    def send_notification(self, method: str, params: dict):
        """Send a JSONRPC notification to A2TUI."""
        notification = {"jsonrpc": "2.0", "method": method, "params": params}
        print(json.dumps(notification), flush=True)

    def cancel_prompt(self):
        """Synchronously cancel the current prompt (called from main loop)."""
        if self.agent:
            self.agent._cancelled = True

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
            if role == "user":
                content = msg.get("content", "")
                self.send_session_update({
                    "sessionUpdate": "user_message_chunk",
                    "content": {"type": "text", "text": content},
                })
            elif role == "assistant":
                # Handle both old format (content as str/list) and new format (blocks)
                if "blocks" in msg:
                    agent_msg = AgentMessage.from_dict(msg)
                    blocks = agent_msg.blocks
                else:
                    content = msg.get("content", "")
                    blocks = self._content_to_blocks(content)

                for block in blocks:
                    if isinstance(block, TextBlock):
                        self.send_session_update({
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": block.content},
                        })
                    elif isinstance(block, ThinkBlock):
                        self.send_session_update({
                            "sessionUpdate": "agent_thought_chunk",
                            "content": {"type": "text", "text": f"```thinking\n{block.content}\n```"},
                        })
                    elif isinstance(block, MsgToolCall):
                        tool_kind = _TOOL_KIND_MAP.get(block.name, "other")
                        self.send_session_update({
                            "sessionUpdate": "tool_call",
                            "toolCallId": block.id,
                            "title": block.name,
                            "kind": tool_kind,
                            "status": block.status.value,
                        })
                    elif isinstance(block, ToolResult):
                        content_block = [{
                            "type": "content",
                            "content": {"type": "text", "text": block.content},
                        }] if block.content else []
                        self.send_session_update({
                            "sessionUpdate": "tool_call_update",
                            "toolCallId": block.tool_use_id,
                            "status": "failed" if block.is_error else "completed",
                            "content": content_block,
                        })
                    elif isinstance(block, SubAgentBlock):
                        content_block = [{
                            "type": "content",
                            "content": {"type": "text", "text": block.result},
                        }] if block.result else []
                        self.send_session_update({
                            "sessionUpdate": "tool_call",
                            "toolCallId": block.id,
                            "title": f"SubAgent: {block.agent_type}",
                            "kind": "other",
                            "status": block.status.value,
                            "content": content_block,
                        })

        return {
            "modes": {
                "currentModeId": cfg.default_mode,
                "availableModes": _DEFAULT_MODES["availableModes"],
            },
        }

    def _make_stream_callback(self):
        """Create a thinking-aware streaming callback for real-time token output.

        Buffers text deltas from the provider, detects <thinking>...</thinking>
        boundaries, and routes content to the appropriate ACP session update type.
        """
        text_buffer = ""
        in_thinking = False

        def _safe_start(s: str) -> str:
            """Return text before any partial <thinking tag at buffer end."""
            tag = "<thinking>"
            for i in range(len(tag) - 1, 0, -1):
                if s.endswith(tag[:i]):
                    return s[:-i]
            return s

        def on_chunk(text: str):
            nonlocal text_buffer, in_thinking
            text_buffer += text

            while text_buffer:
                if in_thinking:
                    idx = text_buffer.find("</thinking>")
                    if idx >= 0:
                        thinking = text_buffer[:idx]
                        if thinking:
                            self.send_session_update({
                                "sessionUpdate": "agent_thought_chunk",
                                "content": {"type": "text", "text": f"```thinking\n{thinking}\n```"},
                            })
                        text_buffer = text_buffer[idx + len("</thinking>"):]
                        in_thinking = False
                    else:
                        break
                else:
                    idx = text_buffer.find("<thinking>")
                    if idx >= 0:
                        before = text_buffer[:idx]
                        if before:
                            self.send_session_update({
                                "sessionUpdate": "agent_message_chunk",
                                "content": {"type": "text", "text": before},
                            })
                        text_buffer = text_buffer[idx + len("<thinking>"):]
                        in_thinking = True
                    else:
                        safe = _safe_start(text_buffer)
                        if safe:
                            self.send_session_update({
                                "sessionUpdate": "agent_message_chunk",
                                "content": {"type": "text", "text": safe},
                            })
                        text_buffer = text_buffer[len(safe):]
                        if not text_buffer.endswith("<") and not any(
                            text_buffer.endswith("<thinking"[:i]) for i in range(1, len("<thinking>"))
                        ):
                            text_buffer = ""

        return on_chunk

    async def session_prompt(self, prompt: list, session_id: str):
        """Send prompt to agent and stream results."""
        if self.agent is None:
            return {"stopReason": "error", "message": "No agent initialized"}

        user_message = ""
        for block in prompt:
            if block.get("type") == "text":
                user_message = block.get("text", "")

        self.agent._cancelled = False
        self.agent.on_text_chunk = self._make_stream_callback()
        async for event in self.agent.chat_stream(user_message):
            if event.type == StreamEventType.TEXT_DELTA:
                text = event.text
                if self.in_thinking:
                    self.send_session_update({
                        "sessionUpdate": "agent_thought_chunk",
                        "content": {"type": "text", "text": text},
                    })
                    if text.strip().endswith("```"):
                        self.in_thinking = False
                elif text.lstrip().startswith("```thinking"):
                    self.send_session_update({
                        "sessionUpdate": "agent_thought_chunk",
                        "content": {"type": "text", "text": text},
                    })
                    if not text.strip().endswith("```"):
                        self.in_thinking = True
                else:
                    self.send_session_update({
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": text},
                    })
            elif event.type == StreamEventType.TOOL_CALL_START:
                tool_kind = _TOOL_KIND_MAP.get(event.tool_name, "other")
                self.tool_calls[event.tool_id] = {
                    "sessionUpdate": "tool_call",
                    "toolCallId": event.tool_id,
                    "title": event.tool_name,
                    "kind": tool_kind,
                    "status": "in_progress",
                    "content": [],
                }
                self.send_session_update(self.tool_calls[event.tool_id])
            elif event.type == StreamEventType.TOOL_CALL_COMPLETE:
                if event.tool_id in self.tool_calls:
                    # Show input args but keep status as in_progress so
                    # frontend doesn't clear agent_thought/agent_response streams
                    args_text = json.dumps(event.tool_args, indent=2, ensure_ascii=False) if event.tool_args else ""
                    content = [{
                        "type": "content",
                        "content": {"type": "text", "text": args_text},
                    }] if args_text else []
                    self.tool_calls[event.tool_id].update({
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": event.tool_id,
                        "status": "in_progress",
                        "content": content,
                    })
                    self.send_session_update(self.tool_calls[event.tool_id])
            elif event.type == StreamEventType.TOOL_RESULT:
                status = "failed" if event.result_is_error else "completed"
                content_block = [{
                    "type": "content",
                    "content": {"type": "text", "text": event.result_content},
                }] if event.result_content else []
                update = {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": event.tool_id,
                    "status": status,
                    "content": content_block,
                }
                if event.tool_id in self.tool_calls:
                    self.tool_calls[event.tool_id].update(update)
                else:
                    self.tool_calls[event.tool_id] = {
                        "sessionUpdate": "tool_call",
                        "toolCallId": event.tool_id,
                        "title": "Tool call",
                        "kind": "other",
                        "status": status,
                        **update,
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
        stop_reason = "cancelled" if self.agent._cancelled else "end_turn"
        return {"stopReason": stop_reason}

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
    prompt_task: asyncio.Task | None = None

    async def _run_prompt(req: dict):
        try:
            result = await server._handle_session_prompt(req.get("params", {}))
            return {"jsonrpc": "2.0", "result": result, "id": req.get("id")}
        except Exception as e:
            return {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}, "id": req.get("id")}

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

        requests = request if isinstance(request, list) else [request]

        for req in requests:
            if not isinstance(req, dict):
                continue
            method = req.get("method", "")
            req_id = req.get("id")

            if method == "session/prompt":
                # Run prompt in background so main loop stays responsive
                # to cancel notifications on stdin
                prompt_task = asyncio.create_task(_run_prompt(req))
                def _on_prompt_done(t):
                    resp = t.result()
                    if resp.get("id") is not None:
                        print(json.dumps(resp), flush=True)
                prompt_task.add_done_callback(_on_prompt_done)
            elif method == "session/cancel":
                if prompt_task and not prompt_task.done():
                    adapter.cancel_prompt()
                # Notification (no id) — nothing to respond with
            else:
                response = await server.handle_request(req)
                if response.get("id") is not None:
                    print(json.dumps(response), flush=True)


def main():
    asyncio.run(_main())

if __name__ == "__main__":
    main()