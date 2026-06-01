from __future__ import annotations

from typing import Any, Optional, Union

from cdha.models.provider import (
    ContentBlock,
    ContentBlockType,
    Message as ProviderMessage,
    ToolResult as ProviderToolResult,
    ToolUse,
)


class ContextConfig:
    max_tokens: int = 100000
    max_messages: int = 1000
    compact_threshold: float = 0.85
    model: str = "gpt-4"


class Message:
    """Internal message — role + content as str or list[dict].

    This is the lightweight storage format used by ContextManager.
    It is converted to provider.Message via get_context() for API calls.
    """
    def __init__(self, role: str, content: Union[str, list], name: Optional[str] = None):
        self.role = role
        self.content = content
        self.name = name

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Message:
        return cls(role=data["role"], content=data["content"], name=data.get("name"))


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def _block_text(block: Any) -> str:
    if isinstance(block, dict):
        return str(block.get("text", "") or block.get("content", ""))
    return str(block)


class ContextManager:
    def __init__(self, config: Optional[ContextConfig] = None):
        self.config = config or ContextConfig()
        self.messages: list[Message] = []
        self._token_count = 0

    def add_message(self, role: str, content: Union[str, list], name: Optional[str] = None) -> None:
        self.messages.append(Message(role=role, content=content, name=name))
        self._update_token_count()

    def add_system(self, content: str) -> None:
        self.add_message("system", content)

    def replace_system_section(self, marker: str, new_content: str) -> bool:
        """Replace a tagged system message by marker substring.

        Args:
            marker: Substring to identify the system message to replace.
            new_content: New content for the system message.

        Returns:
            True if a matching system message was found and replaced.
        """
        for m in self.messages:
            if m.role == "system" and isinstance(m.content, str) and marker in m.content:
                m.content = new_content
                self._update_token_count()
                return True
        return False

    def add_user(self, content: str) -> None:
        self.add_message("user", content)

    def add_assistant(self, content: str | list) -> None:
        self.add_message("assistant", content)

    def add_tool_use(self, tool_use_id: str, name: str, input_data: dict[str, Any]) -> None:
        self.add_message("assistant", [{"type": "tool_use", "id": tool_use_id, "name": name, "input": input_data}])

    def add_tool_result(self, tool_call_id: str, content: Union[str, dict, list], is_error: bool = False) -> None:
        if isinstance(content, (dict, list)):
            self.add_message("tool", content, name=tool_call_id)
        else:
            self.add_message("tool", [{"type": "tool_result", "tool_use_id": tool_call_id, "content": content, "is_error": is_error}], name=tool_call_id)

    def _update_token_count(self) -> None:
        total = 0
        for m in self.messages:
            if isinstance(m.content, str):
                total += _estimate_tokens(m.content)
            elif isinstance(m.content, list):
                for block in m.content:
                    total += _estimate_tokens(_block_text(block))
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
                texts = [_block_text(b)[:200] for b in m.content]
                content_parts.append(f"{prefix}: {' | '.join(texts)[:500]}")
        return "\n".join(content_parts[-10:])

    def get_context(self) -> list:
        def to_provider_content(msg: Message) -> Union[str, list]:
            if isinstance(msg.content, str):
                return msg.content
            blocks = []
            for block in msg.content:
                if isinstance(block, dict):
                    btype = block.get("type", "text")
                    if btype == "text":
                        blocks.append(ContentBlock(type=ContentBlockType.TEXT, text=block.get("text", "")))
                    elif btype == "thinking":
                        blocks.append(ContentBlock(type=ContentBlockType.THINKING, thinking=block.get("thinking", "")))
                    elif btype == "tool_use":
                        blocks.append(ContentBlock(
                            type=ContentBlockType.TOOL_USE,
                            tool_use=ToolUse(
                                id=block.get("id", ""),
                                name=block.get("name", ""),
                                input=block.get("input", {}),
                                caller=block.get("caller", "agent"),
                            ),
                        ))
                    elif btype == "tool_result":
                        blocks.append(ContentBlock(
                            type=ContentBlockType.TOOL_RESULT,
                            tool_result=ProviderToolResult(
                                tool_use_id=block.get("tool_use_id", ""),
                                content=block.get("content", ""),
                                is_error=block.get("is_error", False),
                            ),
                        ))
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
