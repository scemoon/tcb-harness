from __future__ import annotations

from typing import AsyncIterator

import httpx

from cdh.models.provider import Message, ModelResponse, Provider, ProviderRegistry


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(self, endpoint: str = "http://localhost:11434", **kwargs):
        self.endpoint = endpoint.rstrip("/")

    def is_anthropic_style(self) -> bool:
        return False

    async def chat(
        self, messages: list[Message], model: str = "llama2", **kwargs
    ) -> ModelResponse:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.endpoint}/api/chat",
                json={
                    "model": model,
                    "messages": self.prepare_messages(messages),
                    "stream": False,
                },
            )
            data = resp.json()
            return ModelResponse(
                content=[{"type": "text", "text": data.get("message", {}).get("content", "")}],
                model=model,
                usage={"total_tokens": data.get("eval_count", 0)},
                raw=data,
            )

    async def chat_stream(
        self, messages: list[Message], model: str = "llama2", **kwargs
    ) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST",
                f"{self.endpoint}/api/chat",
                json={
                    "model": model,
                    "messages": self.prepare_messages(messages),
                    "stream": True,
                },
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.strip():
                        import json
                        chunk = json.loads(line)
                        yield chunk.get("message", {}).get("content", "")
                        if chunk.get("done"):
                            break


ProviderRegistry.register("ollama", OllamaProvider)
