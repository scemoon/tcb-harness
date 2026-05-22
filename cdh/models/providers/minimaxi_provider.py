from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

import httpx

from cdh.models.provider import Message, ModelResponse, Provider, ProviderRegistry

logger = logging.getLogger("cdh.provider.minimaxi")

LOG_DIR = Path.home() / ".cloud-dev-harness" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _log_request(model: str, messages: list, response_data: dict = None, error: str = None):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    log_file = LOG_DIR / f"minimaxi_{timestamp}.json"
    log_entry = {
        "timestamp": timestamp,
        "model": model,
        "messages": [{"role": m.role, "content": m.to_api_content()} for m in messages],
        "response": response_data,
        "error": error,
    }
    try:
        with open(log_file, "w") as f:
            json.dump(log_entry, f, indent=2, ensure_ascii=False)
        logger.info(f"Request logged to {log_file}")
    except Exception as e:
        logger.error(f"Failed to write log: {e}")
    return log_file


class MiniMaxiProvider(Provider):
    name = "minimaxi"

    def __init__(self, api_key: str = "", endpoint: str = "", **kwargs):
        self.api_key = api_key
        self._endpoint = endpoint or "https://api.minimaxi.com/v1"
        self._request_count = 0

    def is_anthropic_style(self) -> bool:
        return False

    async def chat(
        self, messages: list[Message], model: str = "MiniMax-M2.7", **kwargs
    ) -> ModelResponse:
        self._request_count += 1
        req_id = f"req_{self._request_count}_{int(time.time())}"
        logger.info(f"[{req_id}] chat() called with model={model}, messages={len(messages)}")

        key = self.resolve_api_key(self.api_key)
        logger.info(f"[{req_id}] API key resolved: {'Yes' if key else 'No'}, key_prefix: '{key[:15]}...' if key else 'None'")

        if not key:
            error_msg = "API key not configured. Set MINMAXI_API_KEY."
            _log_request(model, messages, error=error_msg)
            return ModelResponse(content=[{"type": "text", "text": error_msg}], model=model)

        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                logger.info(f"[{req_id}] Sending request to {self._endpoint}/chat/completions")
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
                elapsed = time.time() - start_time
                logger.info(f"[{req_id}] Response status: {resp.status_code}, elapsed: {elapsed:.2f}s")

                data = resp.json()
                choice = data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "")

                _log_request(model, messages, response_data=data)
                logger.info(f"[{req_id}] Response content length: {len(content)}")

                return ModelResponse(
                    content=[{"type": "text", "text": content}],
                    model=model,
                    usage=data.get("usage", {}),
                    raw=data,
                )
        except httpx.ConnectError as e:
            error_msg = f"Connection error: {e}"
            logger.error(f"[{req_id}] {error_msg}")
            _log_request(model, messages, error=error_msg)
            return ModelResponse(content=[{"type": "text", "text": f"Connection error: {e}"}], model=model)
        except Exception as e:
            error_msg = f"Error: {e}"
            logger.exception(f"[{req_id}] {error_msg}")
            _log_request(model, messages, error=error_msg)
            return ModelResponse(content=[{"type": "text", "text": f"Error: {e}"}], model=model)

    async def chat_stream(
        self, messages: list[Message], model: str = "MiniMax-M2.7", **kwargs
    ) -> AsyncIterator[str]:
        self._request_count += 1
        req_id = f"req_{self._request_count}_{int(time.time())}"
        logger.info(f"[{req_id}] chat_stream() called with model={model}, messages={len(messages)}")

        key = self.resolve_api_key(self.api_key)
        logger.info(f"[{req_id}] API key resolved: {'Yes' if key else 'No'}, key_prefix: '{key[:15]}...' if key else 'None'")

        if not key:
            error_msg = "API key not configured."
            _log_request(model, messages, error=error_msg)
            yield error_msg
            return

        start_time = time.time()
        full_content = []
        response_data = None

        try:
            async with httpx.AsyncClient(timeout=300) as client:
                logger.info(f"[{req_id}] Sending stream request to {self._endpoint}/chat/completions")
                logger.info(f"[{req_id}] Request: model={model}, messages_count={len(messages)}")

                async with client.stream(
                    "POST",
                    f"{self._endpoint}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": self.prepare_messages(messages),
                        "stream": True,
                    },
                ) as resp:
                    logger.info(f"[{req_id}] Stream response status: {resp.status_code}")
                    if resp.status_code != 200:
                        error_body = await resp.aread()
                        error_text = error_body.decode("utf-8", errors="replace")
                        logger.error(f"[{req_id}] Stream error HTTP {resp.status_code}: {error_text[:1000]}")
                        _log_request(model, messages, error=f"HTTP {resp.status_code}: {error_text[:500]}")
                        yield f"API Error {resp.status_code}: {error_text[:200]}"
                        return

                    async for line in resp.aiter_lines():
                        if line.startswith("data: ") and line[6:] != "[DONE]":
                            try:
                                chunk = json.loads(line[6:])
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    full_content.append(content)
                                    yield content
                            except json.JSONDecodeError as e:
                                logger.warning(f"[{req_id}] JSON decode error: {e}, line: {line[:100]}")
                        elif line.startswith("data: [DONE]"):
                            pass

                elapsed = time.time() - start_time
                logger.info(f"[{req_id}] Stream complete, elapsed: {elapsed:.2f}s, chars: {len(full_content)}")
                response_data = {"stream": True, "full_content_length": len(full_content)}
        except httpx.ConnectError as e:
            error_msg = f"Connection error: {e}"
            logger.error(f"[{req_id}] {error_msg}")
            _log_request(model, messages, error=error_msg)
            yield error_msg
            return
        except Exception as e:
            error_msg = f"Error: {e}"
            logger.exception(f"[{req_id}] {error_msg}")
            _log_request(model, messages, error=error_msg)
            yield error_msg
            return

        _log_request(model, messages, response_data=response_data)


ProviderRegistry.register("minimaxi", MiniMaxiProvider)