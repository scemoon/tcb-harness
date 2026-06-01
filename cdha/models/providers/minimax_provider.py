from __future__ import annotations

from typing import AsyncIterator

import httpx

from cdha.models.provider import Message, ModelResponse, Provider, ProviderRegistry


class MiniMaxProvider(Provider):
    name = "minimax"

    def __init__(self, api_key: str = "", endpoint: str = "", **kwargs):
        self.api_key = api_key
        self._endpoint = endpoint or "https://api.minimax.com/v1"

    def is_anthropic_style(self) -> bool:
        return False

    async def chat(
        self, messages: list[Message], model: str = "MiniMax-M2.7", **kwargs
    ) -> ModelResponse:
        key = self.resolve_api_key(self.api_key)
        if not key:
            return ModelResponse(
                content="API key not configured. Set MINIMAX_API_KEY.",
                model=model,
            )
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
                    **kwargs,
                },
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
            yield "API key not configured."
            return
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
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line[6:] != "[DONE]":
                        import json
                        chunk = json.loads(line[6:])
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        yield delta.get("content", "")


ProviderRegistry.register("minimax", MiniMaxProvider)
