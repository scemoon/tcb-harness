from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from cdh.config import CLOUD_DEV_HARNESS_DIR, HARNESS_DIR


class LifecycleStage(str, Enum):
    NONE = "none"
    INIT = "init"
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

PIPELINE_ORDER = [
    LifecycleStage.INIT,
    LifecycleStage.SPEC,
    LifecycleStage.DESIGN,
    LifecycleStage.CODING,
    LifecycleStage.TESTING,
    LifecycleStage.DEPLOY,
]

PHASE_DESCRIPTIONS = {
    LifecycleStage.INIT: "Initialize project scaffold, configure cloud environment",
    LifecycleStage.SPEC: "Write requirements using EARS syntax, validate with spec guide",
    LifecycleStage.DESIGN: "Design UI components, API contracts, data models",
    LifecycleStage.CODING: "TDD implementation: RED \u2192 GREEN \u2192 REFACTOR",
    LifecycleStage.TESTING: "Generate and run test cases, verify coverage \u226580%",
    LifecycleStage.DEPLOY: "Deploy to cloud, verify all components work together",
}

PHASE_COMMANDS = {
    LifecycleStage.INIT: ["harness init", "harness switch", "harness status"],
    LifecycleStage.SPEC: ["spec generate", "spec accept", "validate_spec.py"],
    LifecycleStage.DESIGN: ["design generate", "design accept"],
    LifecycleStage.CODING: ["agent_spawn for parallel tasks", "TDD cycle"],
    LifecycleStage.TESTING: ["test run", "test accept", "gen_test_cases.py"],
    LifecycleStage.DEPLOY: ["deploy", "deploy status", "deploy rollback"],
}

PHASE_GATES = {
    LifecycleStage.INIT: "config.json exists, valid JSON",
    LifecycleStage.SPEC: "validate_spec.py passes, user confirms",
    LifecycleStage.DESIGN: "cross-platform consistency check, user confirms",
    LifecycleStage.CODING: "npm test exit 0 (or equivalent)",
    LifecycleStage.TESTING: "report exists, no P0/P1 failures, coverage met",
    LifecycleStage.DEPLOY: "deploy config validated, all components deployed",
}

DEFAULT_WORKSPACE = CLOUD_DEV_HARNESS_DIR / "workspace"


class LifecycleManager:
    def __init__(self, project_name: Optional[str] = None, workspace: Optional[Path] = None):
        self.project_name = project_name
        if workspace is None:
            workspace = DEFAULT_WORKSPACE
        self._workspace = workspace

        self.stages: dict[LifecycleStage, StageStatus] = {
            stage: StageStatus.PENDING for stage in STAGE_ORDER
        }
        self.current: LifecycleStage = LifecycleStage.NONE
        self.spec_content: str = ""
        self.design_content: str = ""
        self.coding_content: str = ""
        self.test_report: str = ""
        self.deploy_version: Optional[str] = None

        self._config: dict = {}
        self._state: dict = {}
        self._load_project_data()

    # ── Project persistence ──

    def _projects_dir(self) -> Path:
        return self._workspace / "projects"

    def _load_project_data(self) -> None:
        if not self.project_name:
            return
        project_dir = self._projects_dir() / self.project_name
        if not project_dir.exists():
            return
        config_file = project_dir / ".harness" / "config.json"
        state_file = project_dir / ".harness" / "state.json"
        if config_file.exists():
            try:
                self._config = json.loads(config_file.read_text(encoding="utf-8"))
            except Exception:
                self._config = {}
        if state_file.exists():
            try:
                self._state = json.loads(state_file.read_text(encoding="utf-8"))
            except Exception:
                self._state = {}

        phase = self._state.get("phase", LifecycleStage.INIT.value)
        try:
            self.current = LifecycleStage(phase)
        except ValueError:
            self.current = LifecycleStage.INIT
        for h in self._state.get("phaseHistory", []):
            try:
                s = LifecycleStage(h["phase"])
                if s in self.stages:
                    self.stages[s] = StageStatus.COMPLETED
            except (ValueError, KeyError):
                pass
        if self.current != LifecycleStage.NONE and self.current in self.stages:
            self.stages[self.current] = StageStatus.IN_PROGRESS

    # ── In-memory stage API (used by TUI commands) ──

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
            StageStatus.PENDING: "\u23f3",
            StageStatus.IN_PROGRESS: "\U0001f504",
            StageStatus.COMPLETED: "\u2714",
            StageStatus.FAILED: "\u274c",
        }
        parts = []
        for stage in STAGE_ORDER:
            icon = status_icons.get(self.stages[stage], "\u23f3")
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

    # ── Project/pipeline API (used by agent engine) ──

    @property
    def current_phase(self) -> str:
        if self.project_name:
            return self._state.get("phase", LifecycleStage.INIT.value)
        return self.current.value

    @property
    def platform(self) -> str:
        return self._config.get("platform", "unknown")

    @property
    def env_id(self) -> str:
        return self._config.get("cloudbase", {}).get("envId", "")

    def get_next_phase(self) -> Optional[str]:
        order = PIPELINE_ORDER if self.project_name else STAGE_ORDER
        current = self.current_phase
        try:
            idx = next(i for i, s in enumerate(order) if s.value == current)
            if idx + 1 < len(order):
                return order[idx + 1].value
        except (StopIteration, ValueError):
            pass
        return None

    def get_phase_info(self, phase: str) -> dict:
        try:
            p = LifecycleStage(phase)
        except ValueError:
            return {"name": phase, "description": "", "commands": [], "gate": "", "order": -1}
        return {
            "name": phase,
            "description": PHASE_DESCRIPTIONS.get(p, ""),
            "commands": PHASE_COMMANDS.get(p, []),
            "gate": PHASE_GATES.get(p, ""),
            "order": PIPELINE_ORDER.index(p) if p in PIPELINE_ORDER else -1,
        }

    def get_pipeline_summary(self) -> str:
        lines = ["## Pipeline: Init \u2192 Spec \u2192 Design \u2192 Coding \u2192 Testing \u2192 Deploy", ""]
        for phase in PIPELINE_ORDER:
            info = self.get_phase_info(phase.value)
            current_marker = " \u25b6" if phase.value == self.current_phase else ""
            lines.append(f"**{phase.value.upper()}{current_marker}**")
            lines.append(f"  {info['description']}")
            if phase.value == self.current_phase:
                lines.append(f"  Commands: {', '.join(info['commands'])}")
                lines.append(f"  Gate: {info['gate']}")
            lines.append("")
        return "\n".join(lines)

    def advance_phase(self) -> Optional[str]:
        if not self.project_name:
            return None
        next_phase = self.get_next_phase()
        if not next_phase:
            return None
        now = datetime.now().isoformat()
        history = self._state.setdefault("phaseHistory", [])
        history.append({"phase": self.current_phase, "completedAt": now})
        self._state["phase"] = next_phase
        self._state["status"] = "in_progress"
        self._state.setdefault("tasks", {})["completed"] = self._state["tasks"].get("completed", 0) + 1
        self._state["lastActivity"] = {"action": "advance_phase", "task": f"phase:{next_phase}", "timestamp": now}
        state_file = self._projects_dir() / self.project_name / ".harness" / "state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(self._state, indent=2, ensure_ascii=False), encoding="utf-8")
        return next_phase

    def get_harness_skill_content(self) -> str:
        skill_md = HARNESS_DIR / "SKILL.md"
        if skill_md.exists():
            return skill_md.read_text(encoding="utf-8")
        return ""
