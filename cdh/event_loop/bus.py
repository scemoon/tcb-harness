from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from cdh.event_loop.events import Event

logger = logging.getLogger("cdh.event_loop.bus")

EventHandler = Callable[[Event], None]


class EventLoopState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


def _is_async(handler: EventHandler) -> bool:
    return asyncio.iscoroutinefunction(handler) or (
        hasattr(handler, "__func__")
        and asyncio.iscoroutinefunction(handler.__func__)  # type: ignore[attr-defined]
    )


@dataclass
class EventBus:
    state: EventLoopState = EventLoopState.IDLE
    _subscribers: dict[str, list[EventHandler]] = field(default_factory=dict)
    _history: list[Event] = field(default_factory=list)
    _max_history: int = 1000

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        logger.debug("Subscribed %s to %s", getattr(handler, "__name__", handler), event_type)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h != handler
            ]

    def publish(self, event: Event) -> None:
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        handlers = self._subscribers.get(event.type, [])
        if not handlers:
            return

        try:
            loop = asyncio.get_running_loop()
            for handler in handlers:
                if _is_async(handler):
                    loop.create_task(self._invoke_async(handler, event))
                else:
                    self._invoke_sync(handler, event)
        except RuntimeError:
            for handler in handlers:
                if _is_async(handler):
                    logger.debug(
                        "Skipping async handler %s — no running event loop",
                        getattr(handler, "__name__", handler),
                    )
                else:
                    self._invoke_sync(handler, event)

    async def _invoke_async(self, handler: EventHandler, event: Event) -> None:
        try:
            await handler(event)
        except Exception as exc:
            logger.warning(
                "Async handler %s failed on event %s: %s",
                getattr(handler, "__name__", handler), event.type, exc,
                exc_info=True,
            )

    def _invoke_sync(self, handler: EventHandler, event: Event) -> None:
        try:
            handler(event)
        except Exception as exc:
            logger.warning(
                "Handler %s failed on event %s: %s",
                getattr(handler, "__name__", handler), event.type, exc,
                exc_info=True,
            )

    def get_history(self, event_type: str | None = None,
                    limit: int = 100) -> list[Event]:
        filtered = self._history
        if event_type:
            filtered = [e for e in self._history if e.type == event_type]
        return filtered[-limit:]

    def start(self) -> None:
        self.state = EventLoopState.RUNNING

    def stop(self) -> None:
        self.state = EventLoopState.COMPLETED
