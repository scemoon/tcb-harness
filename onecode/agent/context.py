from __future__ import annotations

import logging
from typing import Any, Optional, Union

from onecode.models.provider import (
    ContentBlock,
    ContentBlockType,
    ImageContent,
    Message as ProviderMessage,
    ToolResult as ProviderToolResult,
    ToolUse,
)

logger = logging.getLogger("onecode.context")


# ── Token estimation (model-aware, with tiktoken fallback) ──

_ENCODING_CACHE: dict[str, Any] = {}

def _get_encoding(model: str):
    if model in _ENCODING_CACHE:
        return _ENCODING_CACHE[model]
    try:
        import tiktoken
        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        _ENCODING_CACHE[model] = enc
        return enc
    except Exception:
        _ENCODING_CACHE[model] = None
        return None


def _estimate_tokens(text: str, model: str = "gpt-4") -> int:
    if not text:
        return 0
    enc = _get_encoding(model)
    if enc is not None:
        try:
            return len(enc.encode(text, disallowed_special=()))
        except Exception:
            pass
    ascii_count = sum(1 for c in text if ord(c) < 128)
    cjk_count = len(text) - ascii_count
    return max(1, int(ascii_count * 0.3 + cjk_count * 1.5))


# ── Context config ──

class ContextConfig:
    max_tokens: int = 32000
    max_messages: int = 1000
    compact_threshold: float = 0.40
    model: str = "gpt-4"


class Message:
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


def _block_text(block: Any) -> str:
    if isinstance(block, dict):
        btype = block.get("type", "")
        if btype == "resource":
            resource = block.get("resource", {})
            return resource.get("text", "") or f"[{btype}: {resource.get('mimeType', '')} {len(resource.get('blob', ''))} bytes]"
        if btype == "image":
            return f"[image: {block.get('mimeType', block.get('source', {}).get('media_type', 'unknown'))}]"
        return str(block.get("text", "") or block.get("content", ""))
    return str(block)


_ModelRegistry: Any = None

def _get_model_registry() -> Any:
    global _ModelRegistry
    if _ModelRegistry is None:
        from onecode.models.registry import ModelRegistry as MR
        _ModelRegistry = MR
    return _ModelRegistry


