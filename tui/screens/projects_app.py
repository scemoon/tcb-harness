from __future__ import annotations

from pathlib import Path
from time import monotonic

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import var
from textual.widget import Widget
from textual.widgets import Button, Label, Static

from cdha.config import CLOUD_DEV_HARNESS_DIR, load_config, save_config
from cdha.agent.cdh_loader import CdhProjectLoader
from cdha.config_screen import EditFieldScreen

import yaml

CONFIRM_TIMEOUT = 5.0


class ProjectItem(Static, can_focus=True):
    """A single project row in the list."""

    def __init__(self, name: str, path: str) -> None:
        super().__init__()
        self._name = name
        self._path = path

    def render(self) -> str:
        return f"  {self._name:<20} {self._path}"


class ProjectsApp(App):
    """Standalone project management TUI."""

    CSS = """
    Screen {
        align: center middle;
    }
    ProjectsApp {
        background: #000;
    }
    #dialog {
        width: 64;
        height: 20;
        background: #000;
        border: solid #555;
    }
    #header {
        height: 2;
        background: #333;
        content-align: center middle;
        color: #fff;
        text-style: bold;
    }
    #content {
        width: 100%;
        height: 1fr;
        background: #000;
    }
    ProjectItem {
        width: 100%;
        height: 1;
        padding: 0 1;
        color: #fff;
        background: #000;
    }
    ProjectItem:hover, ProjectItem.-focus {
        background: #444;
    }
    #shortcuts {
        height: 1;
        background: #222;
        color: #888;
        padding: 0 1;
        content-align: left middle;
    }
    #button-row {
        height: 3;
        background: #333;
        align: center middle;
    }
    Button {
        margin: 0 1;
        background: #444;
        color: #fff;
    }
    Button:hover {
        background: #666;
    }
    Button:focus {
        background: #555;
    }
    #empty-label {
        width: 100%;
        height: 100%;
        content-align: center middle;
        color: #666;
    }
    """

    BINDINGS = [
        ("up", "cursor_up", "Up"),
        ("down", "cursor_down", "Down"),
        ("enter", "confirm", "Select"),
        ("n", "new_project", "New"),
        ("d", "delete_project", "Delete"),
        ("ctrl+q", "quit", "Quit"),
        ("escape", "dismiss_modal", "Cancel"),
    ]

    cursor: var[int] = var(0)
    _delete_confirm_time: float = 0.0

    def __init__(self) -> None:
        super().__init__()
        self.projects: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("Project Management", id="header")
            with Widget(id="content"):
                pass
            yield Label("↑↓ Select  ↵ Load  n New  d Delete  Ctrl+Q Quit", id="shortcuts")
            with Horizontal(id="button-row"):
                yield Button("Load (↵)", id="load")
                yield Button("New (n)", id="new", variant="primary")
                yield Button("Delete (d)", id="delete")

    def _rebuild_items(self) -> None:
        content = self.query_one("#content")
        content.remove_children()
        if not self.projects:
            content.mount(Static("No projects found", id="empty-label"))
            return
        for name, path in self.projects:
            content.mount(ProjectItem(name, path))
        self.cursor = 0

    def _clamp_cursor(self) -> None:
        if not self.projects:
            return
        self.cursor = max(0, min(self.cursor, len(self.projects) - 1))

    def watch_cursor(self, old: int, new: int) -> None:
        if not self.projects:
            return
        items = list(self.query(ProjectItem))
        for i, item in enumerate(items):
            item.set_class(i == new, "-focus")

    @property
    def _current_item(self) -> ProjectItem | None:
        items = list(self.query(ProjectItem))
        if 0 <= self.cursor < len(items):
            return items[self.cursor]
        return None

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        projects_dir = CLOUD_DEV_HARNESS_DIR / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        pf_list = sorted(
            list(projects_dir.glob("*.yaml")) + list(projects_dir.glob("*.json"))
        )
        self.projects = []
        for pf in pf_list:
            try:
                data = yaml.safe_load(pf.read_text()) or {}
                p = data.get("path", ".")
            except Exception:
                p = "."
            self.projects.append((pf.stem, p))
        self._rebuild_items()

    def action_cursor_up(self) -> None:
        self.cursor -= 1
        self._clamp_cursor()

    def action_cursor_down(self) -> None:
        self.cursor += 1
        self._clamp_cursor()

    def action_confirm(self) -> None:
        self._load_project()

    def action_new_project(self) -> None:
        self._new_project()

    def action_delete_project(self) -> None:
        self._delete_project()

    def action_quit(self) -> None:
        self.exit()

    def action_dismiss_modal(self) -> None:
        pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "new":
            self._new_project()
        elif btn_id == "load":
            self._load_project()
        elif btn_id == "delete":
            self._delete_project()

    def _new_project(self) -> None:
        self.push_screen(
            EditFieldScreen("Project path", str(Path.cwd().resolve())),
            self._on_new_project_path,
        )

    def _on_new_project_path(self, path_str: str | None) -> None:
        try:
            ws = Path(path_str).expanduser().resolve() if path_str else Path.cwd().resolve()
        except Exception:
            ws = Path.cwd().resolve()
        name = ws.name
        CdhProjectLoader.init_project(ws, name)
        projects_dir = CLOUD_DEV_HARNESS_DIR / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        proj_data = {"name": name, "path": str(ws), "description": ""}
        (projects_dir / f"{name}.yaml").write_text(yaml.dump(proj_data))
        cfg = load_config()
        cfg.current_project = name
        cfg.current_project_path = str(ws)
        save_config(cfg)
        self.notify(f"Created project '{name}' at {ws}")
        self._refresh()

    def _load_project(self) -> None:
        item = self._current_item
        if item is None:
            self.notify("No project selected", severity="warning")
            return
        name = item._name
        projects_dir = CLOUD_DEV_HARNESS_DIR / "projects"
        for ext in ["yaml", "yml", "json"]:
            pf = projects_dir / f"{name}.{ext}"
            if pf.exists():
                proj_data = yaml.safe_load(pf.read_text()) if ext in ["yaml", "yml"] else __import__("json").loads(pf.read_text())
                project_path = proj_data.get("path", ".")
                cfg = load_config()
                cfg.current_project = name
                cfg.current_project_path = project_path
                save_config(cfg)
                self.notify(f"Loaded project '{name}' ({project_path})")
                self.exit("loaded")
                return
        self.notify(f"Project '{name}' not found", severity="error")

    def _delete_project(self) -> None:
        now = monotonic()
        if now - self._delete_confirm_time > CONFIRM_TIMEOUT:
            self._delete_confirm_time = now
            self.notify(
                "Press [b]d[/b] again to confirm deletion",
                title="Delete project",
                timeout=CONFIRM_TIMEOUT,
            )
            return
        self._delete_confirm_time = 0.0
        item = self._current_item
        if item is None:
            self.notify("No project selected", severity="warning")
            return
        name = item._name
        projects_dir = CLOUD_DEV_HARNESS_DIR / "projects"
        for ext in ["yaml", "yml", "json"]:
            pf = projects_dir / f"{name}.{ext}"
            if pf.exists():
                pf.unlink()
                self.notify(f"Deleted project '{name}'")
                self._refresh()
                return
        self.notify(f"Project '{name}' not found", severity="error")


def main():
    return ProjectsApp().run()
