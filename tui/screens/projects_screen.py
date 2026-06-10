from time import monotonic

from textual.app import ComposeResult
from textual.binding import Binding
from textual.events import ScreenResume
from textual.screen import ModalScreen
from textual import getters
from textual.widget import Widget
from textual import widgets
from textual import containers
from textual import on


from cdha.config import CLOUD_DEV_HARNESS_DIR

from tui.app import A2TUIApp
from tui.widgets.grid_select import GridSelect
from tui.widgets.project_grid_select import ProjectGridSelect
from tui.widgets.project_summary import ProjectSummary


CONFIRM_TIMEOUT = 5.0
INSTRUCTIONS_NO_PROJECTS = "Your projects will be shown here."


class ProjectsScreen(ModalScreen[str]):
    CSS_PATH = "projects.tcss"
    BINDINGS = [
        Binding("escape", "dismiss", "Dismiss"),
        Binding("d", "delete_project", "Delete"),
        Binding("n", "new_project", "New"),
        Binding("i", "init_project", "Init"),
    ]

    app: getters.app[A2TUIApp] = getters.app(A2TUIApp)
    project_grid_select = getters.query_one(ProjectGridSelect)
    _delete_confirm_time: float = 0.0

    def compose(self) -> ComposeResult:
        with containers.Center(id="title-container"):
            yield widgets.Label("Projects")
        yield widgets.Static(INSTRUCTIONS_NO_PROJECTS, classes="instructions")
        yield ProjectGridSelect()
        with containers.Center():
            yield widgets.Button("+ New Project", id="new-project", variant="primary")
            yield widgets.Button("Init .cdh (i)", id="init-project")
        yield widgets.Footer()

    @property
    def focus_chain(self) -> list[Widget]:
        return [self.project_grid_select]

    def action_delete_project(self) -> None:
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
        highlighted = self.project_grid_select.highlighted
        if highlighted is None:
            return
        try:
            widget = self.project_grid_select.children[highlighted]
        except IndexError:
            return
        if not isinstance(widget, ProjectSummary):
            return
        project_name = widget.id
        if project_name is None:
            return
        projects_dir = CLOUD_DEV_HARNESS_DIR / "projects"
        deleted = False
        for ext in ["yaml", "yml", "json"]:
            pf = projects_dir / f"{project_name}.{ext}"
            if pf.exists():
                pf.unlink()
                deleted = True
                break
        if not deleted:
            self.notify(f"Project file not found", severity="error")
            return
        widget.remove()
        self.notify(f"Deleted project: {project_name}")

    def action_new_project(self) -> None:
        self.dismiss("__new__")

    def action_init_project(self) -> None:
        from pathlib import Path
        from cdha.config_screen import EditFieldScreen
        from cdha.agent.cdh_loader import CdhProjectLoader

        default_path = str(Path.cwd().resolve())
        self.app.push_screen(
            EditFieldScreen("Directory to initialize .cdh", default_path),
            self._on_init_path,
        )

    def _on_init_path(self, path_str: str | None) -> None:
        from pathlib import Path
        from cdha.agent.cdh_loader import CdhProjectLoader

        if not path_str:
            return
        try:
            target = Path(path_str).expanduser().resolve()
            if not target.is_dir():
                self.notify(f"Not a directory: {target}", severity="error")
                return
        except Exception:
            self.notify("Invalid path", severity="error")
            return
        existing = CdhProjectLoader.find_cdh_dir(target)
        if existing is not None:
            self.notify(f".cdh already exists at {existing}", severity="warning")
            return
        name = target.name
        CdhProjectLoader.init_project(target, name)
        self.notify(f"Initialized .cdh in {target}")

    @on(GridSelect.Selected)
    def on_selected(self, event: GridSelect.Selected) -> None:
        if (
            isinstance(event.widget, ProjectSummary)
        ):
            self.dismiss(event.widget.id)

    @on(widgets.Button.Pressed, "#new-project")
    def on_new_project(self) -> None:
        self.dismiss("__new__")

    @on(widgets.Button.Pressed, "#init-project")
    def on_init_project(self) -> None:
        self.action_init_project()
