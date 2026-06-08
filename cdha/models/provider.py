from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Optional


@dataclass(frozen=True)
class ChatResponse:
    """Structured response from a streaming provider call (Clawd-Code style).

    Unlike ModelResponse (which uses ContentBlock list), ChatResponse provides
    a flat structure for the agent loop: content text + structured tool_uses + usage.
    """
    content: str = ""
    tool_uses: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)


class ContentBlockType(str, Enum):
    TEXT = "text"
    THINKING = "thinking"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    SERVER_TOOL_USE = "server_tool_use"
    TOOL_SEARCH_RESULT = "tool_search_tool_result"
    CODE_EXECUTION_RESULT = "code_execution_tool_result"


@dataclass
class ToolUse:
    id: str
    name: str
    input: dict[str, Any]
    caller: str = "agent"


@dataclass
class ServerToolUse:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ToolSearchResult:
    tool_use_id: str
    content: Any  # Can be dict with search results


@dataclass
class CodeExecutionResult:
    tool_use_id: str
    content: Any  # Can be dict with execution output


@dataclass
class ToolResult:
    tool_use_id: str
    content: str
    is_error: bool = False
    content_blocks: list["ContentBlock"] = field(default_factory=list)


@dataclass
class ContentBlock:
    type: ContentBlockType
    text: Optional[str] = None
    thinking: Optional[str] = None
    tool_use: Optional[ToolUse] = None
    tool_result: Optional[ToolResult] = None
    server_tool_use: Optional[ServerToolUse] = None
    tool_search_result: Optional[ToolSearchResult] = None
    code_execution_result: Optional[CodeExecutionResult] = None
    cache_control: Optional[str] = None


@dataclass
class Message:
    role: str  # user | assistant | system | tool
    content: list[ContentBlock] = field(default_factory=list)
    name: Optional[str] = None

    def __init__(self, role: str, content: str | list[ContentBlock] = "", name: Optional[str] = None):
        self.role = role
        self.name = name
        if isinstance(content, str):
            if role == "tool" and name:
                self.content = [ContentBlock(
                    type=ContentBlockType.TOOL_RESULT,
                    tool_result=ToolResult(tool_use_id=name, content=content),
                )]
            else:
                self.content = [ContentBlock(type=ContentBlockType.TEXT, text=content)] if content else []
        else:
            self.content = content

    def add_text(self, text: str) -> None:
        self.content.append(ContentBlock(type=ContentBlockType.TEXT, text=text))

    def add_thinking(self, thinking: str) -> None:
        self.content.append(ContentBlock(type=ContentBlockType.THINKING, thinking=thinking))

    def add_tool_use(self, tool_use: ToolUse) -> None:
        self.content.append(ContentBlock(type=ContentBlockType.TOOL_USE, tool_use=tool_use))

    def add_tool_result(self, tool_result: ToolResult) -> None:
        self.content.append(ContentBlock(type=ContentBlockType.TOOL_RESULT, tool_result=tool_result))

    def to_api_content(self) -> str:
        """Serialize text/thinking content for OpenAI-style API calls."""
        return "\n".join(
            cb.text or cb.thinking or ""
            for cb in self.content
            if cb.type in (ContentBlockType.TEXT, ContentBlockType.THINKING)
        )

    def to_api_dict(self) -> dict:
        """Serialize to OpenAI-compatible message dict, including tool_calls and tool role."""
        text = self.to_api_content()
        msg: dict = {"role": self.role}
        if text:
            msg["content"] = text
        else:
            msg["content"] = None

        tool_calls = []
        for cb in self.content:
            if cb.type == ContentBlockType.TOOL_USE and cb.tool_use:
                tc = {
                    "id": cb.tool_use.id,
                    "type": "function",
                    "function": {
                        "name": cb.tool_use.name,
                        "arguments": cb.tool_use.input if isinstance(cb.tool_use.input, str) else __import__("json").dumps(cb.tool_use.input),
                    }
                }
                tool_calls.append(tc)
            if cb.type == ContentBlockType.TOOL_RESULT and cb.tool_result:
                msg["role"] = "tool"
                msg["tool_call_id"] = cb.tool_result.tool_use_id
                msg["content"] = cb.tool_result.content

        if tool_calls:
            msg["tool_calls"] = tool_calls

        return msg


