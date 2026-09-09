from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TurnRecord:
    turn_number: int
    thought: str
    tool_name: str
    tool_input: dict[str, Any] | None = None
    tool_output: Any = None
    tool_error: str | None = None
    duration_ms: int = 0
    verification_results: list[dict] = field(default_factory=list)

    @property
    def success(self) -> bool:
        if self.tool_error:
            return False
        for v in self.verification_results:
            if isinstance(v, dict) and v.get("failed_gates"):
                return False
        return True

    def add_verification(self, result: dict) -> None:
        self.verification_results.append(result)