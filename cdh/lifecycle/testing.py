from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TestPlan:
    strategy: str = ""
    test_cases: list[str] = field(default_factory=list)
    coverage_report: str = ""
    passed: int = 0
    failed: int = 0
    total: int = 0
