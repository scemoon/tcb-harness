from pathlib import Path
from time import monotonic

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual import getters
from textual.widget import Widget
from textual import widgets
from textual import containers
from textual import on


from tui.app import A2TUIApp
from tui.widgets.grid_select import GridSelect
from tui.widgets.project_grid_select import ProjectGridSelect
from tui.widgets.project_summary import ProjectSummary
from tui.screens.component_picker import ComponentPickerScreen


CONFIRM_TIMEOUT = 5.0
INSTRUCTIONS_NO_PROJECTS = "Your projects will be shown here."


def _project_db_path(name: str):
    """Return the path of the project entry in ``~/.cdh/projects/``
    for *name* across all supported extensions, or ``None`` if the
    project is not registered yet.
    """
    projects_dir = Path.home() / ".cdh" / "projects"
    for ext in ("yaml", "yml", "json"):
        pf = projects_dir / f"{name}.{ext}"
        if pf.exists():
            return pf
    return None


class ProjectsScreen(ModalScreen[str]):
    CSS_PATH = "projects.tcss"
    BINDINGS = [
        Binding("escape", "dismiss", "Dismiss", show=False),
        Binding("d", "delete_project", "Del"),
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
        with containers.Horizontal(id="actions"):
            yield widgets.Button("+ New Project", id="new-project", variant="primary")
            yield widgets.Button("Init .cdh (i)", id="init-project")
        yield widgets.Footer()

    @property
    def focus_chain(self) -> list[Widget]:
        return [
            self.project_grid_select,
            self.query_one("#new-project", widgets.Button),
            self.query_one("#init-project", widgets.Button),
        ]

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
        projects_dir = Path.home() / ".cdh" / "projects"
        deleted = False
        for ext in ["yaml", "yml", "json"]:
            pf = projects_dir / f"{project_name}.{ext}"
            if pf.exists():
                pf.unlink()
                deleted = True
                break
        if not deleted:
            self.notify("Project file not found", severity="error")
            return
        widget.remove()
        self.notify(f"Deleted project: {project_name}")

    def action_new_project(self) -> None:
        from pathlib import Path
        from tui.widgets.edit_field import EditFieldScreen

        default_path = str(Path.cwd().resolve())
        self.app.push_screen(
            EditFieldScreen("Project path", default_path),
            self._on_new_project_path,
        )

    def _on_new_project_path(self, path_str: str | None) -> None:
        from pathlib import Path

        if not path_str:
            return
        try:
            target = Path(path_str).expanduser().resolve()
        except Exception:
            self.notify("Invalid path", severity="error")
            return
        if _project_db_path(target.name) is not None:
            self.notify(
                f"Project '{target.name}' is already in the project list",
                severity="warning",
            )
            return
        self.app.push_screen(
            ComponentPickerScreen(
                title="New Project — Select Components",
                subtitle=(
                    f"Project path: {target}\n"
                    "Cross-cutting items (contracts, shared types, etc.) are created automatically."
                ),
                allow_empty=False,
            ),
            lambda picked: self._on_new_project_components(target, picked),
        )

    async def _on_new_project_components(
        self,
        target: "Path",
        picked: list[str] | None,
    ) -> None:
        if picked is None:
            self.notify("New project cancelled", severity="warning")
            return
        if not picked:
            return
        await self._do_new_project(target, picked)

    async def _do_new_project(
        self,
        target: "Path",
        components: list[str],
    ) -> None:
        from pathlib import Path
        from cdh.project_loader import CdhProjectLoader

        name = target.name
        from cdh.scaffold import scaffold_dlc_project

        try:
            scaffold_dlc_project(target, name, components=components)
        except (ValueError, RuntimeError) as e:
            self.notify(str(e), severity="error")
            return
        if _project_db_path(name) is not None:
            self.notify(
                f"Project '{name}' is already in the project list",
                severity="error",
            )
            return
        projects_dir = Path.home() / ".cdh" / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        proj_file = projects_dir / f"{name}.yaml"
        CdhProjectLoader.init_project(target, name)
        import yaml
        proj_data = {"name": name, "path": str(target), "description": ""}
        proj_file.write_text(yaml.dump(proj_data))
        await self.project_grid_select.reload()
        self.project_grid_select.highlighted = len(self.project_grid_select.children) - 1
        self.notify(
            f"Created project '{name}' at {target} "
            f"(components: {', '.join(components)})"
        )

    def action_init_project(self) -> None:
        from pathlib import Path
        from tui.widgets.edit_field import EditFieldScreen

        default_path = str(Path.cwd().resolve())
        self.app.push_screen(
            EditFieldScreen("Directory to initialize .cdh", default_path),
            self._on_init_path,
        )

    async def _on_init_path(self, path_str: str | None) -> None:
        from pathlib import Path
        from cdh.project_loader import CdhProjectLoader

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
        if existing is not None and existing.parent == target:
            self.notify(f".cdh already exists at {existing}", severity="warning")
            return
        if _project_db_path(target.name) is not None:
            self.notify(
                f"Project '{target.name}' is already in the project list",
                severity="warning",
            )
            return
        await self._do_init_project(target, [])

    async def _do_init_project(
        self,
        target: "Path",
        components: list[str],
    ) -> None:
        from pathlib import Path
        from cdh.project_loader import CdhProjectLoader
        from cdh.scaffold import add_component, init_dlc_project

        name = target.name
        if _project_db_path(name) is not None:
            self.notify(
                f"Project '{name}' is already in the project list",
                severity="error",
            )
            return
        try:
            init_dlc_project(target, name)
        except (ValueError, RuntimeError) as e:
            self.notify(str(e), severity="error")
            return
        for cid in components:
            try:
                add_component(target, cid)
            except (ValueError, FileNotFoundError) as e:
                self.notify(str(e), severity="error")
        CdhProjectLoader.init_project(target, name)
        import yaml
        projects_dir = Path.home() / ".cdh" / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        proj_file = projects_dir / f"{name}.yaml"
        proj_data = {"name": name, "path": str(target), "description": ""}
        proj_file.write_text(yaml.dump(proj_data))
        await self.project_grid_select.reload()
        self.project_grid_select.highlighted = len(self.project_grid_select.children) - 1
        suffix = (
            f" (components: {', '.join(components)})"
            if components
            else " (no components)"
        )
        self.notify(f"Initialized .cdh in {target}{suffix}")

    @on(GridSelect.Selected)
    def on_selected(self, event: GridSelect.Selected) -> None:
        if (
            isinstance(event.widget, ProjectSummary)
        ):
            self.dismiss(event.widget.id)

    @on(widgets.Button.Pressed, "#new-project")
    def on_new_project(self) -> None:
        self.action_new_project()

    @on(widgets.Button.Pressed, "#init-project")
    def on_init_project(self) -> None:
        self.action_init_project()
