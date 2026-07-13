from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

from cdh.event_loop.bus import EventBus
from cdh.event_loop.events import Event, EventTypes
from cdh.verification.aggregation import AggregateResult, GateResult
from cdh.verification.gates.base import Gate
from cdh.verification.policy import is_source_file

logger = logging.getLogger("cdh.verification.loop")


class VerificationState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class PlatformVerificationLoop:
    def __init__(self, project_dir: str | None = None):
        self.state = VerificationState.IDLE
        self.project_dir = project_dir or "."
        self._gates: dict[str, Gate] = {}
        self._bus: EventBus | None = None

    def register_gate(self, gate: Gate) -> None:
        self._gates[gate.name] = gate

    def unregister_gate(self, name: str) -> None:
        self._gates.pop(name, None)

    def activate(self) -> None:
        self.state = VerificationState.RUNNING

    def subscribe(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe(EventTypes.FILE_CHANGED, self._on_file_changed)
        logger.info("PlatformVerificationLoop subscribed to file.changed")

    async def _on_file_changed(self, event: Event) -> None:
        if self.state != VerificationState.RUNNING:
            return

        path = event.payload.get("path", "")
        if not path or not is_source_file(path):
            return

        project = Path(self.project_dir).resolve()
        changed = Path(path).resolve()
        try:
            changed.relative_to(project)
        except ValueError:
            return

        logger.debug("Verification triggered by file change: %s", path)
        results: dict[str, GateResult] = {}
        for name, gate in self._gates.items():
            if not gate.enabled:
                continue
            if not gate.should_run(path):
                continue
            try:
                result = await gate.run(self.project_dir)
                results[name] = result
            except Exception as exc:
                logger.warning("Gate %s failed: %s", name, exc)
                results[name] = GateResult(name=name, status="failed", summary=str(exc))

        aggregated = AggregateResult(gate_results=results)
        if aggregated.failed:
            self.state = VerificationState.FAILED
            logger.warning("Verification failed: %s", aggregated.failed_gates)
        else:
            self.state = VerificationState.COMPLETED

        if self._bus is not None:
            evt_type = EventTypes.VERIFICATION_FAILED if aggregated.failed else EventTypes.VERIFICATION_PASSED
            self._bus.publish(Event(
                type=evt_type,
                source="cdh.verification",
                payload={
                    "session_id": event.payload.get("session_id", ""),
                    "path": path,
                    "failed_gates": aggregated.failed_gates if aggregated.failed else [],
                },
            ))