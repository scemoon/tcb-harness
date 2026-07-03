from pathlib import Path

import yaml
from textual.app import ComposeResult
from textual import getters

from tui.app import A2TUIApp
from tui.widgets.grid_select import GridSelect
from tui.widgets.project_summary import ProjectSummary


def _read_project_path(pf: Path) -> str:
    """Return the project directory path stored in ``pf``, or the
    yaml/json file path as a fallback."""
    try:
        if pf.suffix == ".json":
            import json

            data = json.loads(pf.read_text(encoding="utf-8")) or {}
        else:
            data = yaml.safe_load(pf.read_text(encoding="utf-8")) or {}
        path = data.get("path")
        if isinstance(path, str) and path:
            return path
    except Exception:
        pass
    return str(pf)


class ProjectGridSelect(GridSelect):
    FOCUS_ON_CLICK = True
    app: getters.app[A2TUIApp] = getters.app(A2TUIApp)

    def __init__(
        self,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(
            id=id,
            classes=classes,
            min_column_width=36,
        )

    def allow_focus(self) -> bool:
        return True

    def compose(self) -> ComposeResult:
        projects_dir = Path.home() / ".cdh" / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        project_files = list(projects_dir.glob("*.yaml")) + list(projects_dir.glob("*.json"))
        for pf in sorted(project_files):
            yield ProjectSummary(pf.stem, _read_project_path(pf), id=pf.stem)

    async def reload(self) -> None:
        await self.remove_children()
        projects_dir = Path.home() / ".cdh" / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        project_files = list(projects_dir.glob("*.yaml")) + list(projects_dir.glob("*.json"))
        for pf in sorted(project_files):
            self.mount(ProjectSummary(pf.stem, _read_project_path(pf), id=pf.stem))

    def refresh(self, **kwargs) -> None:
        super().refresh(**kwargs)
