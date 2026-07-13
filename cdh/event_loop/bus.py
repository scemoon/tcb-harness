from __future__ import annotations

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
        logger.debug("Subscribed %s to %s", handler.__name__, event_type)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h != handler
            ]

    def publish(self, event: Event) -> None:
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        for handler in self._subscribers.get(event.type, []):
            try:
                handler(event)
            except Exception as exc:
                logger.warning("Handler %s failed on %s: %s",
                               handler.__name__, event.type, exc)

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