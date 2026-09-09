from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Callable, Optional

import httpx

from onecode.models.errors import (
    ProviderError, TransientProviderError, safe_error_msg,
)
from onecode.models.provider import ChatResponse, Message, ModelResponse, Provider, ProviderRegistry
from onecode.models.ollama_manager import OllamaManager


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(
        self,
        endpoint: str = "http://localhost:11434",
        auto_download: bool = True,
        auto_select: bool = True,
        **kwargs,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.auto_download = auto_download
        self.auto_select = auto_select
        self._manager = OllamaManager(endpoint=endpoint)

    def is_anthropic_style(self) -> bool:
        return False

    def supports_native_tools(self) -> bool:
        return False

    def _get_effective_model(self, model: str, installed: dict) -> str:
        if self.auto_select and model not in installed:
            hardware = self._manager.detect_hardware()
            recommended = self._manager.recommend(hardware)
            if recommended and recommended not in installed:
                print(f"\n⚡ 自动选择模型 {recommended}（基于硬件配置 {hardware.total_memory_gb}GB）")
                return recommended
            elif recommended and recommended in installed:
                return recommended
        return model

    async def _ensure_model(self, model: str) -> str:
        if not await self._manager.check_running():
            raise ProviderError(
                "Ollama 服务未运行\n"
                "安装: curl -fsSL https://ollama.com/install.sh | sh\n"
                "启动: ollama serve"
            )

        installed = await self._manager.list_installed()
        effective_model = self._get_effective_model(model, installed)

        if effective_model not in installed:
            if self.auto_download:
                spec = self._manager.get_spec(effective_model)
                if spec:
                    print(f"\n📥 首次使用，正在下载模型 {effective_model} ({spec['description']})...")
                else:
                    print(f"\n📥 首次使用，正在下载模型 {effective_model}...")
                await self._manager.pull_model(effective_model)
                print(f"✅ 模型 {effective_model} 下载完成\n")
            else:
                raise ProviderError(
                    f"模型 {effective_model} 未安装\n"
                    "请先下载模型或启用自动下载"
                )

        return effective_model

    async def chat(
        self, messages: list[Message], model: str = "llama2", **kwargs
    ) -> ModelResponse:
        effective_model = await self._ensure_model(model)
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.endpoint}/api/chat",
                json={
                    "model": effective_model,
                    "messages": self.prepare_messages(messages),
                    "stream": False,
                },
            )
            if resp.status_code != 200:
                raise ProviderError(
                    f"Ollama returned HTTP {resp.status_code}",
                    status_code=resp.status_code,
                    body=resp.text,
                )
            data = resp.json()
            return ModelResponse(
                content=[{"type": "text", "text": data.get("message", {}).get("content", "")}],
                model=effective_model,
                usage={"total_tokens": data.get("eval_count", 0)},
                raw=data,
            )

    async def chat_stream(
        self, messages: list[Message], model: str = "llama2", **kwargs
    ) -> AsyncIterator[str]:
        effective_model = await self._ensure_model(model)
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST",
                f"{self.endpoint}/api/chat",
                json={
                    "model": effective_model,
                    "messages": self.prepare_messages(messages),
                    "stream": True,
                },
            ) as resp:
                if resp.status_code != 200:
                    error_body = await resp.aread()
                    raise ProviderError(
                        f"Ollama returned HTTP {resp.status_code}",
                        status_code=resp.status_code,
                        body=error_body.decode("utf-8", errors="replace"),
                    )
                async for line in resp.aiter_lines():
                    if line.strip():
                        chunk = json.loads(line)
                        yield chunk.get("message", {}).get("content", "")
                        if chunk.get("done"):
                            break

    async def chat_stream_response(
        self,
        messages: list[Message],
        model: str,
        on_text_chunk: Optional[Callable[[str], None]] = None,
        on_tool_call_delta: Optional[Callable[[str, str, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        **kwargs,
    ) -> ChatResponse:
        if cancel_check and cancel_check():
            raise asyncio.CancelledError("cancelled before chat_stream_response")
        effective_model = await self._ensure_model(model)
        content_parts: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream(
                    "POST",
                    f"{self.endpoint}/api/chat",
                    json={
                        "model": effective_model,
                        "messages": self.prepare_messages(messages),
                        "stream": True,
                    },
                ) as resp:
                    if resp.status_code != 200:
                        error_body = await resp.aread()
                        raise ProviderError(
                            f"Ollama returned HTTP {resp.status_code}",
                            status_code=resp.status_code,
                            body=error_body.decode("utf-8", errors="replace"),
                        )
                    async for line in resp.aiter_lines():
                        if cancel_check and cancel_check():
                            raise asyncio.CancelledError("cancelled during streaming")
                        if line.strip():
                            chunk = json.loads(line)
                            text = chunk.get("message", {}).get("content", "")
                            if text:
                                content_parts.append(text)
                                if on_text_chunk:
                                    on_text_chunk(text)
                            if chunk.get("done"):
                                break
        except asyncio.CancelledError:
            raise
        except ProviderError:
            raise
        except Exception as e:
            raise TransientProviderError(f"Error: {safe_error_msg(e)}") from e
        return ChatResponse(content="".join(content_parts))


ProviderRegistry.register("ollama", OllamaProvider)
