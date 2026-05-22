from __future__ import annotations

import json
from typing import AsyncIterator, Callable, Optional

import httpx

from cdh.models.provider import ChatResponse, Message, ModelResponse, Provider, ProviderRegistry


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self, api_key: str = "", **kwargs):
        self.api_key = api_key
        self._stream_tool_calls: dict[int, dict] = {}

    def is_anthropic_style(self) -> bool:
        return False

    def get_stream_tool_calls(self) -> list[dict]:
        return list(self._stream_tool_calls.values())

    async def chat(
        self, messages: list[Message], model: str = "gpt-4-turbo", **kwargs
    ) -> ModelResponse:
        key = self.resolve_api_key(self.api_key)
        if not key:
            return ModelResponse(
                content="API key not configured. Set OPENAI_API_KEY.",
                model=model,
            )
        body = {
            "model": model,
            "messages": self.prepare_messages(messages),
        }
        tools = kwargs.get("tools")
        if tools:
            body["tools"] = tools
        body.update({k: v for k, v in kwargs.items() if k != "tools"})

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "content-type": "application/json",
                },
                json=body,
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
                    args = __import__("json").loads(func.get("arguments", "{}"))
                except Exception:
                    args = {"raw": func.get("arguments", "")}
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
            yield "API key not configured."
            return
        self._stream_tool_calls = {}
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
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "content-type": "application/json",
                },
                json=body,
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line[6:] != "[DONE]":
                        import json
                        chunk = json.loads(line[6:])
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        yield delta.get("content", "")
                        tc_deltas = delta.get("tool_calls", [])
                        for tcd in tc_deltas:
                            idx = tcd.get("index", 0)
                            if idx not in self._stream_tool_calls:
                                self._stream_tool_calls[idx] = {
                                    "id": tcd.get("id", ""),
                                    "name": tcd.get("function", {}).get("name", ""),
                                    "arguments": "",
                                }
                            args_delta = tcd.get("function", {}).get("arguments", "")
                            self._stream_tool_calls[idx]["arguments"] += args_delta
                            if tcd.get("id"):
                                self._stream_tool_calls[idx]["id"] = tcd["id"]
                            if tcd.get("function", {}).get("name"):
                                self._stream_tool_calls[idx]["name"] = tcd["function"]["name"]


    async def chat_stream_response(
        self,
        messages: list[Message],
        model: str,
        on_text_chunk: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> ChatResponse:
        key = self.resolve_api_key(self.api_key)
        if not key:
            return ChatResponse(content="API key not configured.")
        self._stream_tool_calls = {}
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

        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "content-type": "application/json",
                },
                json=body,
            ) as resp:
                async for line in resp.aiter_lines():
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
                            if idx not in self._stream_tool_calls:
                                self._stream_tool_calls[idx] = {
                                    "id": tcd.get("id", ""),
                                    "name": tcd.get("function", {}).get("name", ""),
                                    "arguments": "",
                                }
                            args_delta = tcd.get("function", {}).get("arguments", "")
                            self._stream_tool_calls[idx]["arguments"] += args_delta
                            if tcd.get("id"):
                                self._stream_tool_calls[idx]["id"] = tcd["id"]
                            if tcd.get("function", {}).get("name"):
                                self._stream_tool_calls[idx]["name"] = tcd["function"]["name"]

        tool_uses = []
        for nt in self._stream_tool_calls.values():
            try:
                inp = json.loads(nt.get("arguments", "{}"))
            except (json.JSONDecodeError, TypeError):
                inp = {"raw": nt.get("arguments", "")}
            tool_uses.append({"id": nt["id"], "name": nt["name"], "input": inp})

        return ChatResponse(
            content="".join(content_parts),
            tool_uses=tool_uses,
        )


ProviderRegistry.register("openai", OpenAIProvider)
