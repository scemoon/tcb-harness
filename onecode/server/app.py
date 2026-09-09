from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from onecode.agent.engine import AgentEngine

logger = logging.getLogger("onecode.server")


async def _sse_publisher(engine: AgentEngine, response: Response):
    """Stream agent output as SSE events."""
    send = response.__dict__.get("send")

    async def _on_text(text: str):
        if send:
            try:
                await send({
                    "type": "http.response.body",
                    "body": f"data: {json.dumps({'type': 'text', 'content': text})}\n\n".encode(),
                    "more_body": True,
                })
            except Exception:
                pass

    engine.on_text_chunk = _on_text
    return send


class AgentServer:
    """HTTP/SSE server for remote agent access (Clawd-Code pattern)."""

    def __init__(self, engine: AgentEngine, host: str = "127.0.0.1", port: int = 8765):
        self._engine = engine
        self._host = host
        self._port = port
        self._app = self._build_app()
        self._server: Optional[asyncio.AbstractServer] = None

    def _build_app(self) -> Starlette:
        routes = [
            Route("/health", endpoint=self._handle_health, methods=["GET"]),
            Route("/status", endpoint=self._handle_status, methods=["GET"]),
            Route("/chat", endpoint=self._handle_chat, methods=["POST"]),
            Route("/events", endpoint=self._handle_events, methods=["GET"]),
        ]
        return Starlette(routes=routes, on_shutdown=[self._shutdown])

    async def _handle_health(self, request):
        return JSONResponse({"status": "ok"})

    async def _handle_status(self, request):
        return JSONResponse({
            "iterations": self._engine.iterations,
            "total_tokens": self._engine.total_tokens,
            "provider": getattr(self._engine.app, "current_provider", None),
            "model": getattr(self._engine.app, "current_model", None),
        })

    async def _handle_chat(self, request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON body"}, status_code=400)

        user_input = body.get("message", "")
        if not user_input:
            return JSONResponse({"error": "message is required"}, status_code=400)

        response_text = await self._engine.chat(user_input)
        return JSONResponse({"response": response_text})

    async def _handle_events(self, request):
        async def _send_events(send):
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/event-stream"),
                    (b"cache-control", b"no-cache"),
                    (b"connection", b"keep-alive"),
                    (b"access-control-allow-origin", b"*"),
                ],
            })

            user_input = request.query_params.get("message", "")
            if not user_input:
                await send({
                    "type": "http.response.body",
                    "body": b"data: {\"error\": \"message query param required\"}\n\n",
                    "more_body": False,
                })
                return

            from onecode.models.messages import StreamEvent, StreamEventType

            _tc_args: dict[str, str] = {}

            # SSE heartbeat — periodic comment lines to keep connection alive
            # during long thinking/processing periods.
            _heartbeat_interval = 15

            async def _heartbeat():
                while True:
                    try:
                        await asyncio.sleep(_heartbeat_interval)
                        await send({
                            "type": "http.response.body",
                            "body": b": keepalive\n\n",
                            "more_body": True,
                        })
                    except asyncio.CancelledError:
                        return
                    except Exception:
                        return

            _hb_task = asyncio.create_task(_heartbeat())

            def _on_tool_call_delta(call_id: str, name: str, args_delta: str) -> None:
                if not args_delta:
                    return
                _tc_args[call_id] = _tc_args.get(call_id, "") + args_delta
                payload = json.dumps({
                    "type": "tool_call_args",
                    "toolCallId": call_id,
                    "name": name,
                    "args": _tc_args[call_id],
                })
                asyncio.ensure_future(send({
                    "type": "http.response.body",
                    "body": f"data: {payload}\n\n".encode(),
                    "more_body": True,
                }))

            self._engine.on_tool_call_delta = _on_tool_call_delta

            text_buffer = []
            try:
                async for event in self._engine.chat_stream(user_input):
                    if isinstance(event, StreamEvent):
                        if event.type == StreamEventType.TEXT_DELTA and event.text:
                            text_buffer.append(event.text)
                            payload = json.dumps({"type": "delta", "text": event.text})
                            await send({
                                "type": "http.response.body",
                                "body": f"data: {payload}\n\n".encode(),
                                "more_body": True,
                            })
                        elif event.type == StreamEventType.THINKING and event.thinking:
                            payload = json.dumps({"type": "thinking", "content": event.thinking})
                            await send({
                                "type": "http.response.body",
                                "body": f"data: {payload}\n\n".encode(),
                                "more_body": True,
                            })
                        elif event.type == StreamEventType.TOOL_CALL_START:
                            payload = json.dumps({
                                "type": "tool_call_start",
                                "toolCallId": event.tool_id,
                                "name": event.tool_name,
                            })
                            await send({
                                "type": "http.response.body",
                                "body": f"data: {payload}\n\n".encode(),
                                "more_body": True,
                            })
                        elif event.type == StreamEventType.TOOL_CALL_COMPLETE:
                            payload = json.dumps({
                                "type": "tool_call_complete",
                                "toolCallId": event.tool_id,
                                "name": event.tool_name,
                                "args": event.tool_args,
                            })
                            await send({
                                "type": "http.response.body",
                                "body": f"data: {payload}\n\n".encode(),
                                "more_body": True,
                            })
                        elif event.type == StreamEventType.TOOL_RESULT:
                            payload = json.dumps({
                                "type": "tool_result",
                                "toolCallId": event.tool_id,
                                "content": event.result_content,
                                "isError": event.result_is_error,
                            })
                            await send({
                                "type": "http.response.body",
                                "body": f"data: {payload}\n\n".encode(),
                                "more_body": True,
                            })
                        elif event.type == StreamEventType.ERROR:
                            payload = json.dumps({"type": "error", "message": event.error_message})
                            await send({
                                "type": "http.response.body",
                                "body": f"data: {payload}\n\n".encode(),
                                "more_body": True,
                            })
                    else:
                        text_buffer.append(str(event))
            finally:
                _hb_task.cancel()
                try:
                    await _hb_task
                except (asyncio.CancelledError, Exception):
                    pass

            full_text = "".join(text_buffer)
            payload = json.dumps({"type": "done", "text": full_text})
            await send({
                "type": "http.response.body",
                "body": f"data: {payload}\n\n".encode(),
                "more_body": False,
            })

        return Response(
            content=None,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
            },
        )

    async def _shutdown(self):
        logger.info("Server shutting down")

    async def start(self):
        import uvicorn
        cfg = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_level="info",
            lifespan="on",
        )
        server = uvicorn.Server(cfg)
        logger.info(f"Agent server starting on http://{self._host}:{self._port}")
        await server.serve()

    def start_background(self) -> None:
        """Start server in background thread."""
        import threading
        t = threading.Thread(target=lambda: asyncio.run(self.start()), daemon=True)
        t.start()
