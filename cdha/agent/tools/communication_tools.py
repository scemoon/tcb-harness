from __future__ import annotations

import json
from typing import Any

from cdha.agent.tools.protocol import ToolResult
from cdha.agent.tools.registry import ToolRegistry, ToolSpec


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



_OPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "description": "Display text for the option"},
        "value": {"type": "string", "description": "Value returned when selected"},
        "description": {"type": "string", "description": "Optional explanation of the choice"},
        "key": {"type": "string", "description": "Optional keyboard shortcut (e.g. 'y', 'n')"},
        "default": {"type": "boolean", "description": "Auto-select if user doesn't respond"},
    },
    "required": ["label", "value"],
}

_QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "header": {"type": "string", "description": "Short label (max 30 chars) for this question"},
        "question": {"type": "string", "description": "The question text shown to the user"},
        "type": {
            "type": "string",
            "enum": ["single", "multiple", "confirm"],
            "description": "Question type: single=one choice, multiple=multi-select, confirm=yes/no",
        },
        "options": {
            "type": "array",
            "items": _OPTION_SCHEMA,
            "description": "Predefined choices. For 'confirm' type, omit to get default Yes/No options.",
        },
    },
    "required": ["question"],
}


class AskUserTool:
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="AskUser",
            description="Ask the user one or more questions with optional predefined choices.",
            input_schema={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "[DEPRECATED] Single question text. Use 'questions' instead."},
                    "header": {"type": "string", "description": "[DEPRECATED] Short label for single question."},
                    "context": {"type": "string", "description": "Additional context"},
                    "options": {
                        "type": "array",
                        "items": _OPTION_SCHEMA,
                        "description": "[DEPRECATED] Options for single question. Use 'questions' instead.",
                    },
                    "questions": {
                        "type": "array",
                        "items": _QUESTION_SCHEMA,
                        "minItems": 1,
                        "maxItems": 6,
                        "description": "One or more questions to ask the user. Supports single choice, multiple selection, and confirm types.",
                    },
                },
                "oneOf": [
                    {"required": ["question"]},
                    {"required": ["questions"]},
                ],
            },
            is_read_only=True,
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        question = tool_input.get("question", "")
        header = tool_input.get("header", "")
        context = tool_input.get("context", "")
        options = tool_input.get("options", [])
        questions = tool_input.get("questions", [])
        return ToolResult(name="AskUser", output={
            "question": question,
            "header": header,
            "context": context,
            "options": options,
            "questions": questions,
        })



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

