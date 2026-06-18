from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Callable, Optional

import httpx

from onecode.models.errors import (
    ProviderError, TransientProviderError, retry_after_seconds,
)
from onecode.models.provider import ChatResponse, Message, ModelResponse, Provider, ProviderRegistry

logger = logging.getLogger("onecode.provider.minimaxi")

LOG_DIR = Path.home() / ".onecode" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _raise_for_status(resp: httpx.Response, body_text: str = "") -> None:
    """Raise a :class:`ProviderError` subclass if ``resp.status_code`` is not 2xx.

    Falls back to :class:`TransientProviderError` for 5xx, and to the
    specific :class:`RateLimitError` / :class:`AuthError` /
    :class:`ContextLengthError` subclasses when the body matches.
    Callers *must* provide ``body_text`` for streaming responses (e.g.
    after calling ``await resp.aread()``).
    """
    if 200 <= resp.status_code < 300:
        return
    if not body_text:
        body_text = resp.text
    raise Provider.classify_http_error(
        resp.status_code,
        body_text,
        retry_after=retry_after_seconds(resp),
    )


def _accumulate_tool_call_delta(
    slot: dict, tcd: dict
) -> None:
    """Fold a single OpenAI-style ``delta.tool_calls`` entry into ``slot``.

    Extracted so the streaming parser and unit tests can share one
    implementation.  Mutates ``slot`` in place.
    """
    if tcd.get("id"):
        slot["id"] = tcd["id"]
    fn = tcd.get("function", {}) or {}
    if fn.get("name"):
        slot["name"] = fn["name"]
    slot["arguments"] += fn.get("arguments", "") or ""


def _finalize_stream_tool_calls(
    stream_tool_calls: dict[int, dict],
) -> list[dict]:
    """Convert accumulated OpenAI-style tool-call deltas into engine ``tool_uses``.

    Each entry becomes ``{id, name, input}`` where ``input`` is the
    ``arguments`` JSON string parsed back to a dict.  Entries without
    a ``name`` are dropped (incomplete deltas at stream end).
    """
    tool_uses: list[dict] = []
    for slot in stream_tool_calls.values():
        name = slot.get("name") or ""
        if not name:
            continue
        raw_args = slot.get("arguments") or ""
        try:
            inp: dict = json.loads(raw_args) if raw_args else {}
        except (json.JSONDecodeError, TypeError):
            inp = {"raw": raw_args}
        if not isinstance(inp, dict):
            inp = {"raw": inp}
        tool_uses.append(
            {"id": slot.get("id") or "", "name": name, "input": inp}
        )
    return tool_uses



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
            raise ProviderError(error_msg)

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

                if resp.status_code != 200:
                    error_text = resp.text
                    logger.error(f"[{req_id}] Non-2xx HTTP {resp.status_code}: {error_text[:500]}")
                    _log_request(model, messages, error=f"HTTP {resp.status_code}: {error_text[:500]}")
                    raise Provider.classify_http_error(
                        resp.status_code, error_text,
                        retry_after=retry_after_seconds(resp),
                    )

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
        except ProviderError:
            raise
        except httpx.ConnectError as e:
            error_msg = f"Connection error: {e}"
            logger.error(f"[{req_id}] {error_msg}")
            _log_request(model, messages, error=error_msg)
            raise TransientProviderError(error_msg) from e
        except Exception as e:
            error_msg = f"Error: {e}"
            logger.exception(f"[{req_id}] {error_msg}")
            _log_request(model, messages, error=error_msg)
            raise TransientProviderError(error_msg) from e

    async def chat_stream_response(
        self,
        messages: list[Message],
        model: str,
        on_text_chunk: Optional[Callable[[str], None]] = None,
        on_tool_call_delta: Optional[Callable[[str, str, str], None]] = None,
        **kwargs,
    ) -> ChatResponse:
        self._request_count += 1
        req_id = f"req_{self._request_count}_{int(time.time())}"
        logger.info(f"[{req_id}] chat_stream_response() called with model={model}, messages={len(messages)}")

        key = self.resolve_api_key(self.api_key)
        if not key:
            raise ProviderError("API key not configured.")

        start_time = time.time()
        content_parts: list[str] = []
        # OpenAI-compatible tool calls are streamed as a sequence of
        # ``delta.tool_calls`` deltas.  Accumulate by ``index`` so the
        # final ``arguments`` string can be parsed back into a dict
        # that the engine passes to ``_build_tool_call_content``.
        stream_tool_calls: dict[int, dict] = {}

        try:
            async with httpx.AsyncClient(timeout=300) as client:
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
                        **kwargs,
                    },
                ) as resp:
                    if resp.status_code >= 400:
                        error_body = (await resp.aread()).decode("utf-8", errors="replace")
                        _raise_for_status(resp, body_text=error_body)
                    async for line in resp.aiter_lines():
                        if line.startswith("data: ") and line[6:] != "[DONE]":
                            try:
                                chunk = json.loads(line[6:])
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    content_parts.append(content)
                                    if on_text_chunk:
                                        on_text_chunk(content)
                                for tcd in delta.get("tool_calls", []) or []:
                                    idx = tcd.get("index", 0)
                                    slot = stream_tool_calls.setdefault(
                                        idx,
                                        {"id": "", "name": "", "arguments": ""},
                                    )
                                    _accumulate_tool_call_delta(slot, tcd)
                                    if on_tool_call_delta:
                                        call_id = slot.get("id", "")
                                        name = slot.get("name", "")
                                        args_delta = tcd.get("function", {}).get("arguments", "") or ""
                                        on_tool_call_delta(call_id, name, args_delta)
                            except json.JSONDecodeError:
                                continue
                        elif line.startswith("data: [DONE]"):
                            pass

            elapsed = time.time() - start_time
            logger.info(
                f"[{req_id}] Stream complete, elapsed: {elapsed:.2f}s, "
                f"chars: {sum(len(p) for p in content_parts)}, "
                f"tool_calls: {len(stream_tool_calls)}"
            )
        except ProviderError:
            # Already classified — propagate verbatim.
            _log_request(model, messages, error="provider error (see exception)")
            raise
        except httpx.ConnectError as e:
            error_msg = f"Connection error: {e}"
            logger.error(f"[{req_id}] {error_msg}")
            _log_request(model, messages, error=error_msg)
            raise TransientProviderError(error_msg) from e
        except Exception as e:
            error_msg = f"Error: {e}"
            logger.exception(f"[{req_id}] {error_msg}")
            _log_request(model, messages, error=error_msg)
            raise TransientProviderError(error_msg) from e

        tool_uses = _finalize_stream_tool_calls(stream_tool_calls)

        _log_request(model, messages, response_data={"stream": True})
        return ChatResponse(content="".join(content_parts), tool_uses=tool_uses)

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
            raise ProviderError(error_msg)

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
                        raise Provider.classify_http_error(
                            resp.status_code, error_text,
                            retry_after=retry_after_seconds(resp),
                        )

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
        except ProviderError:
            raise
        except httpx.ConnectError as e:
            error_msg = f"Connection error: {e}"
            logger.error(f"[{req_id}] {error_msg}")
            _log_request(model, messages, error=error_msg)
            raise TransientProviderError(error_msg) from e
        except Exception as e:
            error_msg = f"Error: {e}"
            logger.exception(f"[{req_id}] {error_msg}")
            _log_request(model, messages, error=error_msg)
            raise TransientProviderError(error_msg) from e

        _log_request(model, messages, response_data=response_data)


ProviderRegistry.register("minimaxi", MiniMaxiProvider)