from __future__ import annotations

import logging
from enum import Enum

from onecode.agent.turn_record import TurnRecord
from onecode.verification.policy import VerificationPolicy
from onecode.verification.aggregation import AggregateResult, GateResult
from onecode.verification.gates.base import Gate

logger = logging.getLogger("onecode.verification.loop")


class VerificationState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class VerificationLoop:
    def __init__(self, policy: str = "conditional"):
        self.state = VerificationState.IDLE
        self.policy = VerificationPolicy.from_str(policy)
        self._gates: dict[str, Gate] = {}

    @property
    def enabled(self) -> bool:
        return self.state is not VerificationState.IDLE

    @property
    def gates(self) -> list[Gate]:
        return list(self._gates.values())

    def register_gate(self, gate: Gate) -> None:
        self._gates[gate.name] = gate

    def unregister_gate(self, name: str) -> None:
        self._gates.pop(name, None)

    def activate(self) -> None:
        self.state = VerificationState.RUNNING

    def pause(self) -> None:
        self.state = VerificationState.PAUSED

    def resume(self) -> None:
        self.state = VerificationState.RUNNING

    def should_verify(self, tool_name: str) -> bool:
        if self.state != VerificationState.RUNNING:
            return False
        return self.policy.should_verify(tool_name)

    def should_final_verify(self) -> bool:
        if self.state != VerificationState.RUNNING:
            return False
        return self.policy.should_final_verify()

    async def run_gates(self, turn_record: TurnRecord) -> AggregateResult:
        results: dict[str, GateResult] = {}
        for name, gate in self._gates.items():
            if not gate.enabled:
                continue
            if not gate.should_run(turn_record.tool_name, turn_record.tool_output):
                continue
            try:
                result = await gate.run(turn_record)
            except Exception as e:
                logger.warning("Gate %s failed: %s", name, e)
                result = GateResult(name=name, status="failed", summary=str(e))
            results[name] = result

        aggregated = AggregateResult(gate_results=results)
        return aggregated

    async def run_all_final_gates(self) -> AggregateResult:
        results: dict[str, GateResult] = {}
        for name, gate in self._gates.items():
            if not gate.enabled:
                continue
            try:
                result = await gate.run(TurnRecord(
                    turn_number=-1, thought="", tool_name="__final__", tool_output=None,
                ))
            except Exception as exc:
                logger.warning("Final gate %s failed: %s", name, exc)
                result = GateResult(name=name, status="failed", summary=str(exc))
            results[name] = result

        aggregated = AggregateResult(gate_results=results)
        if aggregated.failed:
            self.state = VerificationState.FAILED
        return aggregated