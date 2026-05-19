from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static
from textual.timer import Timer
from rich.text import Text


_WAVE_PATTERNS = [
    "▁▂▃▄▅▆▇█▇▆▅▄▃▂",
    "▂▃▄▅▆▇█▇▆▅▄▃▂▁",
    "▃▄▅▆▇█▇▆▅▄▃▂▁▁",
    "▄▅▆▇█▇▆▅▄▃▂▁▁▂",
    "▅▆▇█▇▆▅▄▃▂▁▁▂▃",
    "▆▇█▇▆▅▄▃▂▁▁▂▃▄",
    "▇█▇▆▅▄▃▂▁▁▂▃▄▅",
    "█▇▆▅▄▃▂▁▁▂▃▄▅▆",
]
_LOADING_TEXT = " Generating"


class FooterBar(Container):

    DEFAULT_CSS = """
    FooterBar Static {
        width: 100%;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._timer: Timer | None = None
        self._anim_frame: int = 0
        self._loading: bool = False

    def compose(self) -> ComposeResult:
        yield Static("")

    def sync(self, app) -> None:
        self._update_footer()

    def _update_footer(self, animated: bool = False) -> None:
        try:
            static = self.query_one(Static)
        except Exception:
            return
        app = self.app
        t = getattr(app, 'tui_theme', None)

        key_style = f"bold {t.primary if t else '#89b4fa'}"
        dim = t.variables.get('text_dim', '#3b4261') if t else "#3b4261"
        text_style = t.variables.get('text_bright', '#a9b1d6') if t else "#a9b1d6"

        left = Text.assemble(
            (" Ctrl+F ", key_style), ("Focus", text_style),
            (" │ ", dim),
            (" Tab ", key_style), ("Mode", text_style),
            (" │ ", dim),
            (" Ctrl+P ", key_style), ("Menu", text_style),
            (" │ ", dim),
            (" Ctrl+Q ", key_style), ("Quit", text_style),
        )

        if animated and self._loading:
            wave = _WAVE_PATTERNS[self._anim_frame % len(_WAVE_PATTERNS)]
            loading_style = t.warning if t else "#f7c873"
            dim_style = t.variables.get('text_dim', '#565f89') if t else "#565f89"
            status_text = Text.assemble(
                (wave, loading_style),
                (_LOADING_TEXT, dim_style),
            )
            static.update(Text.assemble(
                (left.plain, left.style),
                ("\n", ""),
                ("    ", ""),
                status_text,
            ))
        else:
            ready_mark = t.success if t else "#9ece6a"
            ready_style = t.variables.get('text_dim', '#565f89') if t else "#565f89"
            static.update(Text.assemble(
                left,
                ("       ", ""),
                ("☆", ready_mark),
                (" Ready", ready_style),
            ))

    def start_loading(self) -> None:
        if self._loading:
            return
        self._loading = True
        self._anim_frame = 0
        self._update_footer(animated=True)
        self._timer = self.set_interval(0.1, self._tick)

    def stop_loading(self) -> None:
        self._loading = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._update_footer()

    def _tick(self) -> None:
        self._anim_frame += 1
        self._update_footer(animated=True)
        self._timer = self.set_interval(0.1, self._tick)

    def stop_loading(self) -> None:
        self._loading = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._update_footer()

    def _tick(self) -> None:
        self._anim_frame += 1
        self._update_footer(animated=True)
