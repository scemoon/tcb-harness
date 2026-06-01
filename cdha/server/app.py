from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from cdha.agent.engine import AgentEngine

logger = logging.getLogger("cdha.server")


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

            text_buffer = []
            async for event in self._engine.chat_stream(user_input):
                from cdha.models.messages import StreamEvent
                if isinstance(event, StreamEvent):
                    if event.text:
                        text_buffer.append(event.text)
                        payload = json.dumps({"type": "delta", "text": event.text})
                        await send({
                            "type": "http.response.body",
                            "body": f"data: {payload}\n\n".encode(),
                            "more_body": True,
                        })
                else:
                    text_buffer.append(str(event))

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
