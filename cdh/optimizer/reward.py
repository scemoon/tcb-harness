from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SessionMetrics:
    session_id: str
    test_pass_rate: float = 0.0
    task_completion_pct: float = 0.0
    tool_efficiency: float = 0.0
    turn_count: int = 0
    timestamp: str = ""
    user_feedback: float = 0.0


class RewardCalculator:
    WEIGHTS_FULL = {
        "test_pass_rate": 0.40,
        "task_completion": 0.30,
        "tool_efficiency": 0.20,
        "user_feedback": 0.10,
    }

    WEIGHTS_PARTIAL = {
        "test_pass_rate": 0.55,
        "tool_efficiency": 0.30,
        "user_feedback": 0.15,
    }

    def compute(self, metrics: SessionMetrics) -> float:
        if metrics.task_completion_pct is not None and metrics.task_completion_pct > 0:
            w = self.WEIGHTS_FULL
            return (
                metrics.test_pass_rate * w["test_pass_rate"]
                + metrics.task_completion_pct * w["task_completion"]
                + metrics.tool_efficiency * w["tool_efficiency"]
                + metrics.user_feedback * w["user_feedback"]
            )
        else:
            w = self.WEIGHTS_PARTIAL
            return (
                metrics.test_pass_rate * w["test_pass_rate"]
                + metrics.tool_efficiency * w["tool_efficiency"]
                + metrics.user_feedback * w["user_feedback"]
            )

    def compute_all(self, all_metrics: list[SessionMetrics]) -> float:
        if not all_metrics:
            return 0.0
        return sum(self.compute(m) for m in all_metrics) / len(all_metrics)