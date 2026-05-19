from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static
from rich.text import Text


_MODE = {"agent": "AGENT", "plan": "PLAN", "solo": "SOLO"}
_MODE_CLR = {"agent": "primary", "plan": "warning", "solo": "success"}


class HeaderBar(Container):

    DEFAULT_CSS = """
    HeaderBar Static {
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("")

    def sync(self, app) -> None:
        mode  = app.current_mode
        proj  = app.current_project or "no-project"
        model = app.current_model[:24]
        cloud = app.current_cloud.upper()
        t = getattr(app, 'tui_theme', None)

        name  = _MODE.get(mode, mode.upper())
        mode_prop = _MODE_CLR.get(mode, "primary")
        color = getattr(t, mode_prop, "#89b4fa") if t else "#89b4fa"
        dim   = t.variables.get('text_dim', '#565f89') if t else "#565f89"
        proj_c = t.variables.get('text_bright', '#a9b1d6') if t else "#a9b1d6"
        model_c = t.secondary if t else "#7dcfff"
        cloud_c = t.success if t else "#9ece6a"

        self.query_one(Static).update(
            Text.assemble(
                (" ", ""),
                (f" {name} ", f"bold {t.surface if t else '#1a1b26'} on {color}"),
                (" \u2502 ", dim),
                (f" {proj} ", proj_c),
                (" \u2502 ", dim),
                (f" {model} ", model_c),
                (" \u2502 ", dim),
                (f" {cloud} ", cloud_c),
            )
        )
