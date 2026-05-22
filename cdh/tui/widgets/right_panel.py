from __future__ import annotations

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, ListView, ListItem, Label
from rich.text import Text

from cdh.lifecycle.manager import STAGE_ORDER, LifecycleStage, StageStatus
from cdh.models.messages import LifecycleStatus as AgentStatus

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

SUBAGENT_ICONS = {
    AgentStatus.PENDING:   "\u25cb",
    AgentStatus.RUNNING:   "\u25d0",
    AgentStatus.COMPLETE:  "\u25c9",
    AgentStatus.FAILED:    "\u2716",
    AgentStatus.CANCELLED: "\u2298",
}


class RightPanel(Vertical):
    """Right sidebar — DeepSeek TUI style PLAN / TASKS / TODOS / SUBAGENTS."""

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
        self._subagents: dict[str, dict] = {}

    def compose(self) -> ComposeResult:
        app = self.app
        t = getattr(app, 'tui_theme', None)
        p = t.primary if t else "#7aa2f7"
        g = t.success if t else "#9ece6a"
        y = t.warning if t else "#e0af68"
        c = t.secondary if t else "#7dcfff"

        yield Static(Text("\u25a0  TASKS", style=f"bold {g}"), classes="section-title tasks-title")
        yield Static("\u2500" * 16, classes="section-rule tasks-rule")
        yield ListView(id="tasks-list", classes="tasks-section")

        yield Static(Text("\u25a0  TODOS", style=f"bold {y}"), classes="section-title todos-title")
        yield Static("\u2500" * 16, classes="section-rule todos-rule")
        yield ListView(id="todos-list", classes="todos-section")

        yield Static(Text("\u25a0  SUBAGENTS", style=f"bold {c}"), classes="section-title subagents-title")
        yield Static("\u2500" * 16, classes="section-rule subagents-rule")
        yield ListView(id="subagents-list", classes="subagents-section")

        yield Static(Text("\u25a0  PLAN", style=f"bold {p}"), classes="section-title plan-title")
        yield Static("\u2500" * 16, classes="section-rule plan-rule")
        yield ListView(id="plan-list", classes="plan-section")

    def on_mount(self) -> None:
        self._do_refresh()

    def refresh_panels(self) -> None:
        self._do_refresh()

    def update_subagent(self, agent_id: str, agent_type: str, status: str) -> None:
        """Track sub-agent lifecycle."""
        self._subagents[agent_id] = {"type": agent_type, "status": status}
        self._refresh_subagents()

    def _do_refresh(self) -> None:
        self._refresh_plan()
        self._refresh_tasks([])
        self._refresh_todos([])
        self._refresh_subagents()

    def _get_theme_colors(self):
        app = self.app
        t = getattr(app, 'tui_theme', None)
        return {
            'dim': t.variables.get('text_dim', '#565f89') if t else "#565f89",
            'bright': t.variables.get('text_bright', '#a9b1d6') if t else "#a9b1d6",
            'foreground': t.foreground if t else "#c0caf5",
            'primary': t.primary if t else "#7aa2f7",
            'success': t.success if t else "#9ece6a",
            'warning': t.warning if t else "#e0af68",
            'error': t.error if t else "red",
            'secondary': t.secondary if t else "#7dcfff",
        }

    def _refresh_plan(self) -> None:
        app = self.app
        lv = self.query_one_optional("#plan-list", ListView)
        if lv is None:
            return
        lv.clear()
        c = self._get_theme_colors()

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

            lv.append(ListItem(Label(Text(f"  {project}", style=f"bold {c['primary']}"))))
            lv.append(ListItem(Label(Text(
                f"  {platform}  {phase} ({status})", style=c['dim']
            ))))

            pipeline_order = ["init", "spec", "design", "coding", "testing", "deploy"]
            phase_labels = {
                "init": "Init", "spec": "Spec", "design": "Design",
                "coding": "Coding", "testing": "Test", "deploy": "Deploy",
            }
            for p in pipeline_order:
                if p in phase_history:
                    icon = "\u25c9"
                    style = c['dim']
                elif p == phase:
                    icon = "\u25d0"
                    style = f"bold {c['foreground']}"
                else:
                    icon = "\u25cb"
                    style = c['dim']
                lv.append(ListItem(Label(Text(f"  {icon}  {phase_labels[p]}", style=style))))
        else:
            active = (
                hasattr(app, "lifecycle")
                and app.lifecycle.current is not None
                and app.lifecycle.current != LifecycleStage.NONE
            )
            if not active:
                lv.append(ListItem(Label(Text("  tracks spec/goal/cycles", style=c['dim']))))
                lv.set_class(False, "hidden")
                self.query(".plan-title")[0].set_class(False, "hidden")
                self.query(".plan-rule")[0].set_class(False, "hidden")
                return

            lc = app.lifecycle
            for stage in STAGE_ORDER:
                st = lc.stages.get(stage, StageStatus.PENDING)
                icon = STATUS_ICONS.get(st, "\u25cb")
                label = STAGE_LABELS.get(stage, stage.value)
                is_current = lc.current == stage
                style = f"bold {c['foreground']}" if is_current else c['dim']
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
        c = self._get_theme_colors()
        if not tasks:
            has_content = False
        else:
            icon_map = {
                "done": "\u25c9", "doing": "\u25d0", "todo": "\u25cb",
                "waiting": "\u29d6", "failed": "\u2716",
            }
            for task in tasks:
                icon = icon_map.get(task.get("status", "todo"), "\u25cb")
                name = task.get("name", "")
                tv.append(
                    ListItem(Label(Text(f"  {icon}  {name}", style=c['bright'])))
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
        c = self._get_theme_colors()
        if not todos:
            has_content = False
        else:
            for todo in todos:
                icon = "\u25c9" if todo.get("done") else "\u25cb"
                text = todo.get("text", "")
                tdv.append(
                    ListItem(Label(Text(f"  {icon}  {text}", style=c['bright'])))
                )

        has_content = todos and len(todos) > 0
        self.query(".todos-title")[0].set_class(not has_content, "hidden")
        self.query(".todos-rule")[0].set_class(not has_content, "hidden")
        tdv.set_class(not has_content, "hidden")

    def _refresh_subagents(self) -> None:
        """Show active sub-agent status."""
        sv = self.query_one_optional("#subagents-list", ListView)
        if sv is None:
            return
        sv.clear()
        c = self._get_theme_colors()
        
        if not self._subagents:
            sv.set_class(True, "hidden")
            self.query(".subagents-title")[0].set_class(True, "hidden")
            self.query(".subagents-rule")[0].set_class(True, "hidden")
            return
        
        has_content = False
        for agent_id, info in self._subagents.items():
            try:
                status = AgentStatus(info["status"])
            except ValueError:
                status = AgentStatus.RUNNING
            icon = SUBAGENT_ICONS.get(status, "\u25cb")
            agent_type = info.get("type", "general")
            style_map = {
                AgentStatus.RUNNING:  c['secondary'],
                AgentStatus.COMPLETE: c['success'],
                AgentStatus.FAILED:   c['error'],
                AgentStatus.PENDING:  c['dim'],
            }
            style = style_map.get(status, c['bright'])
            short_id = agent_id[:8]
            sv.append(ListItem(Label(Text(
                f"  {icon}  {agent_type} ({short_id})", style=style
            ))))
            has_content = True
        
        self.query(".subagents-title")[0].set_class(not has_content, "hidden")
        self.query(".subagents-rule")[0].set_class(not has_content, "hidden")
        sv.set_class(not has_content, "hidden")
