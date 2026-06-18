from pathlib import Path

from textual.app import ComposeResult
from textual import getters

from tui.app import A2TUIApp
from tui.widgets.grid_select import GridSelect
from tui.widgets.project_summary import ProjectSummary
from onecode.config import CLOUD_DEV_HARNESS_DIR


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
        projects_dir = CLOUD_DEV_HARNESS_DIR / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        project_files = list(projects_dir.glob("*.yaml")) + list(projects_dir.glob("*.json"))
        for pf in sorted(project_files):
            yield ProjectSummary(pf.stem, str(pf), id=pf.stem)