@dataclass
class ModelResponse:
    content: list[ContentBlock] = field(default_factory=list)
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    raw: Any = None

    def __init__(self, content: str | list[ContentBlock | dict] = "", model: str = "", usage: dict[str, Any] = None, raw: Any = None):
        self.model = model
        self.usage = usage or {}
        self.raw = raw
        if isinstance(content, str):
            self.content = [ContentBlock(type=ContentBlockType.TEXT, text=content)] if content else []
        elif isinstance(content, list):
            self.content = []
            for item in content:
                if isinstance(item, ContentBlock):
                    self.content.append(item)
                elif isinstance(item, dict):
                    cb_type = ContentBlockType(item.get("type", "text"))
                    if cb_type == ContentBlockType.TEXT:
                        self.content.append(ContentBlock(type=cb_type, text=item.get("text", "")))
                    elif cb_type == ContentBlockType.THINKING:
                        self.content.append(ContentBlock(type=cb_type, thinking=item.get("thinking", "")))
                    elif cb_type == ContentBlockType.TOOL_USE:
                        self.content.append(ContentBlock(
                            type=cb_type,
                            tool_use=ToolUse(
                                id=item.get("id", ""),
                                name=item.get("name", ""),
                                input=item.get("input", {}),
                                caller=item.get("caller", "agent"),
                            )
                        ))
                    elif cb_type == ContentBlockType.TOOL_RESULT:
                        self.content.append(ContentBlock(
                            type=cb_type,
                            tool_result=ToolResult(
                                tool_use_id=item.get("tool_use_id", ""),
                                content=item.get("content", ""),
                                is_error=item.get("is_error", False),
                            )
                        ))
                    elif cb_type == ContentBlockType.SERVER_TOOL_USE:
                        self.content.append(ContentBlock(
                            type=cb_type,
                            server_tool_use=ServerToolUse(
                                id=item.get("id", ""),
                                name=item.get("name", ""),
                                input=item.get("input", {}),
                            )
                        ))
                    elif cb_type == ContentBlockType.TOOL_SEARCH_RESULT:
                        self.content.append(ContentBlock(
                            type=cb_type,
                            tool_search_result=ToolSearchResult(
                                tool_use_id=item.get("tool_use_id", ""),
                                content=item.get("content", {}),
                            )
                        ))
                    elif cb_type == ContentBlockType.CODE_EXECUTION_RESULT:
                        self.content.append(ContentBlock(
                            type=cb_type,
                            code_execution_result=CodeExecutionResult(
                                tool_use_id=item.get("tool_use_id", ""),
                                content=item.get("content", {}),
                            )
                        ))
                    else:
                        self.content.append(ContentBlock(type=cb_type, text=str(item)))
                else:
                    self.content.append(ContentBlock(type=ContentBlockType.TEXT, text=str(item)))
        else:
            self.content = []

    def get_text(self) -> str:
        return "".join(cb.text or "" for cb in self.content if cb.type == ContentBlockType.TEXT)

    def get_thinking(self) -> Optional[str]:
        for cb in self.content:
            if cb.type == ContentBlockType.THINKING:
                return cb.thinking
        return None


