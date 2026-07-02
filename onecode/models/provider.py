from __future__ import annotations

from __future__ import annotations

import asyncio
import logging
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
    IMAGE = "image"
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
class ImageContent:
    data: str  # base64-encoded image data
    mime_type: str = "image/png"


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
    image: Optional[ImageContent] = None
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

    def add_image(self, data: str, mime_type: str = "image/png") -> None:
        self.content.append(ContentBlock(
            type=ContentBlockType.IMAGE,
            image=ImageContent(data=data, mime_type=mime_type),
        ))

    def add_thinking(self, thinking: str) -> None:
        self.content.append(ContentBlock(type=ContentBlockType.THINKING, thinking=thinking))

    def add_tool_use(self, tool_use: ToolUse) -> None:
        self.content.append(ContentBlock(type=ContentBlockType.TOOL_USE, tool_use=tool_use))

    def add_tool_result(self, tool_result: ToolResult) -> None:
        self.content.append(ContentBlock(type=ContentBlockType.TOOL_RESULT, tool_result=tool_result))

    def to_api_content(self) -> str:
        """Serialize text/thinking content for API calls.

        For image blocks, includes a placeholder describing the image
        so non-vision providers still get context about attached images.
        """
        parts = []
        for cb in self.content:
            if cb.type == ContentBlockType.TEXT and cb.text:
                parts.append(cb.text)
            elif cb.type == ContentBlockType.THINKING and cb.thinking:
                parts.append(cb.thinking)
            elif cb.type == ContentBlockType.IMAGE and cb.image:
                parts.append(f"[Image: {cb.image.mime_type}]")
        return "\n".join(parts)

    def to_api_dict(self) -> dict:
        """Serialize to OpenAI-compatible message dict (text-only).

        For vision-capable providers, use to_multimodal_dict() to include
        image content as content parts.
        """
        text = self.to_api_content()
        msg: dict = {"role": self.role}
        msg["content"] = text if text else None

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

    def to_multimodal_dict(self) -> dict:
        """Serialize to OpenAI-compatible message dict with image content.

        Returns content as a list of parts (text + image_url) for vision
        API calls. Falls back to to_api_dict() when no images are present.
        """
        has_image = any(cb.type == ContentBlockType.IMAGE and cb.image for cb in self.content)
        if not has_image:
            return self.to_api_dict()

        content_parts: list[dict] = []
        for cb in self.content:
            if cb.type == ContentBlockType.TEXT and cb.text:
                content_parts.append({"type": "text", "text": cb.text})
            elif cb.type == ContentBlockType.IMAGE and cb.image:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{cb.image.mime_type};base64,{cb.image.data}",
                    },
                })

        msg: dict = self.to_api_dict()
        msg["content"] = content_parts
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
                    elif cb_type == ContentBlockType.IMAGE:
                        source = item.get("source", {})
                        self.content.append(ContentBlock(
                            type=cb_type,
                            image=ImageContent(
                                data=source.get("data", item.get("data", "")),
                                mime_type=source.get("media_type", item.get("mimeType", "image/png")),
                            ),
                        ))
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

    _prep_logger = logging.getLogger("onecode.provider.prepare")

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
        from onecode.config import resolve_env

        if key and key.startswith("${"):
            return resolve_env(key)
        return key or ""

    def prepare_messages(self, messages: list["Message"]) -> list[dict]:
        """Prepare messages for API call. Handles tool, tool_use, tool_result blocks properly.

        Hardening applied before serialization:
        1. Drop ``tool`` messages with empty content and no ``tool_call_id``
           (the OpenAI-compatible API rejects these with HTTP 400).
        2. Coalesce runs of consecutive identical ``user`` content into one
           message (some MiniMax gateways reject back-to-back duplicates).
        3. Cap the combined system-prompt length at 32 KiB, keeping the
           highest-priority blocks (``AGENT_CONFIG`` → ``REACT_PHASE`` →
           newest skills) and dropping older skill bodies first.
        4. Drop ``tool`` messages whose ``tool_call_id`` is not present in
           the immediately preceding assistant message's ``tool_calls`` —
           the MiniMax gateway returns ``(2013) tool call result does not
           follow tool call`` otherwise.
        5. When a tool message is dropped (empty or orphan), also strip
           the matching ``tool_call`` entry from the *owning* assistant
           message — i.e. the assistant that originally emitted that
           ``tool_call.id``.  Without this, the request still contains
           an ``assistant.tool_calls`` reference with no following
           ``tool`` result, which MiniMax rejects with the same (2013)
           error (``tool call and result not match`` in the stricter
           validator).  Tracking is per-id, not per-last-assistant, so
           drops that span multiple turns (e.g. an empty result from
           turn 1 and a legitimate one from turn 2) are each routed
           back to the right assistant.
        """
        _SYSTEM_CAP_BYTES = 32 * 1024
        log = Provider._prep_logger
        dropped_empty_tools = 0
        dropped_orphan_tools = 0
        coalesced_user_msgs = 0

        system_parts: list[tuple[str, str]] = []  # (marker, body)
        non_system: list[dict] = []

        for m in messages:
            if m.role == "system":
                body = m.to_api_content()
                marker = ""
                if "<!-- AGENT_CONFIG -->" in body:
                    marker = "AGENT_CONFIG"
                elif "<!-- REACT_PHASE -->" in body:
                    marker = "REACT_PHASE"
                elif "<!-- SKILL:" in body:
                    marker = "SKILL"
                elif "<!-- CDH_PROJECT -->" in body:
                    marker = "CDH_PROJECT"
                if body:
                    system_parts.append((marker, body))
            elif m.role == "tool":
                api = m.to_api_dict()
                has_id = bool(api.get("tool_call_id"))
                has_content = bool((api.get("content") or "").strip())
                if not has_id or not has_content:
                    dropped_empty_tools += 1
                    log.debug(
                        "prepare_messages: dropped empty tool message (id=%r content_len=%d)",
                        api.get("tool_call_id"),
                        len(api.get("content") or ""),
                    )
                    continue
                non_system.append(api)
            else:
                non_system.append(m.to_api_dict())

        coalesced: list[dict] = []
        for msg in non_system:
            if (
                msg.get("role") == "user"
                and coalesced
                and coalesced[-1].get("role") == "user"
                and (msg.get("content") or "") == (coalesced[-1].get("content") or "")
                and not msg.get("tool_calls")
                and not coalesced[-1].get("tool_calls")
            ):
                coalesced_user_msgs += 1
                continue
            coalesced.append(msg)
        non_system = coalesced

        # First pass: walk messages, drop orphan tool messages, and build
        # a per-id map of ``tc_id -> owning assistant index`` so we know
        # exactly which assistant emitted each ``tool_call`` entry.
        linked: list[dict] = []
        last_assistant_tc_ids: set[str] = set()
        # Maps tool_call.id -> index in ``linked`` of the assistant that
        # currently owns it.  Rebuilt whenever a new assistant message
        # is appended (matches the same reset semantics as
        # ``last_assistant_tc_ids``).
        tc_owner: dict[str, int] = {}
        for msg in non_system:
            if msg.get("role") == "tool":
                tcid = msg.get("tool_call_id") or ""
                if tcid not in last_assistant_tc_ids:
                    dropped_orphan_tools += 1
                    log.debug(
                        "prepare_messages: dropped orphan tool message "
                        "(tool_call_id=%r not in preceding assistant.tool_calls)",
                        tcid,
                    )
                    continue
                linked.append(msg)
                continue
            new_index = len(linked)
            linked.append(msg)
            if msg.get("role") == "assistant":
                last_assistant_tc_ids = {
                    tc.get("id") for tc in (msg.get("tool_calls") or []) if tc.get("id")
                }
                for tc in msg.get("tool_calls") or []:
                    tcid = tc.get("id")
                    if tcid:
                        tc_owner[tcid] = new_index
            else:
                last_assistant_tc_ids = set()
        non_system = linked

        # Second pass: any tool_call whose matching tool message was
        # dropped (empty content caught above, or otherwise missing)
        # must be removed from the *owning* assistant message — not just
        # the last assistant.  We do this in two steps:
        #   1. Walk the full list and collect every tool_call_id that
        #      appears in any tool message — these are the "seen" ids.
        #   2. Walk again and, for each assistant message, find any
        #      tool_call.id that is NOT in the seen set.  Those are
        #      dangling entries that must be stripped.
        seen_tool_ids: set[str] = set()
        for msg in non_system:
            if msg.get("role") == "tool":
                tcid = msg.get("tool_call_id") or ""
                if tcid:
                    seen_tool_ids.add(tcid)

        dangling: dict[int, set[str]] = {}
        for msg in non_system:
            if msg.get("role") != "assistant":
                continue
            tcs = msg.get("tool_calls") or []
            if not tcs:
                continue
            for tc in tcs:
                tcid = tc.get("id") or ""
                if tcid and tcid not in seen_tool_ids:
                    owner_idx = tc_owner.get(tcid)
                    if owner_idx is not None:
                        dangling.setdefault(owner_idx, set()).add(tcid)
        # Also strip tool_call entries with an empty id — those can
        # never be matched to a tool result and would be silently
        # dangling.  This mirrors the upstream filter in the first-pass
        # tool tracking (``if tc.get("id")`` / ``if tcid``).
        for msg in non_system:
            if msg.get("role") != "assistant":
                continue
            tcs = msg.get("tool_calls") or []
            if not tcs:
                continue
            kept = [tc for tc in tcs if tc.get("id")]
            if len(kept) < len(tcs):
                log.debug(
                    "prepare_messages: stripped %d empty-id tool_call entr%s "
                    "from assistant message",
                    len(tcs) - len(kept),
                    "y" if len(tcs) - len(kept) == 1 else "ies",
                )
                if kept:
                    msg["tool_calls"] = kept
                else:
                    msg.pop("tool_calls", None)

        # Apply the cleanup: strip dangling tool_call entries.  Empty
        # ``tool_calls`` lists are removed entirely.
        if dangling:
            total_stripped = 0
            for idx, ids in dangling.items():
                assistant_msg = non_system[idx]
                tcs = assistant_msg.get("tool_calls") or []
                kept = [tc for tc in tcs if (tc.get("id") or "") not in ids]
                stripped = len(tcs) - len(kept)
                if stripped:
                    total_stripped += stripped
                    log.debug(
                        "prepare_messages: stripped %d dangling tool_call entr%s "
                        "from assistant message idx=%d (ids=%r)",
                        stripped,
                        "y" if stripped == 1 else "ies",
                        idx,
                        sorted(ids),
                    )
                    if kept:
                        assistant_msg["tool_calls"] = kept
                    else:
                        assistant_msg.pop("tool_calls", None)
            if total_stripped:
                log.info(
                    "prepare_messages(%s): stripped %d dangling tool_call entr%s across %d assistant message(s)",
                    self.name or "?",
                    total_stripped,
                    "y" if total_stripped == 1 else "ies",
                    len(dangling),
                )

        if dropped_empty_tools or dropped_orphan_tools or coalesced_user_msgs:
            log.info(
                "prepare_messages(%s): dropped empty_tools=%d orphan_tools=%d "
                "coalesced_user=%d (input=%d output=%d)",
                self.name or "?",
                dropped_empty_tools,
                dropped_orphan_tools,
                coalesced_user_msgs,
                len(messages),
                len(non_system) + (1 if system_parts else 0),
            )

        combined_system = ""
        if system_parts:
            combined_parts = [body for _, body in system_parts]
            combined_system = "\n\n".join(combined_parts)
            if len(combined_system.encode("utf-8")) > _SYSTEM_CAP_BYTES:
                priority = {"AGENT_CONFIG": 0, "REACT_PHASE": 1, "CDH_PROJECT": 2, "SKILL": 3}
                ordered = sorted(
                    range(len(system_parts)),
                    key=lambda i: (priority.get(system_parts[i][0], 9), -i),
                )
                kept_indices: set[int] = set()
                running = 0
                for idx in ordered:
                    marker, body = system_parts[idx]
                    size = len(body.encode("utf-8")) + 2
                    if marker == "AGENT_CONFIG":
                        kept_indices.add(idx)
                        running = max(running, size)
                        continue
                    if running + size <= _SYSTEM_CAP_BYTES:
                        kept_indices.add(idx)
                        running += size
                kept = [body for i, body in enumerate(combined_parts) if i in kept_indices]
                if not any("<!-- AGENT_CONFIG -->" in b for b in kept) and system_parts:
                    kept.insert(0, system_parts[0][1])
                combined_system = "\n\n".join(kept).encode("utf-8")[:_SYSTEM_CAP_BYTES].decode("utf-8", errors="ignore")

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
            if not isinstance(args, dict):
                args = {"raw": args}
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
        on_tool_call_delta: Optional[Callable[[str, str, str], None]] = None,
        **kwargs,
    ) -> ChatResponse:
        """Stream with structured ChatResponse return (Clawd-Code style).

        Default implementation: falls back to chat() for providers that
        don't implement structured streaming.
        """
        logging.getLogger("onecode.models.provider").warning(
            "[PROVIDER-STREAM] %s does not override chat_stream_response — "
            "falling back to non-streaming chat() (on_text_chunk will NOT fire)",
            type(self).__name__,
        )
        response = await asyncio.wait_for(
            self.chat(messages, model=model, **kwargs),
            timeout=300,
        )
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
        from onecode.models.errors import (
            AuthError,
            ContextLengthError,
            ProviderError,
            RateLimitError,
            TransientProviderError,
        )
        snippet = (body or "").strip()
        body_excerpt = snippet[:200] if snippet else ""
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
            msg = f"upstream {status_code}: {body_excerpt}" if body_excerpt else f"upstream {status_code}"
            return TransientProviderError(
                msg, status_code=status_code, body=snippet,
            )
        msg = f"upstream error {status_code}: {body_excerpt}" if body_excerpt else f"upstream error {status_code}"
        return ProviderError(
            msg, status_code=status_code, body=snippet,
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