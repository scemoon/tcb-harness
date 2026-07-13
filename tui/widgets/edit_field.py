from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class EditFieldScreen(ModalScreen[str]):
    def __init__(self, field_label: str, current_value: str):
        super().__init__()
        self.field_label = field_label
        self.current_value = current_value

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Cancel"),
    ]

    CSS = """
    EditFieldScreen { background: rgba(0,0,0,0.7); align: center middle; }
    #edit-dialog { width: 50; height: 7; background: #111; border: solid #555; }
    #edit-label { height: 1; background: #333; color: #fff; padding: 0 1; }
    #edit-input { height: 3; padding: 0 1; background: #111; color: #fff; }
    #edit-buttons { height: 3; background: #222; align: center middle; }
    Button { margin: 0 1; background: #444; color: #fff; }
    Button:hover { background: #666; }
    Button:focus { background: #555; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="edit-dialog"):
            yield Label(f"  {self.field_label}", id="edit-label")
            yield Input(value=self.current_value, id="edit-input")
            with Horizontal(id="edit-buttons"):
                yield Button("Cancel", id="edit-cancel")
                yield Button("Save", id="edit-save")

    def on_mount(self) -> None:
        inp = self.query_one("#edit-input", Input)
        inp.selection_color = "#000"
        inp.selection_background = "#fff"

    @on(Button.Pressed, "#edit-save")
    def on_save(self) -> None:
        value = self.query_one("#edit-input", Input).value.strip()
        self.dismiss(value or None)

    @on(Button.Pressed, "#edit-cancel")
    def on_cancel(self) -> None:
        self.dismiss(None)

    @on(Input.Submitted)
    def on_input_submitted(self) -> None:
        value = self.query_one("#edit-input", Input).value.strip()
        self.dismiss(value or None)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)


class OptionPickerScreen(ModalScreen[str]):
    def __init__(self, field_label: str, options: list[tuple[str, str]], current_value: str):
        super().__init__()
        self.field_label = field_label
        self.options = options
        self.current_value = current_value
        self._selected_index = 0

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Cancel"),
        Binding("up", "cursor_up", "Up"),
        Binding("down", "cursor_down", "Down"),
        Binding("enter", "confirm", "Confirm"),
    ]

    CSS = """
    OptionPickerScreen { background: rgba(0,0,0,0.7); align: center middle; }
    #picker-dialog { width: 50; height: auto; background: #111; border: solid #555; max-height: 20; }
    #picker-label { height: 1; background: #333; color: #fff; padding: 0 1; }
    #picker-list { height: auto; max-height: 15; background: #000; }
    .option-item { height: 1; padding: 0 1; color: #fff; background: #000; }
    .option-item:hover, .option-item.selected { background: #444; }
    #picker-buttons { height: 3; background: #222; align: center middle; }
    Button { margin: 0 1; background: #444; color: #fff; }
    Button:hover { background: #666; }
    Button:focus { background: #555; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-dialog"):
            yield Label(f"  {self.field_label}", id="picker-label")
            with Vertical(id="picker-list"):
                pass
            with Horizontal(id="picker-buttons"):
                yield Button("Cancel (ESC)", id="picker-cancel")
                yield Button("Confirm (ENTER)", id="picker-confirm")

    def on_mount(self) -> None:
        list_container = self.query_one("#picker-list", Vertical)
        for i, (label, val) in enumerate(self.options):
            is_selected = (val == self.current_value) or (self.current_value is None and i == 0)
            if is_selected:
                self._selected_index = i
            item = Static(f"  {'>' if is_selected else ' '}{label}", classes="option-item")
            item._option_index = i
            list_container.mount(item)
        self.query_one("#picker-confirm", Button).focus()

    def _refresh_list(self) -> None:
        list_container = self.query_one("#picker-list", Vertical)
        for i, item in enumerate(list_container.children):
            if isinstance(item, Static):
                label = self.options[i][0]
                marker = ">" if i == self._selected_index else " "
                item.update(f"  {marker}{label}")

    def action_cursor_up(self) -> None:
        if self._selected_index > 0:
            self._selected_index -= 1
            self._refresh_list()

    def action_cursor_down(self) -> None:
        if self._selected_index < len(self.options) - 1:
            self._selected_index += 1
            self._refresh_list()

    def action_confirm(self) -> None:
        _, val = self.options[self._selected_index]
        self.dismiss(val)

    @on(Button.Pressed, "#picker-confirm")
    def on_confirm_button(self) -> None:
        self.action_confirm()

    @on(Button.Pressed, "#picker-cancel")
    def on_cancel(self) -> None:
        self.dismiss(None)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)
