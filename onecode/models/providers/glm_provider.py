from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator, Callable, Optional

import httpx

from onecode.models.errors import (
    ProviderError, TransientProviderError, retry_after_seconds, safe_error_msg,
)
from onecode.models.provider import ChatResponse, Message, ModelResponse, Provider, ProviderRegistry

logger = logging.getLogger("onecode.models.providers.glm")


class GLMProvider(Provider):
    name = "glm"

    def __init__(self, api_key: str = "", endpoint: str = "", **kwargs):
        self.api_key = api_key
        self._endpoint = endpoint or "https://open.bigmodel.cn/api/paas/v4"

    def is_anthropic_style(self) -> bool:
        return False

    async def chat(
        self, messages: list[Message], model: str = "glm-4-plus", **kwargs
    ) -> ModelResponse:
        key = self.resolve_api_key(self.api_key)
        if not key:
            raise ProviderError("API key not configured. Set GLM_API_KEY.")
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
        self, messages: list[Message], model: str = "glm-4-plus", **kwargs
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
        _n_msgs = len(messages)
        _t0 = time.monotonic()
        _first_byte_t: float | None = None
        _chunk_n = 0
        _text_n = 0
        _bytes = 0
        _on_text_cb = bool(on_text_chunk)
        logger.debug(
            "[GLM-STREAM] open model=%s msgs=%d on_text_chunk_cb=%s",
            model, _n_msgs, _on_text_cb,
        )
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
                    logger.debug(
                        "[GLM-STREAM] stream opened status=%d t=%.2fs",
                        resp.status_code, time.monotonic() - _t0,
                    )
                    async for line in resp.aiter_lines():
                        if cancel_check and cancel_check():
                            raise asyncio.CancelledError("cancelled during streaming")
                        if not line:
                            continue
                        _chunk_n += 1
                        if line.startswith("data: ") and line[6:] != "[DONE]":
                            chunk = json.loads(line[6:])
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            text = delta.get("content", "")
                            if text:
                                if _first_byte_t is None:
                                    _first_byte_t = time.monotonic() - _t0
                                    logger.debug(
                                        "[GLM-STREAM] first-byte t=%.2fs chunk#%d",
                                        _first_byte_t, _chunk_n,
                                    )
                                _text_n += 1
                                _bytes += len(text)
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
                    logger.debug(
                        "[GLM-STREAM] stream done chunks=%d text_chunks=%d "
                        "bytes=%d on_text_cb=%s t=%.2fs",
                        _chunk_n, _text_n, _bytes, _on_text_cb,
                        time.monotonic() - _t0,
                    )
        except asyncio.CancelledError:
            raise
        except ProviderError:
            raise
        except Exception as e:
            logger.exception(
                "[GLM-STREAM] EXCEPTION t=%.2fs chunks=%d text_chunks=%d: %s",
                time.monotonic() - _t0, _chunk_n, _text_n, e,
            )
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


ProviderRegistry.register("glm", GLMProvider)
