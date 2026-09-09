from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual import containers
from textual import widgets
from textual.message import Message


class SideBarCollapsible(widgets.Collapsible):
    BINDING_GROUP_TITLE = "Sidebar collapsible"
    BINDINGS = [
        Binding("down", "focus_content", "Focus content", show=False),
    ]
    HELP = """\
## Sidebar

This is your sidebar.

The Sidebar contains additonal information associated with the conversation.

- **tab / shift+tab** Navigate sections
- **enter** expand or collapse secions
"""

    def action_focus_content(self) -> None:
        """Move focus into the content area when expanded."""
        if self.collapsed:
            return
        self.screen.focus_next()


class SideBar(containers.Vertical):
    BINDING_GROUP_TITLE = "Sidebar"
    BINDINGS = [("escape", "dismiss", "Dismiss sidebar")]

    class Dismiss(Message):
        pass

    @dataclass(frozen=True)
    class Panel:
        title: str
        widget: Widget
        flex: bool = False
        collapsed: bool = False
        id: str | None = None

    def __init__(
        self,
        *panels: Panel,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
        hide: bool = False,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self.panels: list[SideBar.Panel] = [*panels]
        self.hide = hide

    def on_mount(self) -> None:
        self.trap_focus()

    def compose(self) -> ComposeResult:
        for panel in self.panels:
            yield SideBarCollapsible(
                panel.widget,
                title=panel.title,
                collapsed=panel.collapsed,
                classes="-flex" if panel.flex else "-fixed",
                id=panel.id,
            )

    def action_dismiss(self) -> None:
        self.post_message(self.Dismiss())

    def has_panel(self, panel_id: str) -> bool:
        return self.query_one_optional(f"#{panel_id}") is not None

    async def add_panel(self, panel: Panel) -> SideBarCollapsible:
        collapsible = SideBarCollapsible(
            panel.widget,
            title=panel.title,
            collapsed=panel.collapsed,
            classes="-flex" if panel.flex else "-fixed",
            id=panel.id,
        )
        await self.mount(collapsible)
        self.panels.append(panel)
        return collapsible

    def remove_panel(self, panel_id: str) -> bool:
        for i, p in enumerate(self.panels):
            if p.id == panel_id:
                widget = self.query_one_optional(f"#{panel_id}")
                if widget is not None:
                    widget.remove()
                self.panels.pop(i)
                return True
        return False


if __name__ == "__main__":
    from textual.app import App, ComposeResult

    class SApp(App):
        def compose(self) -> ComposeResult:
            yield SideBar(
                SideBar.Panel("Hello", widgets.Label("Hello, World!")),
                SideBar.Panel(
                    "Files",
                    widgets.DirectoryTree(
                        "~/",
                    ),
                    flex=True,
                ),
                SideBar.Panel(
                    "Hello",
                    widgets.Static("Where there is a Will! " * 10),
                ),
            )

    SApp().run()
