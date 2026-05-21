from __future__ import annotations

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, ListView, ListItem, Label
from rich.text import Text

from cdh.lifecycle.manager import STAGE_ORDER, LifecycleStage, StageStatus

STATUS_ICONS = {
    StageStatus.PENDING:     "\u25cb",
    StageStatus.IN_PROGRESS: "\u25d0",
    StageStatus.COMPLETED:   "\u25c9",
    StageStatus.FAILED:      "\u2716",
}

STAGE_LABELS = {
    LifecycleStage.SPEC:    "Spec",
    LifecycleStage.DESIGN:  "Design",
    LifecycleStage.CODING:  "Coding",
    LifecycleStage.TESTING: "Test",
    LifecycleStage.DEPLOY:  "Deploy",
}

PIPELINE_ICONS = {
    "init":    "\u2699",
    "spec":    "\u25cb",
    "design":  "\u25d0",
    "coding":  "\u25c9",
    "testing": "\u2716",
    "deploy":  "\u2716",
}


class RightPanel(Vertical):
    """Right sidebar — DeepSeek TUI style PLAN / TASKS / TODOS."""

    DEFAULT_CSS = """
    RightPanel {
        background: transparent;
        padding: 0;
        height: 100%;
    }

    RightPanel .section-title {
        text-style: bold;
        padding: 0;
    }

    RightPanel ListView {
        height: auto;
        border: none;
        background: transparent;
    }

    RightPanel ListView > ListItem {
        padding: 0 0 0 0;
    }

    RightPanel .hidden {
        display: none;
    }

    RightPanel .section-rule {
        color: $text_dim;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._plan_section: list = []
        self._tasks_section: list = []
        self._todos_section: list = []

    def compose(self) -> ComposeResult:
        app = self.app
        t = getattr(app, 'tui_theme', None)
        p = t.primary if t else "#7aa2f7"
        g = t.success if t else "#9ece6a"
        y = t.warning if t else "#e0af68"

        yield Static(Text("\u25a0  TASKS", style=f"bold {g}"), classes="section-title tasks-title")
        yield Static("\u2500" * 16, classes="section-rule tasks-rule")
        yield ListView(id="tasks-list", classes="tasks-section")

        yield Static(Text("\u25a0  TODOS", style=f"bold {y}"), classes="section-title todos-title")
        yield Static("\u2500" * 16, classes="section-rule todos-rule")
        yield ListView(id="todos-list", classes="todos-section")

        yield Static(Text("\u25a0  PLAN", style=f"bold {p}"), classes="section-title plan-title")
        yield Static("\u2500" * 16, classes="section-rule plan-rule")
        yield ListView(id="plan-list", classes="plan-section")

    def on_mount(self) -> None:
        self._do_refresh()

    def refresh_panels(self) -> None:
        self._do_refresh()

    def _do_refresh(self) -> None:
        self._refresh_plan()
        self._refresh_tasks([])
        self._refresh_todos([])

    def _refresh_plan(self) -> None:
        app = self.app
        lv = self.query_one_optional("#plan-list", ListView)
        if lv is None:
            return
        lv.clear()
        t = getattr(app, 'tui_theme', None)
        dim = t.variables.get('text_dim', '#565f89') if t else "#565f89"
        bright = t.foreground if t else "#c0caf5"
        primary = t.primary if t else "#7aa2f7"

        engine = getattr(app, "agent", None)
        pipeline = getattr(engine, "_pipeline", None) if engine else None
        project = getattr(app, "current_project", None)
        is_harness = (
            project
            and pipeline is not None
            and pipeline.project_name is not None
        )

        if is_harness:
            project_dir = app.projects_dir / project
            state_file = project_dir / ".harness" / "state.json"
            config_file = project_dir / ".harness" / "config.json"
            state = {}
            config = {}
            if state_file.exists():
                import json
                try:
                    state = json.loads(state_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            if config_file.exists():
                import json
                try:
                    config = json.loads(config_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            phase = state.get("phase", "init")
            status = state.get("status", "unknown")
            phase_history = {h["phase"] for h in state.get("phaseHistory", [])}
            platform = config.get("platform", "?")

            lv.append(ListItem(Label(Text(f"  {project}", style=f"bold {primary}"))))
            lv.append(ListItem(Label(Text(
                f"  {platform}  {phase} ({status})", style=dim
            ))))

            pipeline_order = ["init", "spec", "design", "coding", "testing", "deploy"]
            phase_labels = {
                "init": "Init", "spec": "Spec", "design": "Design",
                "coding": "Coding", "testing": "Test", "deploy": "Deploy",
            }
            for p in pipeline_order:
                if p in phase_history:
                    icon = "\u25c9"
                    style = dim
                elif p == phase:
                    icon = "\u25d0"
                    style = f"bold {bright}"
                else:
                    icon = "\u25cb"
                    style = dim
                lv.append(ListItem(Label(Text(f"  {icon}  {phase_labels[p]}", style=style))))
        else:
            active = (
                hasattr(app, "lifecycle")
                and app.lifecycle.current is not None
                and app.lifecycle.current != LifecycleStage.NONE
            )
            if not active:
                lv.append(ListItem(Label(Text("  tracks spec/goal/cycles", style=dim))))
                return

            lc = app.lifecycle
            for stage in STAGE_ORDER:
                st = lc.stages.get(stage, StageStatus.PENDING)
                icon = STATUS_ICONS.get(st, "\u25cb")
                label = STAGE_LABELS.get(stage, stage.value)
                is_current = lc.current == stage
                style = f"bold {bright}" if is_current else dim
                lv.append(
                    ListItem(Label(Text(f"  {icon}  {label}", style=style)))
                )

        has_content = len(lv.children) > 0
        self.query(".plan-title")[0].set_class(not has_content, "hidden")
        self.query(".plan-rule")[0].set_class(not has_content, "hidden")
        lv.set_class(not has_content, "hidden")

    def _refresh_tasks(self, tasks: list[dict]) -> None:
        tv = self.query_one_optional("#tasks-list", ListView)
        if tv is None:
            return
        tv.clear()
        if not tasks:
            has_content = False
        else:
            app = self.app
            t = getattr(app, 'tui_theme', None)
            bright = t.variables.get('text_bright', '#a9b1d6') if t else "#a9b1d6"
            icon_map = {
                "done": "\u25c9", "doing": "\u25d0", "todo": "\u25cb",
                "waiting": "\u29d6", "failed": "\u2716",
            }
            for task in tasks:
                icon = icon_map.get(task.get("status", "todo"), "\u25cb")
                name = task.get("name", "")
                tv.append(
                    ListItem(Label(Text(f"  {icon}  {name}", style=bright)))
                )

        has_content = tasks and len(tasks) > 0
        self.query(".tasks-title")[0].set_class(not has_content, "hidden")
        self.query(".tasks-rule")[0].set_class(not has_content, "hidden")
        tv.set_class(not has_content, "hidden")

    def _refresh_todos(self, todos: list[dict]) -> None:
        tdv = self.query_one_optional("#todos-list", ListView)
        if tdv is None:
            return
        tdv.clear()
        if not todos:
            has_content = False
        else:
            app = self.app
            t = getattr(app, 'tui_theme', None)
            bright = t.variables.get('text_bright', '#a9b1d6') if t else "#a9b1d6"
            for todo in todos:
                icon = "\u25c9" if todo.get("done") else "\u25cb"
                text = todo.get("text", "")
                tdv.append(
                    ListItem(Label(Text(f"  {icon}  {text}", style=bright)))
                )

        has_content = todos and len(todos) > 0
        self.query(".todos-title")[0].set_class(not has_content, "hidden")
        self.query(".todos-rule")[0].set_class(not has_content, "hidden")
        tdv.set_class(not has_content, "hidden")


class TaskManager:
    def __init__(self):
        self._tasks: list[dict] = []
        self._todos: list[dict] = []

    def add_task(self, name: str, status: str = "todo") -> None:
        self._tasks.append({"name": name, "status": status, "id": len(self._tasks) + 1})

    def update_task(self, task_id: int, status: str) -> None:
        for t in self._tasks:
            if t["id"] == task_id:
                t["status"] = status
                break

    def list_tasks(self) -> list[dict]:
        return self._tasks

    def clear_tasks(self) -> None:
        self._tasks = []

    def add_todo(self, text: str) -> None:
        self._todos.append({"text": text, "done": False, "id": len(self._todos) + 1})

    def complete_todo(self, todo_id: int) -> None:
        for t in self._todos:
            if t["id"] == todo_id:
                t["done"] = True
                break

    def remove_todo(self, todo_id: int) -> None:
        self._todos = [t for t in self._todos if t["id"] != todo_id]

    def list_todos(self) -> list[dict]:
        return self._todos

    def clear_todos(self) -> None:
        self._todos = []
