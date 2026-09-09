from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Event:
    type: str
    source: str
    payload: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EventTypes:
    SESSION_ENDED = "session.ended"
    SESSION_STARTED = "session.started"
    VERIFICATION_PASSED = "verification.passed"
    VERIFICATION_FAILED = "verification.failed"
    CRON_TICK = "cron.tick"
    FILE_CHANGED = "file.changed"
    CONFIG_CHANGED = "config.changed"
    TOOL_EXECUTED = "tool.executed"
    TOOL_FAILED = "tool.failed"