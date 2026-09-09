from __future__ import annotations

import logging

from cdh.event_loop.bus import EventBus
from cdh.event_loop.events import Event, EventTypes

logger = logging.getLogger("cdh.event_loop.runner")


class EventRunner:
    def __init__(self, bus: EventBus):
        self.bus = bus

    def subscribe_all(self) -> None:
        self.bus.subscribe(EventTypes.CRON_TICK, self._on_cron_tick)
        self.bus.subscribe(EventTypes.FILE_CHANGED, self._on_file_changed)

    def _on_cron_tick(self, event: Event) -> None:
        payload = event.payload
        job_name = payload.get("job_name", "unknown")
        command = payload.get("command", "")
        engine_name = payload.get("engine", "onecode")
        logger.info("Cron tick: job=%s engine=%s command=%s", job_name, engine_name, command)

    def _on_file_changed(self, event: Event) -> None:
        path = event.payload.get("path", "")
        logger.info("File changed: %s", path)