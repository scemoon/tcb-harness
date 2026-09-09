from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Callable, Optional

import httpx

from onecode.models.errors import (
    ProviderError, TransientProviderError, retry_after_seconds, safe_error_msg,
)
from onecode.models.provider import ChatResponse, Message, ModelResponse, Provider, ProviderRegistry


class MiniMaxProvider(Provider):
    name = "minimax"

    def __init__(self, api_key: str = "", endpoint: str = "", **kwargs):
        self.api_key = api_key
        self._endpoint = endpoint or "https://api.minimax.com/v1"

    def is_anthropic_style(self) -> bool:
        return False

    def supports_native_tools(self) -> bool:
        return False

    async def chat(
        self, messages: list[Message], model: str = "MiniMax-M2.7", **kwargs
    ) -> ModelResponse:
        key = self.resolve_api_key(self.api_key)
        if not key:
            raise ProviderError("API key not configured. Set MINIMAX_API_KEY.")
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._endpoint}/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "messages": self.prepare_messages(messages),
                    **{k: v for k, v in kwargs.items() if k != "stream"},
                },
            )
            if resp.status_code != 200:
                raise Provider.classify_http_error(
                    resp.status_code, resp.text,
                    retry_after=retry_after_seconds(resp),
                )
            data = resp.json()
            choice = data.get("choices", [{}])[0]
            return ModelResponse(
                content=[{"type": "text", "text": choice.get("message", {}).get("content", "")}],
                model=model,
                usage=data.get("usage", {}),
                raw=data,
            )

    async def chat_stream(
        self, messages: list[Message], model: str = "MiniMax-M2.7", **kwargs
    ) -> AsyncIterator[str]:
        key = self.resolve_api_key(self.api_key)
        if not key:
            raise ProviderError("API key not configured.")
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST",
                f"{self._endpoint}/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "messages": self.prepare_messages(messages),
                    "stream": True,
                    **{k: v for k, v in kwargs.items() if k != "stream"},
                },
            ) as resp:
                if resp.status_code != 200:
                    error_body = await resp.aread()
                    raise Provider.classify_http_error(
                        resp.status_code, error_body.decode("utf-8", errors="replace"),
                        retry_after=retry_after_seconds(resp),
                    )
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line[6:] != "[DONE]":
                        chunk = json.loads(line[6:])
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        yield delta.get("content", "")

    async def chat_stream_response(
        self,
        messages: list[Message],
        model: str,
        on_text_chunk: Optional[Callable[[str], None]] = None,
        on_tool_call_delta: Optional[Callable[[str, str, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        **kwargs,
    ) -> ChatResponse:
        key = self.resolve_api_key(self.api_key)
        if not key:
            raise ProviderError("API key not configured.")
        if cancel_check and cancel_check():
            raise asyncio.CancelledError("cancelled before chat_stream_response")
        content_parts: list[str] = []
        stream_tool_calls: dict[int, dict] = {}
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream(
                    "POST",
                    f"{self._endpoint}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": self.prepare_messages(messages),
                        "stream": True,
                        **{k: v for k, v in kwargs.items() if k != "stream"},
                    },
                ) as resp:
                    if resp.status_code != 200:
                        error_body = await resp.aread()
                        raise Provider.classify_http_error(
                            resp.status_code, error_body.decode("utf-8", errors="replace"),
                            retry_after=retry_after_seconds(resp),
                        )
                    async for line in resp.aiter_lines():
                        if cancel_check and cancel_check():
                            raise asyncio.CancelledError("cancelled during streaming")
                        if line.startswith("data: ") and line[6:] != "[DONE]":
                            chunk = json.loads(line[6:])
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            text = delta.get("content", "")
                            if text:
                                content_parts.append(text)
                                if on_text_chunk:
                                    on_text_chunk(text)
                            for tcd in delta.get("tool_calls", []) or []:
                                idx = tcd.get("index", 0)
                                slot = stream_tool_calls.setdefault(
                                    idx,
                                    {"id": "", "name": "", "arguments": ""},
                                )
                                if tcd.get("id"):
                                    slot["id"] = tcd["id"]
                                fn = tcd.get("function", {}) or {}
                                if fn.get("name"):
                                    slot["name"] = fn["name"]
                                args_delta = fn.get("arguments", "") or ""
                                slot["arguments"] += args_delta
                                if on_tool_call_delta:
                                    on_tool_call_delta(slot.get("id", ""), slot.get("name", ""), args_delta)
        except asyncio.CancelledError:
            raise
        except ProviderError:
            raise
        except Exception as e:
            raise TransientProviderError(f"Error: {safe_error_msg(e)}") from e
        tool_uses = []
        for slot in stream_tool_calls.values():
            name = slot.get("name") or ""
            if not name:
                continue
            raw_args = slot.get("arguments") or ""
            try:
                inp: dict = json.loads(raw_args) if raw_args else {}
            except (json.JSONDecodeError, TypeError):
                inp = {"raw": raw_args}
            if not isinstance(inp, dict):
                inp = {"raw": inp}
            tool_uses.append(
                {"id": slot.get("id") or "", "name": name, "input": inp}
            )
        return ChatResponse(content="".join(content_parts), tool_uses=tool_uses)


ProviderRegistry.register("minimax", MiniMaxProvider)