class ContextManager:
    def __init__(self, config: Optional[ContextConfig] = None):
        self.config = config or ContextConfig()
        self.messages: list[Message] = []
        self._token_count = 0

    def set_model(self, model: str) -> None:
        """Sync context config with the model's context window.

        Sets ``config.model`` and derives ``config.max_tokens`` from the
        model's known ``context_window`` in the registry.  Falls back to
        32000 (typical small-model window) if the model is unrecognised.
        """
        self.config.model = model
        info = _get_model_registry().get(model)
        if info is not None and info.context_window > 0:
            self.config.max_tokens = info.context_window
        else:
            self.config.max_tokens = 32000

    # -- model-aware token estimation (incremental O(1) per message) --

    def _estimate_message_tokens(self, msg: Message) -> int:
        model = self.config.model
        STRUCT_OVERHEAD = 20
        if isinstance(msg.content, str):
            return _estimate_tokens(msg.content, model) + STRUCT_OVERHEAD
        elif isinstance(msg.content, list):
            return sum(_estimate_tokens(_block_text(b), model) for b in msg.content) + STRUCT_OVERHEAD
        return STRUCT_OVERHEAD

    # -- message management (incremental token counters) --

    def add_message(self, role: str, content: Union[str, list], name: Optional[str] = None) -> None:
        if isinstance(content, list):
            block_types = [b.get("type", type(b).__name__) if isinstance(b, dict) else type(b).__name__ for b in content]
            logger.debug("add_message role=%s block_types=%s", role, block_types)
        msg = Message(role=role, content=content, name=name)
        self.messages.append(msg)
        self._token_count += self._estimate_message_tokens(msg)

    def add_system(self, content: str) -> None:
        self.add_message("system", content)

    def insert_system_before_non_system(self, content: str) -> None:
        """Insert a system message before the first non-system message.

        Use this when adding system directives during an agent turn to ensure
        they appear before user/assistant/tool messages in the message list,
        which is the ordering most LLM APIs expect.
        """
        for i, m in enumerate(self.messages):
            if m.role != "system":
                msg = Message(role="system", content=content)
                self.messages.insert(i, msg)
                self._token_count += self._estimate_message_tokens(msg)
                return
        self.add_system(content)

    def _marker_in_content(self, content: str, marker: str) -> bool:
        """Check if *marker* appears in the content.

        Markers use HTML-comment syntax (``<!-- NAME -->``) which is
        distinct enough that a plain substring check is safe.  Only
        system-role messages are checked, so user messages mentioning
        the same keyword cannot cause false matches.
        """
        return marker in content

    def replace_system_section(self, marker: str, new_content: str) -> bool:
        for m in self.messages:
            if m.role == "system" and isinstance(m.content, str) and self._marker_in_content(m.content, marker):
                old_tokens = self._estimate_message_tokens(m)
                m.content = new_content
                self._token_count += self._estimate_message_tokens(m) - old_tokens
                return True
        return False

    def remove_system_by_marker(self, marker: str) -> int:
        before = len(self.messages)
        removed_tokens = 0
        kept: list[Message] = []
        for m in self.messages:
            if m.role == "system" and isinstance(m.content, str) and self._marker_in_content(m.content, marker):
                removed_tokens += self._estimate_message_tokens(m)
            else:
                kept.append(m)
        self.messages = kept
        self._token_count -= removed_tokens
        return before - len(self.messages)

    def add_user(self, content: str | list) -> None:
        self.add_message("user", content)

    def add_assistant(self, content: str | list) -> None:
        self.add_message("assistant", content)

    def add_tool_use(self, tool_use_id: str, name: str, input_data: dict[str, Any]) -> None:
        self.add_message("assistant", [{"type": "tool_use", "id": tool_use_id, "name": name, "input": input_data}])

    def add_tool_result(self, tool_call_id: str, content: Union[str, dict, list], is_error: bool = False) -> None:
        if isinstance(content, (dict, list)):
            logger.debug("add_tool_result raw content type=%s is_error=%s call_id=%s",
                         type(content).__name__, is_error, tool_call_id)
            self.add_message("tool", content, name=tool_call_id)
        else:
            self.add_message("tool", [{"type": "tool_result", "tool_use_id": tool_call_id, "content": content, "is_error": is_error}], name=tool_call_id)

    # -- full recalibration (rare: after bulk ops) --

    def _update_token_count(self) -> None:
        total = 0
        for m in self.messages:
            total += self._estimate_message_tokens(m)
        self._token_count = total

    def should_compact(self) -> bool:
        if self.config.max_tokens <= 0:
            return False
        return self._token_count >= self.config.max_tokens * self.config.compact_threshold

    # ── Tiered compression pipeline ──

    def compact(self) -> str:
        """Apply tiered compression.

        Returns the level applied: ``"none"``, ``"light"``, ``"medium"``, or ``"heavy"``.
        """
        system_msgs = [m for m in self.messages if m.role == "system"]
        other_msgs = [m for m in self.messages if m.role != "system"]
        if not other_msgs and len(system_msgs) <= 1:
            return "none"

        threshold = self.config.max_tokens * self.config.compact_threshold

        # Tier 0 — System: truncate overly large system messages in-place.
        # This runs even with only 1-2 messages (e.g. first turn) to prevent
        # context-length errors from oversized system context.
        self._tier_compress_system_messages(system_msgs)
        if self._token_count_under(system_msgs, other_msgs, threshold):
            self.messages = system_msgs + other_msgs
            self._update_token_count()
            logger.info("compact: light — compressed system messages")
            return "light"

        # Tier 1 — Light: compress verbose tool results in-place
        self._tier_compress_tool_results(other_msgs)
        if self._token_count_under(system_msgs, other_msgs, threshold):
            self.messages = system_msgs + other_msgs
            self._update_token_count()
            logger.info("compact: light — compressed tool results + system")
            return "light"

        # Tier 2 — Medium: truncate older non-system messages
        self._tier_truncate_old(other_msgs)
        if self._token_count_under(system_msgs, other_msgs, threshold):
            self.messages = system_msgs + other_msgs
            self._update_token_count()
            logger.info("compact: medium — truncated old messages")
            return "medium"

        # Tier 3 — Heavy: full summarization, preserving last 5 structured messages
        if len(other_msgs) > 5:
            summary = self._summarize_messages(other_msgs[:-5])
            self.messages = system_msgs + [
                Message(role="system", content=f"<!-- COMPACT_SUMMARY -->\n[Previous context summarized]\n{summary}")
            ] + other_msgs[-5:]
        else:
            # For ≤5 non-system messages, summarization buys nothing (we'd keep
            # all originals anyway). Aggressively truncate each message instead.
            truncated = []
            for m in other_msgs:
                if isinstance(m.content, str):
                    truncated.append(Message(m.role, m.content[:200] + "..."))
                elif isinstance(m.content, list):
                    truncated.append(Message(m.role, "[truncated]"))
                else:
                    truncated.append(m)
            self.messages = system_msgs + truncated
        self._update_token_count()
        logger.info("compact: heavy — full summarization")
        return "heavy"

    def _token_count_under(self, system_msgs, other_msgs, threshold) -> bool:
        total = 0
        for m in system_msgs:
            total += self._estimate_message_tokens(m)
        for m in other_msgs:
            total += self._estimate_message_tokens(m)
        return total < threshold

    def _tier_compress_system_messages(self, msgs: list[Message]) -> None:
        CRITICAL_MARKERS = {
            "<!-- AGENT_CONFIG -->",
            "<!-- REACT_PHASE -->",
        }
        TRUNCATABLE_MARKERS = {
            "<!-- SKILL:",
            "<!-- AI-DLC:",
            "<!-- CODEBASE -->",
            "<!-- MEMORY -->",
            "<!-- CDH_PROJECT -->",
            "<!-- PROJECT_DOC -->",
        }
        sys_char_limit = max(4000, int(self.config.max_tokens * self.config.compact_threshold * 0.3))
        for m in msgs:
            if isinstance(m.content, str) and len(m.content) > sys_char_limit:
                if any(marker in m.content for marker in CRITICAL_MARKERS):
                    continue
                if any(marker in m.content for marker in TRUNCATABLE_MARKERS):
                    keep = sys_char_limit // 2
                    m.content = m.content[:keep] + "\n... [truncated]" + m.content[-keep:]
                else:
                    m.content = m.content[:sys_char_limit] + "\n... [system message truncated]"

    def _tier_compress_tool_results(self, msgs: list[Message]) -> None:
        for m in msgs:
            if m.role == "tool" and isinstance(m.content, list):
                for b in m.content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        content = b.get("content", "")
                        if isinstance(content, str) and len(content) > 2000:
                            b["content"] = content[:1000] + "\n... [truncated]"

    def _tier_truncate_old(self, msgs: list[Message], keep_recent: int = 20) -> None:
        if len(msgs) <= keep_recent:
            return
        for m in msgs[:-keep_recent]:
            if isinstance(m.content, str) and len(m.content) > 200:
                m.content = m.content[:200] + "..."
            elif isinstance(m.content, list):
                truncated: list = []
                for b in m.content:
                    if isinstance(b, dict):
                        btype = b.get("type", "")
                        if btype == "tool_result":
                            content = b.get("content", "")
                            if isinstance(content, str) and len(content) > 300:
                                b = dict(b, content=content[:300] + "... [truncated]")
                            truncated.append(b)
                        elif btype == "tool_use":
                            truncated.append(b)
                        elif btype == "thinking":
                            truncated.append(b)
                        else:
                            continue
                if truncated:
                    m.content = truncated
                else:
                    m.content = "[truncated]"

    def _summarize_messages(self, msgs: list[Message]) -> str:
        content_parts = []
        for m in msgs[-30:]:
            prefix = {"user": "User", "assistant": "Assistant", "tool": "Tool"}.get(m.role, m.role)
            if isinstance(m.content, str):
                content_parts.append(f"{prefix}: {m.content[:800]}")
            elif isinstance(m.content, list):
                texts = []
                for b in m.content:
                    if isinstance(b, dict):
                        btype = b.get("type", "")
                        if btype == "tool_use":
                            texts.append(f"[call {b.get('name', '?')}]")
                        elif btype == "tool_result":
                            texts.append(f"[result: {str(b.get('content', ''))[:300]}]")
                        else:
                            texts.append(_block_text(b)[:300])
                    else:
                        texts.append(str(b)[:300])
                content_parts.append(f"{prefix}: {' | '.join(texts)[:800]}")
        return "\n".join(content_parts[-20:])

    def get_context(self) -> list:
        def _is_image_mime(mime: str) -> bool:
            return mime and mime.startswith("image/")

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
                    elif btype == "resource":
                        resource = block.get("resource", {})
                        uri = resource.get("uri", "")
                        mime = resource.get("mimeType", "")
                        if resource.get("text") is not None:
                            blocks.append(ContentBlock(
                                type=ContentBlockType.TEXT,
                                text=f"\n\n[File: {uri}]({mime})\n```\n{resource['text']}\n```\n",
                            ))
                        elif resource.get("blob") and _is_image_mime(mime):
                            blocks.append(ContentBlock(
                                type=ContentBlockType.IMAGE,
                                image=ImageContent(
                                    data=resource["blob"],
                                    mime_type=mime,
                                ),
                            ))
                        elif resource.get("blob"):
                            blocks.append(ContentBlock(
                                type=ContentBlockType.TEXT,
                                text=f"\n\n[Attachment: {uri}]({mime})\n[Binary data, {len(resource['blob'])} base64 bytes]\n",
                            ))
                    elif btype == "image":
                        data = block.get("data", block.get("source", {}).get("data", ""))
                        mime = block.get("mimeType", block.get("source", {}).get("media_type", "image/png"))
                        blocks.append(ContentBlock(
                            type=ContentBlockType.IMAGE,
                            image=ImageContent(data=data, mime_type=mime),
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
