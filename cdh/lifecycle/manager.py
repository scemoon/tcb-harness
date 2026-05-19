from __future__ import annotations

from enum import Enum
from typing import Optional


class LifecycleStage(str, Enum):
    NONE = "none"
    SPEC = "spec"
    DESIGN = "design"
    CODING = "coding"
    TESTING = "testing"
    DEPLOY = "deploy"


class StageStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


STAGE_ORDER = [
    LifecycleStage.SPEC,
    LifecycleStage.DESIGN,
    LifecycleStage.CODING,
    LifecycleStage.TESTING,
    LifecycleStage.DEPLOY,
]


class LifecycleManager:
    def __init__(self):
        self.stages: dict[LifecycleStage, StageStatus] = {
            stage: StageStatus.PENDING for stage in STAGE_ORDER
        }
        self.current: LifecycleStage = LifecycleStage.NONE
        self.spec_content: str = ""
        self.design_content: str = ""
        self.coding_content: str = ""
        self.test_report: str = ""
        self.deploy_version: Optional[str] = None

    def start(self, stage: LifecycleStage):
        if stage in self.stages:
            self.stages[stage] = StageStatus.IN_PROGRESS
            self.current = stage

    def complete(self, stage: LifecycleStage):
        if stage in self.stages:
            self.stages[stage] = StageStatus.COMPLETED
            self._advance()

    def fail(self, stage: LifecycleStage):
        if stage in self.stages:
            self.stages[stage] = StageStatus.FAILED

    def can_advance_to(self, stage: LifecycleStage) -> bool:
        if stage == LifecycleStage.SPEC:
            return True
        idx = STAGE_ORDER.index(stage)
        if idx == 0:
            return True
        return self.stages[STAGE_ORDER[idx - 1]] == StageStatus.COMPLETED

    def _advance(self):
        idx = STAGE_ORDER.index(self.current) if self.current in STAGE_ORDER else -1
        if idx + 1 < len(STAGE_ORDER):
            self.current = STAGE_ORDER[idx + 1]

    def summary(self) -> str:
        status_icons = {
            StageStatus.PENDING: "⏳",
            StageStatus.IN_PROGRESS: "🔄",
            StageStatus.COMPLETED: "✔",
            StageStatus.FAILED: "❌",
        }
        parts = []
        for stage in STAGE_ORDER:
            icon = status_icons.get(self.stages[stage], "⏳")
            parts.append(f"{icon} {stage.value.capitalize()}")
        return "  ".join(parts)

    def to_dict(self) -> dict:
        return {
            "stages": {s.value: st.value for s, st in self.stages.items()},
            "current": self.current.value,
        }

    def from_dict(self, data: dict):
        for s in STAGE_ORDER:
            if s.value in data.get("stages", {}):
                self.stages[s] = StageStatus(data["stages"][s.value])
        self.current = LifecycleStage(data.get("current", "none"))
