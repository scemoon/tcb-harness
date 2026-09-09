from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class GateResult:
    name: str
    status: str = "skipped"
    exit_code: int | None = None
    duration_ms: int = 0
    summary: str = ""
    log_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "summary": self.summary[:200] if self.summary else "",
        }


@dataclass
class AggregateResult:
    gate_results: dict[str, GateResult] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def passed(self) -> bool:
        return len(self.failed_gates) == 0

    @property
    def failed(self) -> bool:
        return len(self.failed_gates) > 0

    @property
    def skipped(self) -> list[str]:
        return [n for n, r in self.gate_results.items() if r.status == "skipped"]

    @property
    def failed_gates(self) -> list[str]:
        return [n for n, r in self.gate_results.items() if r.status == "failed"]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "failed_gates": self.failed_gates,
            "results": {n: {"status": r.status, "duration_ms": r.duration_ms, "summary": r.summary}
                       for n, r in self.gate_results.items()},
        }