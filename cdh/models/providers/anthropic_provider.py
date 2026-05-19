from __future__ import annotations

from typing import AsyncIterator

import httpx

from cdh.models.provider import Message, ModelResponse, Provider, ProviderRegistry


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, api_key: str = "", **kwargs):
        self.api_key = api_key

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
                "https://api.anthropic.com/v1/messages",
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
                "https://api.anthropic.com/v1/messages",
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
                        import json
                        chunk = json.loads(line[6:])
                        if chunk.get("type") == "content_block_delta":
                            delta = chunk.get("delta", {})
                            yield delta.get("text", "")


ProviderRegistry.register("anthropic", AnthropicProvider)
