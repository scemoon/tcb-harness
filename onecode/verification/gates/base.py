from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from onecode.agent.turn_record import TurnRecord
from onecode.verification.aggregation import GateResult


class Gate(ABC):
    name: str = ""
    enabled: bool = True

    @abstractmethod
    def should_run(self, tool_name: str, tool_result: Any) -> bool:
        ...

    @abstractmethod
    async def run(self, turn_record: TurnRecord) -> GateResult:
        ...