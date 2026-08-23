from __future__ import annotations

import json
from pathlib import Path

import yaml

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Click
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static


class AIDLCModeChanged(Message):
    def __init__(self, mode: str) -> None:
        super().__init__()
        self.mode = mode


_PHASE_LABELS: dict[str, str] = {
    "init": "Initialized",
    "understand": "\u2460 Understand",
    "plan": "\u2461 Plan",
    "verify": "\u2462 Verify",
    "deliver": "\u2463 Deliver",
}

_PHASE_ORDER: list[str] = ["understand", "plan", "verify", "deliver"]

_AIDLC_MODE_OPTIONS = [
    ("L0", "closed"),
    ("L1", "nudge"),
    ("L2", "auto"),
    ("L3", "enforce"),
]

_DEFAULT_AIDLC_MODE = "L2"


class AIDLCStats(Static):
    DEFAULT_CSS = """
    AIDLCStats {
        height: auto;
        padding: 0 1;

        #aidlc-mode-header {
            margin: 0;
            padding: 0;
        }

        #aidlc-mode-options {
            height: auto;
        }

        .mode-option {
            height: auto;
            padding: 0 1;
        }

        .mode-option:hover {
            background: $surface-lighten-1;
        }

        .mode-indicator {
            width: auto;
            margin-right: 1;
        }

        .mode-option.active .mode-indicator {
            color: $primary;
        }

        .mode-label {
            width: auto;
        }

        .mode-option.active .mode-label {
            color: $primary;
            text-style: bold;
        }

        #aidlc-phase {
            text-style: bold;
            margin: 0;
            padding: 1 0 0 0;
        }

        #aidlc-progress {
            color: $text-secondary;
            margin: 0;
            padding: 1 0 0 0;
        }

        #aidlc-completed {
            color: $success;
            margin: 0;
            padding: 0;
        }

        #aidlc-gates {
            color: $text-secondary;
            margin: 0;
            padding: 0;
        }
    }
    """

    aidlc_mode: reactive[str] = reactive(_DEFAULT_AIDLC_MODE)
    current_phase: reactive[str] = reactive("")
    completed_phases: reactive[list[str]] = reactive(list)
    gate_results: reactive[dict] = reactive(dict)
    project_path: reactive[Path | None] = reactive(None)

    def __init__(
        self,
        aidlc_mode: str = _DEFAULT_AIDLC_MODE,
        current_phase: str = "",
        completed_phases: list[str] | None = None,
        gate_results: dict | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        project_path: Path | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._initial_mode = aidlc_mode
        self._initial_phase = current_phase
        self._initial_completed = completed_phases or []
        self._initial_gates = gate_results or {}
        self.project_path = project_path
        self._state_mtime: float | None = None
        self._project_yaml_mtime: float | None = None

    def compose(self) -> ComposeResult:
        yield Static("mode level:", id="aidlc-mode-header")
        with Vertical(id="aidlc-mode-options"):
            for mode, desc in _AIDLC_MODE_OPTIONS:
                option = Static(
                    f"\u25cb {mode}: {desc}",
                    id=f"mode-option-{mode}",
                    classes="mode-option",
                )
                option.can_focus = True
                yield option
        yield Static("", id="aidlc-phase")
        yield Static("", id="aidlc-progress")
        yield Static("", id="aidlc-completed")
        yield Static("", id="aidlc-gates")

    def on_mount(self) -> None:
        self.aidlc_mode = self._initial_mode
        self.current_phase = self._initial_phase
        self.completed_phases = self._initial_completed
        self.gate_results = self._initial_gates
        self._load_mode_from_project()
        self._refresh_display()
        self._check_state_file()
        self.set_timer(2.0, self._poll_state_file)

    def _poll_state_file(self) -> None:
        self._check_state_file()
        self._check_project_yaml()
        self.set_timer(2.0, self._poll_state_file)

    def _check_project_yaml(self) -> None:
        if self.project_path is None:
            return
        project_yaml = self.project_path / "aidlc" / "project.yaml"
        if not project_yaml.exists():
            return
        try:
            mtime = project_yaml.stat().st_mtime
            if self._project_yaml_mtime is not None and mtime != self._project_yaml_mtime:
                self._load_mode_from_project()
            self._project_yaml_mtime = mtime
        except Exception:
            pass

    def _load_mode_from_project(self) -> None:
        if self.project_path is None:
            return
        project_yaml = self.project_path / "aidlc" / "project.yaml"
        if not project_yaml.exists():
            return
        try:
            data = yaml.safe_load(project_yaml.read_text(encoding="utf-8")) or {}
            settings = data.get("settings", {})
            mode = settings.get("aidlc_mode", _DEFAULT_AIDLC_MODE)
            if mode in [m for m, _ in _AIDLC_MODE_OPTIONS]:
                self.aidlc_mode = mode
                self._update_indicators(mode)
        except Exception:
            pass

    def _save_mode_to_project(self, mode: str) -> None:
        if self.project_path is None:
            return
        project_yaml = self.project_path / "aidlc" / "project.yaml"
        if not project_yaml.exists():
            return
        try:
            data = yaml.safe_load(project_yaml.read_text(encoding="utf-8")) or {}
            if "settings" not in data:
                data["settings"] = {}
            data["settings"]["aidlc_mode"] = mode
            project_yaml.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
        except Exception:
            pass

    def _check_state_file(self) -> None:
        if self.project_path is None:
            return
        cdh_dir = self.project_path / ".cdh"
        state_file = cdh_dir / "state.json"
        if not state_file.exists():
            return
        try:
            mtime = state_file.stat().st_mtime
            if self._state_mtime is not None and mtime != self._state_mtime:
                self._load_state_from_file()
            self._state_mtime = mtime
        except Exception:
            pass

    def _load_state_from_file(self) -> None:
        if self.project_path is None:
            return
        cdh_dir = self.project_path / ".cdh"
        state_file = cdh_dir / "state.json"
        if not state_file.exists():
            return
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.refresh_from_state(state)
        except Exception:
            pass

    def watch_project_path(self, path: Path | None) -> None:
        self._state_mtime = None
        self._project_yaml_mtime = None
        self._check_state_file()
        self._check_project_yaml()

    def watch_aidlc_mode(self, mode: str) -> None:
        if self._is_ready():
            self._update_indicators(mode)
            self._refresh_display()

    def watch_current_phase(self, phase: str) -> None:
        if self._is_ready():
            self._refresh_display()

    def watch_completed_phases(self, completed: list[str]) -> None:
        if self._is_ready():
            self._refresh_display()

    def watch_gate_results(self, gates: dict) -> None:
        if self._is_ready():
            self._refresh_display()

    def refresh_from_state(self, state: dict) -> None:
        self.current_phase = state.get("current_phase", "")
        self.completed_phases = state.get("completed_phases", [])
        self.gate_results = state.get("gate_results", {})

    def _is_ready(self) -> bool:
        if not self.is_mounted:
            return False
        try:
            self.query_one("#aidlc-mode-options")
            return True
        except Exception:
            return False

    def _update_indicators(self, active_mode: str) -> None:
        for mode, desc in _AIDLC_MODE_OPTIONS:
            option = self.query_one(f"#mode-option-{mode}", Static)
            if mode == active_mode:
                option.update(f"\u25cf {mode}: {desc}")
                option.classes = "mode-option active"
            else:
                option.update(f"\u25cb {mode}: {desc}")
                option.classes = "mode-option"

    def _on_click(self, event) -> None:
        event.stop()
        widget_id = event.widget.id
        if widget_id and widget_id.startswith("mode-option-"):
            mode = widget_id.replace("mode-option-", "")
            if mode in [m for m, _ in _AIDLC_MODE_OPTIONS] and mode != self.aidlc_mode:
                self.aidlc_mode = mode
                self._save_mode_to_project(mode)
                self._update_indicators(mode)
                self.post_message(AIDLCModeChanged(mode))

    def _refresh_display(self) -> None:
        phase = self.current_phase
        completed = self.completed_phases
        gates = self.gate_results

        label = _PHASE_LABELS.get(phase, phase or "\u2014")
        phase_label = self.query_one("#aidlc-phase", Static)
        phase_label.update(f"Phase: {label}")

        progress = self.query_one("#aidlc-progress", Static)
        if completed or phase:
            done = len(completed) + (1 if phase and phase in _PHASE_ORDER and phase not in completed else 0)
            progress.update(f"Progress: {done} phase{'s' if done > 1 else ''}")
        else:
            progress.update("")
        completed_label = self.query_one("#aidlc-completed", Static)
        if completed:
            names = [_PHASE_LABELS.get(p, p) for p in completed if p != "init"]
            completed_label.update("Completed: " + ", ".join(names))
        else:
            completed_label.update("")

        gates_label = self.query_one("#aidlc-gates", Static)
        if gates:
            passed = sum(1 for r in gates.values() if isinstance(r, dict) and r.get("status") == "passed")
            failed = sum(1 for r in gates.values() if isinstance(r, dict) and r.get("status") == "failed")
            total_gates = len(gates)
            parts = []
            if passed:
                parts.append(f"\u2713 {passed}")
            if failed:
                parts.append(f"\u2717 {failed}")
            if total_gates - passed - failed:
                parts.append(f"\u2219 {total_gates - passed - failed}")
            gates_label.update("Gates: " + " ".join(parts) if parts else f"Gates: {total_gates} total")
        else:
            gates_label.update("")
