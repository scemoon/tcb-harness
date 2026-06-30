from __future__ import annotations

from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Footer, Static


class ComponentPickerScreen(ModalScreen[Optional[list[str]]]):
    """Modal screen for selecting application components.

    Returns the list of selected component ids, or None if cancelled.
    If ``allow_empty`` is False (default), confirming with no selection
    shows a notification and does not dismiss the screen.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    CSS = """
    ComponentPickerScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #picker-dialog {
        width: 78;
        height: auto;
        max-height: 90%;
        background: $surface;
        border: solid $border;
        padding: 0 1;
    }

    #picker-title {
        height: 1;
        background: $panel;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }

    #picker-subtitle {
        height: 1;
        color: $text-muted;
        padding: 0 1;
        margin-bottom: 1;
    }

    #picker-list {
        height: auto;
        max-height: 22;
        padding: 0 1;
        background: $surface;
    }

    .component-row {
        height: 2;
        padding: 0 1;
        background: $surface;
    }

    .component-row Checkbox {
        width: 1fr;
        background: $surface;
        color: $text;
    }

    .component-row Checkbox > .toggle--button {
        background: $panel;
        color: $text-muted;
    }

    .component-row Checkbox.-on > .toggle--button {
        background: $primary;
        color: $text;
    }

    .component-row Checkbox > .toggle--label {
        color: $text;
    }

    Footer {
        background: $panel;
        color: $text-muted;
    }

    #picker-buttons {
        height: 3;
        align: center middle;
        background: $panel;
    }

    #picker-buttons Button {
        margin: 0 1;
        background: $panel;
        color: $text;
    }

    #picker-buttons Button:hover {
        background: $primary-darken-2;
    }

    #picker-buttons #picker-confirm {
        background: $primary-background;
        color: $text;
    }

    #picker-buttons #picker-confirm:hover {
        background: $primary-darken-1;
    }
    """

    def __init__(
        self,
        title: str = "Select Application Components",
        subtitle: str = "Choose the components for this project.",
        allow_empty: bool = False,
    ) -> None:
        super().__init__()
        self._title_text = title
        self._subtitle_text = subtitle
        self._allow_empty = allow_empty

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-dialog"):
            yield Static(self._title_text, id="picker-title")
            yield Static(self._subtitle_text, id="picker-subtitle")
            with VerticalScroll(id="picker-list"):
                from cdh.scaffold import COMPONENTS

                for spec in COMPONENTS:
                    label = f"{spec.label}  \u2014  {spec.description}"
                    yield Checkbox(label, id=f"comp-{spec.id}", classes="component-row")
            with Horizontal(id="picker-buttons"):
                yield Button("Cancel", id="picker-cancel")
                yield Button("Confirm", id="picker-confirm", variant="primary")
        yield Footer()

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#picker-cancel")
    def on_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#picker-confirm")
    def on_confirm(self) -> None:
        selected: list[str] = []
        from cdh.scaffold import COMPONENTS

        for spec in COMPONENTS:
            cb = self.query_one(f"#comp-{spec.id}", Checkbox)
            if cb.value:
                selected.append(spec.id)
        if not selected and not self._allow_empty:
            self.notify(
                "Select at least one application component",
                title="No components selected",
                severity="error",
            )
            return
        self.dismiss(selected)
