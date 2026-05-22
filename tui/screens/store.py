from pathlib import Path

from textual.binding import Binding
from textual.screen import Screen
from textual.app import ComposeResult
from textual.content import Content
from textual import containers, widgets

from tui.app import TUI2App
from tui.format_path import format_path
from tui import messages
from tui.widgets.condensed_path import CondensedPath
from tui.widgets.directory_input import DirectoryInput


class StoreScreen(Screen):
    BINDING_GROUP_TITLE = "Home"

    BINDINGS = [
        Binding("escape", "app.quit", "Quit"),
    ]

    DEFAULT_CSS = """
    StoreScreen {
        align: center middle;
    }

    #welcome {
        width: 60;
        height: auto;
        padding: 1 2;
        border: round $primary;
    }

    #welcome-title {
        content-align: center middle;
        text-style: bold;
        color: $text-primary;
        padding: 0 0 1 0;
    }

    #welcome-message {
        text-style: not bold;
    }

    #launch-button {
        width: 100%;
        content-align: center middle;
        background: $primary 30%;
        color: $text-primary;
        margin: 1 0 0 0;
        &:hover {
            background: $primary 50%;
        }
    }

    .section-title {
        text-style: bold;
        color: $text-secondary;
        padding: 1 0 0 0;
    }
    """

    def compose(self) -> ComposeResult:
        with containers.Vertical(id="welcome"):
            yield widgets.Static("TUI 2.0", id="welcome-title")
            yield widgets.Static(
                "A terminal user interface for AI-assisted development.",
                id="welcome-message",
            )
            yield widgets.Static("Getting Started", classes="section-title")
            yield widgets.Static(
                Content.assemble(
                    Content.from_markup(
                        "Type [b]!command[/] for shell, or just type naturally to chat."
                    ),
                ),
                id="getting-started",
            )
            yield widgets.Button("Launch TUI2", id="launch-button", variant="primary")

    def on_button_pressed(self, event: widgets.Button.Pressed) -> None:
        if event.button.id == "launch-button":
            self.post_message(messages.LaunchAgent("local", prompt=""))

    def on_mount(self) -> None:
        self.call_after_refresh(self.query_one("#launch-button").focus)
