from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static

_PHASE_LABELS: dict[str, str] = {
    "init": "Initialized",
    "understand": "\u2460 Understand",
    "plan": "\u2461 Plan",
    "verify": "\u2462 Verify",
    "deliver": "\u2463 Deliver",
}

_PHASE_ORDER: list[str] = ["understand", "plan", "verify", "deliver"]


class AIDLCStats(Static):
    DEFAULT_CSS = """
    AIDLCStats {
        height: auto;
        padding: 0 1;

        #aidlc-phase {
            text-style: bold;
            margin: 0;
            padding: 0;
        }

        #aidlc-progress {
            color: $text-secondary;
            margin: 0;
            padding: 0;
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

    current_phase: reactive[str] = reactive("")
    completed_phases: reactive[list[str]] = reactive(list)
    gate_results: reactive[dict] = reactive(dict)

    def __init__(
        self,
        current_phase: str = "",
        completed_phases: list[str] | None = None,
        gate_results: dict | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._initial_phase = current_phase
        self._initial_completed = completed_phases or []
        self._initial_gates = gate_results or {}

    def compose(self) -> ComposeResult:
        yield Static("", id="aidlc-phase")
        yield Static("", id="aidlc-progress")
        yield Static("", id="aidlc-completed")
        yield Static("", id="aidlc-gates")

    def on_mount(self) -> None:
        self.current_phase = self._initial_phase
        self.completed_phases = self._initial_completed
        self.gate_results = self._initial_gates
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
        return self.is_mounted and self.query_children("Static")

    def _refresh_display(self) -> None:
        phase = self.current_phase
        completed = self.completed_phases
        gates = self.gate_results

        label = _PHASE_LABELS.get(phase, phase or "\u2014")
        phase_label = self.query_one("#aidlc-phase", Static)
        phase_label.update(f"Phase: {label}")

        progress = self.query_one("#aidlc-progress", Static)
        total = len(_PHASE_ORDER)
        done = sum(1 for p in _PHASE_ORDER if p in completed or p == phase)
        progress.update(f"Progress: {done}/{total} phases")
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
