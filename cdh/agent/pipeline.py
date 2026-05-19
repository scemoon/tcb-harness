from __future__ import annotations

from pathlib import Path
from typing import Optional
import yaml


WORKSPACE = Path(__file__).parent.parent.parent
HARNESS_DIR = WORKSPACE / "cloud-harness"


class PipelinePhase:
    INIT = "init"
    SPEC = "spec"
    DESIGN = "design"
    CODING = "coding"
    TESTING = "testing"
    DEPLOY = "deploy"


PIPELINE_ORDER = [
    PipelinePhase.INIT,
    PipelinePhase.SPEC,
    PipelinePhase.DESIGN,
    PipelinePhase.CODING,
    PipelinePhase.TESTING,
    PipelinePhase.DEPLOY,
]


PHASE_DESCRIPTIONS = {
    PipelinePhase.INIT: "Initialize project scaffold, configure cloud environment",
    PipelinePhase.SPEC: "Write requirements using EARS syntax, validate with spec guide",
    PipelinePhase.DESIGN: "Design UI components, API contracts, data models",
    PipelinePhase.CODING: "TDD implementation: RED → GREEN → REFACTOR",
    PipelinePhase.TESTING: "Generate and run test cases, verify coverage ≥80%",
    PipelinePhase.DEPLOY: "Deploy to cloud, verify all components work together",
}


PHASE_COMMANDS = {
    PipelinePhase.INIT: ["harness init", "harness switch", "harness status"],
    PipelinePhase.SPEC: ["spec generate", "spec accept", "validate_spec.py"],
    PipelinePhase.DESIGN: ["design generate", "design accept"],
    PipelinePhase.CODING: ["agent_spawn for parallel tasks", "TDD cycle"],
    PipelinePhase.TESTING: ["test run", "test accept", "gen_test_cases.py"],
    PipelinePhase.DEPLOY: ["deploy", "deploy status", "deploy rollback"],
}


PHASE_GATES = {
    PipelinePhase.INIT: "config.json exists, valid JSON",
    PipelinePhase.SPEC: "validate_spec.py passes, user confirms",
    PipelinePhase.DESIGN: "cross-platform consistency check, user confirms",
    PipelinePhase.CODING: "npm test exit 0 (or equivalent)",
    PipelinePhase.TESTING: "report exists, no P0/P1 failures, coverage met",
    PipelinePhase.DEPLOY: "deploy config validated, all components deployed",
}


class PipelineManager:
    def __init__(self, project_name: Optional[str] = None):
        self.project_name = project_name
        self._config = None
        self._state = None
        self._load_project_data()

    def _load_project_data(self) -> None:
        if not self.project_name:
            self._config = {}
            self._state = {}
            return

        project_dir = WORKSPACE / "projects" / self.project_name
        if not project_dir.exists():
            self._config = {}
            self._state = {}
            return

        config_file = project_dir / ".harness" / "config.json"
        state_file = project_dir / ".harness" / "state.json"

        if config_file.exists():
            try:
                self._config = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
            except Exception:
                self._config = {}
        else:
            self._config = {}

        if state_file.exists():
            try:
                self._state = yaml.safe_load(state_file.read_text(encoding="utf-8")) or {}
            except Exception:
                self._state = {}
        else:
            self._state = {}

    @property
    def current_phase(self) -> str:
        return self._state.get("phase", PipelinePhase.INIT)

    @property
    def platform(self) -> str:
        return self._config.get("platform", "unknown")

    @property
    def env_id(self) -> str:
        return self._config.get("cloudbase", {}).get("envId", "")

    def can_advance_to(self, target_phase: str) -> bool:
        if target_phase not in PIPELINE_ORDER:
            return False
        if target_phase == PipelinePhase.INIT:
            return True

        current_idx = PIPELINE_ORDER.index(self.current_phase)
        target_idx = PIPELINE_ORDER.index(target_phase)

        if target_idx <= current_idx:
            return True

        return all(
            self._state.get("phaseHistory", []) and
            any(p.get("phase") == PIPELINE_ORDER[i]
                for p in self._state.get("phaseHistory", []))
            for i in range(current_idx, target_idx)
        )

    def get_next_phase(self) -> Optional[str]:
        try:
            idx = PIPELINE_ORDER.index(self.current_phase)
            if idx + 1 < len(PIPELINE_ORDER):
                return PIPELINE_ORDER[idx + 1]
        except ValueError:
            pass
        return None

    def get_phase_info(self, phase: str) -> dict:
        return {
            "name": phase,
            "description": PHASE_DESCRIPTIONS.get(phase, ""),
            "commands": PHASE_COMMANDS.get(phase, []),
            "gate": PHASE_GATES.get(phase, ""),
            "order": PIPELINE_ORDER.index(phase) if phase in PIPELINE_ORDER else -1,
        }

    def get_pipeline_summary(self) -> str:
        lines = ["## Pipeline: Init → Spec → Design → Coding → Testing → Deploy", ""]

        for phase in PIPELINE_ORDER:
            info = self.get_phase_info(phase)
            current_marker = " ▶" if phase == self.current_phase else ""
            lines.append(f"**{phase.upper()}{current_marker}**")
            lines.append(f"  {info['description']}")
            if phase == self.current_phase:
                lines.append(f"  Commands: {', '.join(info['commands'])}")
                lines.append(f"  Gate: {info['gate']}")
            lines.append("")

        return "\n".join(lines)

    def get_harness_skill_content(self) -> str:
        skill_md = HARNESS_DIR / "SKILL.md"
        if skill_md.exists():
            return skill_md.read_text(encoding="utf-8")
        return ""


def get_pipeline_for_agent(project_name: Optional[str] = None) -> str:
    pm = PipelineManager(project_name)
    return pm.get_pipeline_summary()