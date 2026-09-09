from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Callable, Optional

import httpx

from onecode.models.errors import (
    ProviderError, TransientProviderError, retry_after_seconds, safe_error_msg,
)
from onecode.models.provider import ChatResponse, Message, ModelResponse, Provider, ProviderRegistry


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self, api_key: str = "", endpoint: str = "", **kwargs):
        self.api_key = api_key
        self._endpoint = endpoint or "https://api.openai.com/v1"

    def is_anthropic_style(self) -> bool:
        return False

    def _non_system_to_dict(self, msg: Message) -> dict:
        return msg.to_multimodal_dict()

    def prepare_messages(self, messages: list[Message]) -> list[dict]:
        """Prepare messages for OpenAI API, supporting multimodal content.

        Delegates to the base hardening pipeline which handles empty-tool
        dropping, user coalescing, orphan-tool stripping, dangling
        tool_call cleanup, and system-prompt capping.
        """
        return super().prepare_messages(messages)

    async def chat(
        self, messages: list[Message], model: str = "gpt-4-turbo", **kwargs
    ) -> ModelResponse:
        key = self.resolve_api_key(self.api_key)
        if not key:
            raise ProviderError("API key not configured. Set OPENAI_API_KEY.")
        body = {
            "model": model,
            "messages": self.prepare_messages(messages),
        }
        tools = kwargs.get("tools")
        if tools:
            body["tools"] = tools
        body.update({k: v for k, v in kwargs.items() if k not in ("tools", "stream")})

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._endpoint}/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "content-type": "application/json",
                },
                json=body,
            )
            if resp.status_code != 200:
                raise Provider.classify_http_error(
                    resp.status_code, resp.text,
                    retry_after=retry_after_seconds(resp),
                )
            data = resp.json()
            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})

            content_blocks = []
            text = msg.get("content", "") or ""
            if text:
                content_blocks.append({"type": "text", "text": text})

            tool_calls = msg.get("tool_calls", [])
            for tc in tool_calls:
                func = tc.get("function", {})
                try:
                    args = json.loads(func.get("arguments", "{}"))
                except Exception:
                    args = {"raw": func.get("arguments", "")}
                if not isinstance(args, dict):
                    args = {"raw": args}
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": func.get("name", ""),
                    "input": args,
                })

            return ModelResponse(
                content=content_blocks,
                model=model,
                usage=data.get("usage", {}),
                raw=data,
            )

    async def chat_stream(
        self, messages: list[Message], model: str = "gpt-4-turbo", **kwargs
    ) -> AsyncIterator[str]:
        key = self.resolve_api_key(self.api_key)
        if not key:
            raise ProviderError("API key not configured.")
        body = {
            "model": model,
            "messages": self.prepare_messages(messages),
            "stream": True,
        }
        tools = kwargs.get("tools")
        if tools:
            body["tools"] = tools
        body.update({k: v for k, v in kwargs.items() if k not in ("tools", "stream")})

        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST",
                f"{self._endpoint}/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "content-type": "application/json",
                },
                json=body,
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

        body = {
            "model": model,
            "messages": self.prepare_messages(messages),
            "stream": True,
        }
        tools = kwargs.get("tools")
        if tools:
            body["tools"] = tools
        body.update({k: v for k, v in kwargs.items() if k not in ("tools", "stream")})

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
                    json=body,
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
                            tc_deltas = delta.get("tool_calls", [])
                            for tcd in tc_deltas:
                                idx = tcd.get("index", 0)
                                if idx not in stream_tool_calls:
                                    stream_tool_calls[idx] = {
                                        "id": tcd.get("id", ""),
                                        "name": tcd.get("function", {}).get("name", ""),
                                        "arguments": "",
                                    }
                                args_delta = tcd.get("function", {}).get("arguments", "")
                                stream_tool_calls[idx]["arguments"] += args_delta
                                if tcd.get("id"):
                                    stream_tool_calls[idx]["id"] = tcd["id"]
                                if tcd.get("function", {}).get("name"):
                                    stream_tool_calls[idx]["name"] = tcd["function"]["name"]
                                if on_tool_call_delta:
                                    call_id = stream_tool_calls[idx].get("id", "")
                                    name = stream_tool_calls[idx].get("name", "")
                                    on_tool_call_delta(call_id, name, args_delta)
        except asyncio.CancelledError:
            raise
        except ProviderError:
            raise
        except Exception as e:
            raise TransientProviderError(f"Error: {safe_error_msg(e)}") from e

        tool_uses = []
        for nt in stream_tool_calls.values():
            try:
                inp = json.loads(nt.get("arguments", "{}"))
            except (json.JSONDecodeError, TypeError):
                inp = {"raw": nt.get("arguments", "")}
            if not isinstance(inp, dict):
                inp = {"raw": inp}
            tool_uses.append({"id": nt["id"], "name": nt["name"], "input": inp})

        return ChatResponse(
            content="".join(content_parts),
            tool_uses=tool_uses,
        )


ProviderRegistry.register("openai", OpenAIProvider)
