from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static, ListView, ListItem, Label, Input

from rich.text import Text


class ConfigScreen(Screen):
    """Screen-based dialog replacing ConfigPanel — select or info modes."""

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel"),
        Binding("up", "cursor_up", "Up", priority=True),
        Binding("down", "cursor_down", "Down", priority=True),
    ]

    DEFAULT_CSS = """
    ConfigScreen { align: center middle; }

    ConfigScreen > #config-dialog { width: 66; max-height: 30; padding: 1 2; }
    #config-header { width: 100%; text-align: center; text-style: bold; padding: 1 0; }
    #config-list { height: 1fr; max-height: 16; overflow-y: auto; }
    #config-list ListItem { padding: 0 1; }
    #config-list ListItem.-highlight { text-style: bold; }
    #config-list ListItem.-highlight > Label { padding: 0 0 0 1; }
    #config-text { height: auto; max-height: 16; overflow-y: auto; padding: 0 1; }
    #config-hint { width: 100%; text-align: center; margin-top: 1; }
    """

    def __init__(
        self,
        title: str,
        items: list[tuple[str, str]] | None = None,
        prefix: str = "",
        text: str = "",
        execute: bool = False,
    ):
        super().__init__()
        self._title = title
        self._items = items or []
        self._prefix = prefix
        self._text = text
        self._index = 0
        self._mode = "select" if self._items else "info"
        self._execute = execute

    def compose(self) -> ComposeResult:
        with Vertical(id="config-dialog"):
            yield Static(f" {self._title} ", id="config-header")
            yield ListView(id="config-list")
            yield Static("", id="config-text")
            hint = (
                "[↑/↓] Navigate  [Enter] Execute  [Esc] Cancel"
                if self._mode == "select"
                else "[Esc] Cancel"
            )
            yield Static(hint, id="config-hint")

    def on_mount(self) -> None:
        if self._mode == "select":
            self._show_select()
        else:
            self._show_info()

    def _show_select(self) -> None:
        list_view = self.query_one("#config-list", ListView)
        text_widget = self.query_one("#config-text", Static)
        text_widget.display = False
        t = getattr(self.app, 'tui_theme', None)
        text_style = t.variables.get('text_bright', '#a9b1d6') if t else "#a9b1d6"

        for i, (label, _) in enumerate(self._items):
            prefix = "\u25b8 " if i == self._index else "  "
            item = ListItem(Label(Text(f"{prefix}{label}", style=text_style)))
            if i == self._index:
                item.add_class("-highlight")
            list_view.append(item)

        if list_view.children:
            list_view.index = self._index
            list_view.focus()

    def _show_info(self) -> None:
        list_view = self.query_one("#config-list", ListView)
        list_view.display = False

        text_widget = self.query_one("#config-text", Static)
        text_widget.display = True
        t = getattr(self.app, 'tui_theme', None)
        text_widget.update(Text(self._text, style=t.variables.get('text_bright', '#a9b1d6') if t else "#a9b1d6"))

    def action_cursor_up(self) -> None:
        if self._mode != "select" or not self._items:
            return
        self._index = (self._index - 1) % len(self._items)
        self._refresh_selection()

    def action_cursor_down(self) -> None:
        if self._mode != "select" or not self._items:
            return
        self._index = (self._index + 1) % len(self._items)
        self._refresh_selection()

    def _refresh_selection(self) -> None:
        list_view = self.query_one("#config-list", ListView)
        for i, child in enumerate(list_view.children):
            if i == self._index:
                child.add_class("-highlight")
            else:
                child.remove_class("-highlight")
        list_view.index = self._index

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        event.stop()
        if self._mode != "select" or event.list_view.id != "config-list":
            return
        idx = event.list_view.index
        if idx is not None and 0 <= idx < len(self._items):
            label, value = self._items[idx]
            if not value or not label or label.startswith("\u2500"):
                return
            cmd = f"/{self._prefix}{value}"
            if self._execute:
                from cdh.tui.commands.registry import CommandRegistry
                # Dismiss before dispatch — dispatch may push a new ConfigScreen
                # via show_config_panel when _config_flow is True
                self.dismiss()
                result = CommandRegistry.dispatch(self.app, cmd)
                self.app._config_flow = False
                if result:
                    self.app.handle_command_result(cmd, result)
                return
            else:
                inp = self.app.query_one("#chat-input", Input)
                inp.value = cmd
        self.app._config_flow = False
        self.dismiss()

    def action_dismiss(self) -> None:
        self.app._config_flow = False
        self.dismiss()
