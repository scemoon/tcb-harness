from __future__ import annotations

import json
from typing import AsyncIterator, Callable, Optional

import httpx

from cdha.models.provider import ChatResponse, Message, ModelResponse, Provider, ProviderRegistry


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, api_key: str = "", endpoint: str = "", **kwargs):
        self.api_key = api_key
        self._endpoint = endpoint or "https://api.anthropic.com/v1"

    def is_anthropic_style(self) -> bool:
        return True

    async def chat(
        self, messages: list[Message], model: str = "claude-3-opus-20240229", **kwargs
    ) -> ModelResponse:
        key = self.resolve_api_key(self.api_key)
        if not key:
            return ModelResponse(
                content="API key not configured. Set ANTHROPIC_API_KEY.",
                model=model,
            )
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._endpoint}/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": kwargs.get("max_tokens", 4096),
                    "messages": self.prepare_messages(messages),
                },
            )
            data = resp.json()
            return ModelResponse(
                content=[{"type": "text", "text": data.get("content", [{}])[0].get("text", "")}],
                model=model,
                usage=data.get("usage", {}),
                raw=data,
            )

    async def chat_stream(
        self, messages: list[Message], model: str = "claude-3-opus-20240229", **kwargs
    ) -> AsyncIterator[str]:
        key = self.resolve_api_key(self.api_key)
        if not key:
            yield "API key not configured."
            return
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST",
                f"{self._endpoint}/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": kwargs.get("max_tokens", 4096),
                    "messages": self.prepare_messages(messages),
                    "stream": True,
                },
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line[6:] != "[DONE]":
                        chunk = json.loads(line[6:])
                        if chunk.get("type") == "content_block_delta":
                            delta = chunk.get("delta", {})
                            yield delta.get("text", "")

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

        content_parts: list[str] = []
        tool_uses: list[dict] = []
        usage: dict = {}
        current_tool: Optional[dict] = None

        async with httpx.AsyncClient(timeout=300) as client:
            body = {
                "model": model,
                "max_tokens": kwargs.get("max_tokens", 4096),
                "messages": self.prepare_messages(messages),
                "stream": True,
            }
            tools = kwargs.get("tools")
            if tools:
                body["tools"] = tools
            body.update({k: v for k, v in kwargs.items() if k not in ("tools", "stream", "max_tokens")})

            async with client.stream(
                "POST",
                f"{self._endpoint}/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line[6:] != "[DONE]":
                        chunk = json.loads(line[6:])
                        chunk_type = chunk.get("type", "")

                        if chunk_type == "content_block_start":
                            block = chunk.get("content_block", {})
                            if block.get("type") == "tool_use":
                                current_tool = {
                                    "id": block.get("id", ""),
                                    "name": block.get("name", ""),
                                    "input": {},
                                    "input_json": "",
                                }

                        elif chunk_type == "content_block_delta":
                            delta = chunk.get("delta", {})
                            delta_type = delta.get("type", "")
                            if delta_type == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    content_parts.append(text)
                                    if on_text_chunk:
                                        on_text_chunk(text)
                            elif delta_type == "input_json_delta":
                                if current_tool is not None:
                                    current_tool["input_json"] += delta.get("partial_json", "")

                        elif chunk_type == "content_block_stop":
                            if current_tool is not None:
                                try:
                                    current_tool["input"] = json.loads(current_tool["input_json"])
                                except (json.JSONDecodeError, TypeError):
                                    current_tool["input"] = {"raw": current_tool["input_json"]}
                                tool_uses.append({
                                    "id": current_tool["id"],
                                    "name": current_tool["name"],
                                    "input": current_tool["input"],
                                })
                                current_tool = None

                        elif chunk_type == "message_delta":
                            usage = chunk.get("usage", {})

        return ChatResponse(
            content="".join(content_parts),
            tool_uses=tool_uses,
            usage=usage,
        )


ProviderRegistry.register("anthropic", AnthropicProvider)
