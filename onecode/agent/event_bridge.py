from __future__ import annotations

import logging
from typing import Any

from onecode.agent.engine import ToolEvent
from onecode.verification.aggregation import AggregateResult

logger = logging.getLogger("onecode.agent.event_bridge")

try:
    from cdh.event_loop.bus import EventBus
    from cdh.event_loop.events import Event, EventTypes
    HAS_CDH = True
except ImportError:
    HAS_CDH = False
    EventBus = None  # type: ignore
    EventTypes = None  # type: ignore


class EventBridge:
    def __init__(self, bus: EventBus | None = None):
        self.bus = bus
        self._session_id: str = ""

    def set_session(self, session_id: str) -> None:
        self._session_id = session_id

    def on_tool_event(self, event: ToolEvent) -> None:
        if self.bus is None or not HAS_CDH:
            logger.debug("EventBridge: bus unavailable, dropping %s event for %s",
                         event.kind, event.tool_name)
            return
        event_type = EventTypes.TOOL_FAILED if event.is_error else EventTypes.TOOL_EXECUTED
        self.bus.publish(Event(
            type=event_type,
            source="onecode",
            payload={
                "session_id": self._session_id,
                "tool_name": event.tool_name,
                "is_error": event.is_error,
                "error": event.error,
            },
        ))

    def on_session_ended(self, turn_count: int, metrics: dict[str, Any]) -> None:
        if self.bus is None or not HAS_CDH:
            return
        self.bus.publish(Event(
            type=EventTypes.SESSION_ENDED,
            source="onecode",
            payload={
                "session_id": self._session_id,
                "turn_count": turn_count,
                "metrics": metrics,
            },
        ))

    def on_verification_passed(self) -> None:
        if self.bus is None or not HAS_CDH:
            return
        self.bus.publish(Event(
            type=EventTypes.VERIFICATION_PASSED,
            source="onecode",
            payload={"session_id": self._session_id},
        ))

    def on_verification_failed(self, result: AggregateResult) -> None:
        if self.bus is None or not HAS_CDH:
            return
        self.bus.publish(Event(
            type=EventTypes.VERIFICATION_FAILED,
            source="onecode",
            payload={"session_id": self._session_id, "failed_gates": result.failed_gates},
        ))