class Provider(ABC):
    name: str = ""

    @abstractmethod
    async def chat(
        self, messages: list[Message], model: str, **kwargs
    ) -> ModelResponse:
        ...

    @abstractmethod
    async def chat_stream(
        self, messages: list[Message], model: str, **kwargs
    ) -> AsyncIterator[str]:
        ...
        yield ""

    def resolve_api_key(self, key: Optional[str]) -> str:
        from cdha.config import resolve_env

        if key and key.startswith("${"):
            return resolve_env(key)
        return key or ""

    def prepare_messages(self, messages: list["Message"]) -> list[dict]:
        """Prepare messages for API call. Handles tool, tool_use, tool_result blocks properly."""
        system_parts = []
        non_system = []

        for m in messages:
            if m.role == "system":
                system_parts.append(m.to_api_content())
            else:
                non_system.append(m.to_api_dict())

        if len(system_parts) > 1:
            combined_system = "\n\n".join(system_parts)
        elif system_parts:
            combined_system = system_parts[0]
        else:
            combined_system = ""

        if combined_system:
            non_system.insert(0, {"role": "system", "content": combined_system})

        return non_system

    def parse_response_tool_calls(self, response_data: dict) -> list[dict]:
        """Extract tool calls from a non-streaming API response."""
        choice = response_data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        tool_calls = msg.get("tool_calls", [])
        result = []
        for tc in tool_calls:
            func = tc.get("function", {})
            try:
                args = __import__("json").loads(func.get("arguments", "{}"))
            except Exception:
                args = {"raw": func.get("arguments", "")}
            result.append({
                "id": tc.get("id", ""),
                "name": func.get("name", ""),
                "input": args,
            })
        return result

    # ── Clawd-Code style structured streaming ──

    def is_anthropic_style(self) -> bool:
        """Whether this provider uses Anthropic-style 'system' kwarg."""
        return False

    async def chat_stream_response(
        self,
        messages: list[Message],
        model: str,
        on_text_chunk: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> ChatResponse:
        """Stream with structured ChatResponse return (Clawd-Code style).

        Default implementation: falls back to chat() for providers that
        don't implement structured streaming.
        """
        response = await self.chat(messages, model=model, **kwargs)
        return ChatResponse(
            content=response.get_text(),
            tool_uses=[
                {"id": tu.id, "name": tu.name, "input": tu.input}
                for cb in response.content
                if cb.type == ContentBlockType.TOOL_USE and cb.tool_use
                for tu in [cb.tool_use]
            ],
            usage=response.usage,
        )

    # ── Error classification ────────────────────────────────────────

    @staticmethod
    def classify_http_error(
        status_code: int,
        body: str,
        *,
        retry_after: Optional[float] = None,
    ) -> "ProviderError":
        """Convert an upstream HTTP error into the most specific
        :class:`ProviderError` subclass.

        The 4 KiB body cap is applied here too so callers don't have to
        remember to truncate before constructing the exception.
        """
        from cdha.models.errors import (
            AuthError,
            ContextLengthError,
            ProviderError,
            RateLimitError,
            TransientProviderError,
        )
        snippet = (body or "").strip()
        if status_code == 429:
            return RateLimitError(
                "rate limit exceeded", status_code=status_code,
                retry_after=retry_after, body=snippet,
            )
        if status_code in (401, 403):
            return AuthError(
                "authentication failed", status_code=status_code, body=snippet,
            )
        if status_code == 400 and "context" in snippet.lower() and "length" in snippet.lower():
            return ContextLengthError(
                "context length exceeded", status_code=status_code, body=snippet,
            )
        if 500 <= status_code < 600:
            return TransientProviderError(
                f"upstream {status_code}", status_code=status_code, body=snippet,
            )
        return ProviderError(
            f"upstream error {status_code}", status_code=status_code, body=snippet,
        )


class ProviderRegistry:
    _providers: dict[str, type[Provider]] = {}

    @classmethod
    def register(cls, name: str, provider_cls: type[Provider]):
        cls._providers[name] = provider_cls

    @classmethod
    def get(cls, name: str) -> Optional[type[Provider]]:
        return cls._providers.get(name)

    @classmethod
    def list(cls) -> list[str]:
        return list(cls._providers.keys())