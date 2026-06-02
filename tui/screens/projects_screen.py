from textual.app import ComposeResult
from textual.binding import Binding
from textual.events import ScreenResume
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


INSTRUCTIONS_NO_PROJECTS = "Your projects will be shown here."


class ProjectsScreen(ModalScreen[str]):
    CSS_PATH = "projects.tcss"
    BINDINGS = [Binding("escape", "dismiss", "Dismiss")]

    app: getters.app[A2TUIApp] = getters.app(A2TUIApp)
    project_grid_select = getters.query_one(ProjectGridSelect)

    def compose(self) -> ComposeResult:
        with containers.Center(id="title-container"):
            yield widgets.Label("Projects")
        yield widgets.Static(INSTRUCTIONS_NO_PROJECTS, classes="instructions")
        yield ProjectGridSelect()
        yield widgets.Footer()

    @property
    def focus_chain(self) -> list[Widget]:
        return [self.project_grid_select]

    @on(GridSelect.Selected)
    def on_selected(self, event: GridSelect.Selected) -> None:
        if (
            isinstance(event.widget, ProjectSummary)
        ):
            self.dismiss(event.widget.id)
