from __future__ import annotations

import json
from typing import AsyncIterator, Callable, Optional

import httpx

from onecode.models.provider import ChatResponse, Message, ModelResponse, Provider, ProviderRegistry


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, api_key: str = "", endpoint: str = "", **kwargs):
        self.api_key = api_key
        self._endpoint = endpoint or "https://api.anthropic.com/v1"

    def is_anthropic_style(self) -> bool:
        return True

    def prepare_messages(self, messages: list[Message]) -> list[dict]:
        """Prepare messages for Anthropic API.

        Converts OpenAI-format image blocks (image_url) to Anthropic's
        native image format (image + source).
        """
        prepared = super().prepare_messages(messages)
        for msg in prepared:
            content = msg.get("content")
            if isinstance(content, list):
                new_content = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        url = part["image_url"]["url"]
                        if url.startswith("data:"):
                            header, _, encoded = url[5:].partition(",")
                            mime = header.split(";")[0] if ";" in header else "image/png"
                            new_content.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": mime,
                                    "data": encoded,
                                },
                            })
                    else:
                        new_content.append(part)
                msg["content"] = new_content
        return prepared

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
        on_tool_call_delta: Optional[Callable[[str, str, str], None]] = None,
        **kwargs,
    ) -> ChatResponse:
        from onecode.models.errors import (
            ProviderError, TransientProviderError, retry_after_seconds,
        )
        key = self.resolve_api_key(self.api_key)
        if not key:
            raise ProviderError("API key not configured.")

        content_parts: list[str] = []
        tool_uses: list[dict] = []
        usage: dict = {}
        current_tool: Optional[dict] = None

        try:
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
                    if resp.status_code != 200:
                        error_body = await resp.aread()
                        error_text = error_body.decode("utf-8", errors="replace")
                        raise Provider.classify_http_error(
                            resp.status_code, error_text, retry_after=retry_after_seconds(resp),
                        )

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
                                        if on_tool_call_delta:
                                            partial = delta.get("partial_json", "") or ""
                                            call_id = current_tool.get("id", "")
                                            name = current_tool.get("name", "")
                                            on_tool_call_delta(call_id, name, partial)

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
        except ProviderError:
            raise
        except httpx.ConnectError as e:
            raise TransientProviderError(f"Connection error: {e}") from e
        except Exception as e:
            raise TransientProviderError(f"Error: {e}") from e

        return ChatResponse(
            content="".join(content_parts),
            tool_uses=tool_uses,
            usage=usage,
        )


ProviderRegistry.register("anthropic", AnthropicProvider)
