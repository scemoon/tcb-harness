from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from cdh.models.provider import ContentBlock, Message as ProviderMessage


class ContextConfig:
    max_tokens: int = 100000
    max_messages: int = 1000
    compact_threshold: float = 0.85
    model: str = "gpt-4"


class Message:
    def __init__(self, role: str, content: str, name: Optional[str] = None):
        self.role = role
        self.content = content
        self.name = name

    def to_dict(self) -> dict:
        d = {"role": self.role, "content": self.content}
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

    def add_message(self, role: str, content: str, name: Optional[str] = None) -> None:
        msg = Message(role=role, content=content, name=name)
        self.messages.append(msg)
        self._update_token_count()

    def add_system(self, content: str) -> None:
        self.add_message("system", content)

    def add_user(self, content: str) -> None:
        self.add_message("user", content)

    def add_assistant(self, content: str | list) -> None:
        from cdh.models.provider import ModelResponse
        if isinstance(content, str):
            self.add_message("assistant", content)
        else:
            response = ModelResponse(content)
            text = response.get_text()
            self.add_message("assistant", text)

    def _update_token_count(self) -> None:
        self._token_count = sum(
            _estimate_tokens(m.content) for m in self.messages
        )

    def _update_token_count(self) -> None:
        self._token_count = sum(_estimate_tokens(m.content) for m in self.messages)

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

        self._token_count = sum(_estimate_tokens(m.content) for m in self.messages)

    def _summarize_messages(self, msgs: list[Message]) -> str:
        content_parts = []
        for m in msgs[-20:]:
            prefix = {"user": "User", "assistant": "Assistant"}.get(m.role, m.role)
            content_parts.append(f"{prefix}: {m.content[:500]}")
        return "\n".join(content_parts[-10:])

    def add_tool_result(self, tool_call_id: str, content: str, is_error: bool = False) -> None:
        self.add_message("tool", content, name=tool_call_id)

    def get_context(self) -> list:
        from cdh.models.provider import Message as ProviderMessage
        return [
            ProviderMessage(role=m.role, content=m.content, name=m.name)
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