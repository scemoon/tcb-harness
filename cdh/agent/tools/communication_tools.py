from __future__ import annotations

import json
from typing import Any

from cdh.agent.tools.protocol import ToolResult
from cdh.agent.tools.registry import ToolRegistry, ToolSpec


class SendMessageTool:
    def __init__(self):
        self.last_message: str = ""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="SendMessage",
            description="Send a user-visible message with optional file attachments.",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "The message to show to the user"},
                    "attachments": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional file paths to attach",
                    },
                },
                "required": ["message"],
            },
            is_read_only=True,
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        message = tool_input.get("message", "")
        attachments = tool_input.get("attachments", [])
        self.last_message = message
        return ToolResult(name="SendMessage", output={"message": message, "attachments": attachments})


class AskUserTool:
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="AskUser",
            description="Ask the user a question and wait for their response.",
            input_schema={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question to ask"},
                    "context": {"type": "string", "description": "Additional context"},
                },
                "required": ["question"],
            },
            is_read_only=True,
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        question = tool_input.get("question", "")
        context = tool_input.get("context", "")
        return ToolResult(name="AskUser", output={"question": question, "context": context})


class ToolSearchTool:
    def __init__(self, registry: ToolRegistry):
        self._registry = registry

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="ToolSearch",
            description="Search for available tools by keyword.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword to find relevant tools"},
                },
                "required": ["query"],
            },
            is_read_only=True,
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        query = tool_input.get("query", "").lower()
        specs = self._registry.list_specs()
        matches = []
        for spec in specs:
            if query in spec.name.lower() or query in spec.description.lower():
                matches.append({"name": spec.name, "description": spec.description})
        if not matches:
            matches = [{"name": s.name, "description": s.description[:80]} for s in specs[:10]]
        return ToolResult(name="ToolSearch", output={"matches": matches[:20]})
