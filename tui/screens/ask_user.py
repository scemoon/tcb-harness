from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual import widgets
from textual import containers


class AskUserScreen(ModalScreen[dict]):
    """Modal dialog showing the agent's question with a text input for the user's answer."""

    DEFAULT_CSS = """
    AskUserScreen {
        align: center middle;
    }
    #ask-user-container {
        width: 60;
        height: auto;
        padding: 2 3;
        background: $surface;
        border: thick $primary;
    }
    #ask-user-label {
        text-style: bold;
        margin-bottom: 1;
    }
    #ask-user-question {
        margin-bottom: 1;
    }
    #ask-user-input {
        margin-bottom: 1;
    }
    #ask-user-context {
        margin-bottom: 1;
        color: $text-muted;
    }
    #ask-user-buttons {
        height: 3;
        align: center middle;
    }
    #ask-user-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        question: str,
        context: str = "",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._question = question
        self._context = context
        super().__init__(name=name, id=id, classes=classes)

    def compose(self) -> ComposeResult:
        with containers.VerticalGroup(id="ask-user-container"):
            yield widgets.Static("❓ Agent asks:", id="ask-user-label")
            yield widgets.Static(self._question, id="ask-user-question")
            yield widgets.Input(
                placeholder="Type your answer…",
                id="ask-user-input",
            )
            if self._context:
                yield widgets.Static(self._context, id="ask-user-context")
            with containers.HorizontalGroup(id="ask-user-buttons"):
                yield widgets.Button("Submit", id="ask-user-submit", variant="primary")
                yield widgets.Button("Cancel", id="ask-user-cancel")

    def on_mount(self) -> None:
        self.query_one("#ask-user-input", widgets.Input).focus()

    @on(widgets.Input.Submitted, "#ask-user-input")
    def on_input_submitted(self) -> None:
        self.action_submit()

    @on(widgets.Button.Pressed, "#ask-user-submit")
    def action_submit(self) -> None:
        input_widget = self.query_one("#ask-user-input", widgets.Input)
        answer = input_widget.value.strip()
        self.dismiss({"answer": answer, "cancelled": False})

    @on(widgets.Button.Pressed, "#ask-user-cancel")
    def action_cancel(self) -> None:
        self.dismiss({"answer": "", "cancelled": True})
