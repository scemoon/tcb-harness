from __future__ import annotations

import json
from typing import Any, Optional, Union

from cdh.models.provider import ContentBlock


class ContextConfig:
    max_tokens: int = 100000
    max_messages: int = 1000
    compact_threshold: float = 0.85
    model: str = "gpt-4"


class TextContent:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class ToolUseContent:
    def __init__(self, tool_use_id: str, name: str, input: dict[str, Any]):
        self.type = "tool_use"
        self.id = tool_use_id
        self.name = name
        self.input = input


class ToolResultContent:
    def __init__(self, tool_use_id: str, content: str, is_error: bool = False):
        self.type = "tool_result"
        self.tool_use_id = tool_use_id
        self.content = content
        self.is_error = is_error


class Message:
    def __init__(self, role: str, content: Union[str, list], name: Optional[str] = None):
        self.role = role
        self.content = content
        self.name = name

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"role": self.role}
        if isinstance(self.content, str):
            d["content"] = self.content
        else:
            blocks = []
            for block in self.content:
                if isinstance(block, TextContent):
                    blocks.append({"type": "text", "text": block.text})
                elif isinstance(block, ToolUseContent):
                    blocks.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
                elif isinstance(block, ToolResultContent):
                    blocks.append({
                        "type": "tool_result",
                        "tool_use_id": block.tool_use_id,
                        "content": block.content,
                        "is_error": block.is_error,
                    })
            d["content"] = blocks
        if self.name:
            d["name"] = self.name
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Message:
        return cls(role=data["role"], content=data["content"], name=data.get("name"))


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


class ContextManager:
    def __init__(self, config: Optional[ContextConfig] = None):
        self.config = config or ContextConfig()
        self.messages: list[Message] = []
        self._token_count = 0

    def add_message(self, role: str, content: Union[str, list], name: Optional[str] = None) -> None:
        msg = Message(role=role, content=content, name=name)
        self.messages.append(msg)
        self._update_token_count()

    def add_system(self, content: str) -> None:
        self.add_message("system", content)

    def add_user(self, content: str) -> None:
        self.add_message("user", content)

    def add_assistant(self, content: str | list) -> None:
        if isinstance(content, str):
            self.add_message("assistant", content)
        else:
            self.add_message("assistant", content)

    def add_tool_use(self, tool_use_id: str, name: str, input_data: dict[str, Any]) -> None:
        self.add_message("assistant", [ToolUseContent(tool_use_id, name, input_data)])

    def add_tool_result(self, tool_call_id: str, content: Union[str, dict, list], is_error: bool = False) -> None:
        if isinstance(content, (dict, list)):
            self.add_message("tool", content, name=tool_call_id)
        else:
            self.add_message("tool", [ToolResultContent(tool_call_id, content, is_error)], name=tool_call_id)

    def _update_token_count(self) -> None:
        total = 0
        for m in self.messages:
            if isinstance(m.content, str):
                total += _estimate_tokens(m.content)
            elif isinstance(m.content, list):
                for block in m.content:
                    if isinstance(block, dict):
                        text = block.get("text", "") or block.get("content", "")
                        total += _estimate_tokens(str(text))
                    elif hasattr(block, 'text'):
                        total += _estimate_tokens(block.text)
                    elif hasattr(block, 'content') and isinstance(block.content, str):
                        total += _estimate_tokens(block.content)
        self._token_count = total

    def should_compact(self) -> bool:
        if self.config.max_tokens <= 0:
            return False
        return self._token_count >= self.config.max_tokens * self.config.compact_threshold

    def compact(self) -> None:
        if len(self.messages) <= 2:
            return

        system_msgs = [m for m in self.messages if m.role == "system"]
        other_msgs = [m for m in self.messages if m.role != "system"]

        if not other_msgs:
            return

        summary = self._summarize_messages(other_msgs)
        self.messages = system_msgs + [Message(role="system", content=f"[Previous context summarized]\n{summary}")]
        self._update_token_count()

    def _summarize_messages(self, msgs: list[Message]) -> str:
        content_parts = []
        for m in msgs[-20:]:
            prefix = {"user": "User", "assistant": "Assistant", "tool": "Tool"}.get(m.role, m.role)
            if isinstance(m.content, str):
                content_parts.append(f"{prefix}: {m.content[:500]}")
            elif isinstance(m.content, list):
                parts = []
                for block in m.content:
                    if isinstance(block, dict):
                        text = block.get("text", "") or block.get("content", "")
                        parts.append(str(text)[:200])
                    elif hasattr(block, 'text'):
                        parts.append(block.text[:200])
                    elif hasattr(block, 'content') and isinstance(block.content, str):
                        parts.append(block.content[:200])
                content_parts.append(f"{prefix}: {' | '.join(parts)[:500]}")
        return "\n".join(content_parts[-10:])

    def get_context(self) -> list:
        from cdh.models.provider import Message as ProviderMessage

        def to_provider_content(msg: Message) -> Union[str, list]:
            if isinstance(msg.content, str):
                return msg.content
            blocks = []
            for block in msg.content:
                if isinstance(block, TextContent):
                    blocks.append({"type": "text", "text": block.text})
                elif isinstance(block, ToolUseContent):
                    blocks.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
                elif isinstance(block, ToolResultContent):
                    blocks.append({"type": "tool_result", "tool_use_id": block.tool_use_id, "content": block.content, "is_error": block.is_error})
            return blocks

        return [
            ProviderMessage(role=m.role, content=to_provider_content(m), name=m.name)
            for m in self.messages
        ]

    def reset(self) -> None:
        self.messages = []
        self._token_count = 0

    def load_from_session(self, data: list[dict]) -> None:
        self.messages = [Message.from_dict(d) for d in data]
        self._update_token_count()

    def to_session_format(self) -> list[dict]:
        return [m.to_dict() for m in self.messages]

    def info(self) -> str:
        return f"Messages: {len(self.messages)}, Tokens: ~{self._token_count}"
