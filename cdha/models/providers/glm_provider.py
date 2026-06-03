from __future__ import annotations

import json
from typing import AsyncIterator, Callable, Optional

import httpx

from cdha.models.provider import ChatResponse, Message, ModelResponse, Provider, ProviderRegistry


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
            return ModelResponse(
                content="API key not configured. Set GLM_API_KEY.",
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
        self, messages: list[Message], model: str = "glm-4-plus", **kwargs
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
                        **kwargs,
                    },
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
        except Exception as e:
            return ChatResponse(content=f"Error: {e}")
        return ChatResponse(content="".join(content_parts))


ProviderRegistry.register("glm", GLMProvider)
