from textual.app import ComposeResult
from textual import containers
from textual import widgets


class ProjectSummary(containers.VerticalGroup):
    def __init__(
        self,
        project_name: str,
        project_path: str,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._project_name = project_name
        self._project_path = project_path

    def compose(self) -> ComposeResult:
        with containers.HorizontalGroup():
            yield widgets.Label("❯", classes="icon")
            with containers.VerticalGroup():
                yield widgets.Label(
                    self._project_name,
                    classes="title",
                    markup=False,
                )
                with containers.HorizontalGroup():
                    yield widgets.Label("📁 ")
                    yield widgets.Label(
                        self._project_path,
                        classes="path",
                        markup=False,
                    )
