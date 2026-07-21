"""Trace Screen — structured view of agenttrace spans (replaces /logs)."""
from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Static

from cdh.trace import get_db_path, get_tracer


_ICONS = {
    "ACP": "⇄",
    "ACP_EVENT": "📡",
    "LIFECYCLE": "⚙",
}


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return ""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.1f}s"


def _truncate(s: str, n: int = 60) -> str:
    return s[:n] + "…" if len(s) > n else s


# ── TraceEntry: a single span widget ───────────────────────────

class TraceEntryClicked(Message):
    def __init__(self, entry: TraceEntry) -> None:
        super().__init__()
        self.entry = entry


class TraceEntry(Static):
    """One trace span row: collapsed = one line, expanded = detail."""

    DEFAULT_CSS = """
    TraceEntry {
        height: auto;
        padding: 0 1;
    }
    TraceEntry > .trace-summary {
        height: 1;
    }
    TraceEntry > .trace-summary:hover {
        background: $panel;
    }
    TraceEntry.-selected > .trace-summary {
        background: $accent;
        color: $text;
        text-style: bold;
    }
    TraceEntry > .trace-body {
        height: auto;
        padding: 0 0 0 4;
    }
    TraceEntry.-collapsed > .trace-body {
        display: none;
    }
    """

    expanded: reactive[bool] = reactive(False)
    selected: reactive[bool] = reactive(False)

    def __init__(self, trace_type: str, func_name: str,
                 duration: float | None = None,
                 tags: dict | None = None,
                 session_id: str | None = None) -> None:
        super().__init__()
        self.trace_type = trace_type
        self.func_name = func_name
        self._duration = duration
        self._tags = tags or {}
        self._session_id = session_id or ""

    def compose(self) -> ComposeResult:
        yield Static(self._summary_text(), classes="trace-summary")
        yield Static(self._body_text(), classes="trace-body", markup=False)

    def on_mount(self) -> None:
        self.set_class(not self.expanded, "-collapsed")

    def _summary_text(self) -> Text:
        marker = "▼" if self.expanded else "▶"
        icon = _ICONS.get(self.trace_type, "•")
        t = Text()
        t.append(f" {marker} ", style="dim")
        t.append(f"{icon} ", style="bold")
        t.append(f"{self.trace_type}  ", style="dim")
        t.append(self.func_name, style="bold")
        if self._duration is not None:
            dur = _format_duration(self._duration)
            t.append(f"  {dur}", style="italic cyan")
        return t

    def _body_text(self) -> Text:
        lines = [f"Type:     {self.trace_type}",
                 f"Function: {self.func_name}"]
        if self._session_id:
            lines.append(f"Session:  {self._session_id}")
        if self._duration is not None:
            lines.append(f"Duration: {_format_duration(self._duration)}")
        if self._tags:
            lines.append("Tags:")
            for k, v in self._tags.items():
                lines.append(f"  {k} = {v}")
        return Text("\n".join(lines))

    def watch_expanded(self, expanded: bool) -> None:
        self.set_class(not expanded, "-collapsed")
        try:
            self.query_one(".trace-summary", Static).update(self._summary_text())
        except Exception:
            pass

    def on_click(self) -> None:
        self.expanded = not self.expanded
        self.post_message(TraceEntryClicked(self))

    def watch_selected(self, selected: bool) -> None:
        self.set_class(selected, "-selected")
        if selected:
            self.scroll_visible()


# ── TraceScreen ─────────────────────────────────────────────────

class TraceScreen(ModalScreen[None]):
    """Trace viewer — shows structured agenttrace spans (replaces LogScreen)."""

    BINDINGS = [
        Binding("escape,f4", "dismiss", "Close"),
        Binding("down,j", "next_entry", "Next", priority=True),
        Binding("up,k", "prev_entry", "Prev", priority=True),
        Binding("enter,space,l", "toggle_current", "Toggle"),
        Binding("o", "open_current", "Open"),
        Binding("O", "expand_all", "Open all"),
        Binding("C", "collapse_all", "Close all"),
        Binding("r", "refresh", "Refresh"),
    ]

    DEFAULT_CSS = """
    TraceScreen {
        align: center middle;
    }

    TraceScreen > Vertical {
        width: 95%;
        height: 90%;
        border: thick $primary;
        background: $surface;
    }

    TraceScreen #trace-header {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }

    TraceScreen #trace-list {
        height: 1fr;
        background: $surface;
    }
    """

    def __init__(self, session_id: str | None = None) -> None:
        super().__init__()
        self._session_id = session_id
        self._entries: list[TraceEntry] = []
        self._current_index: int = -1

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(id="trace-header")
            yield VerticalScroll(id="trace-list")

    async def on_mount(self) -> None:
        self.query_one("#trace-list", VerticalScroll).can_focus = False
        await self._load_traces()

    async def _load_traces(self) -> None:
        scroller = self.query_one("#trace-list", VerticalScroll)
        await scroller.remove_children()
        self._entries = []

        db_path = get_db_path()
        if not db_path.exists():
            msg = "[dim]No traces yet. Start an agent session to collect traces.[/dim]"
            await scroller.mount(Static(msg))
            self._refresh_header()
            return

        try:
            tracer = get_tracer()
            traces = tracer.get_traces(limit=500, session_id=self._session_id)
        except Exception:
            traces = []

        if not traces:
            msg = f"[dim]No traces found for session: {self._session_id or '(all)'}[/dim]"
            await scroller.mount(Static(msg))
            self._refresh_header()
            return

        for t in traces:
            trace_type = t.get("type", "ACP")
            func_name = t.get("function", "")
            duration = t.get("duration")
            tags_data = t.get("tags", {})
            sid = t.get("session_id", "") or self._session_id or ""
            entry = TraceEntry(
                trace_type=trace_type,
                func_name=func_name,
                duration=duration,
                tags=tags_data if isinstance(tags_data, dict) else {},
                session_id=sid,
            )
            self._entries.append(entry)

        await scroller.mount(*self._entries)
        self._current_index = 0 if self._entries else -1
        self._apply_selection()
        self._refresh_header()

    def _refresh_header(self) -> None:
        total = len(self._entries)
        sid = self._session_id or "(all sessions)"
        try:
            self.query_one("#trace-header", Static).update(
                f"🔍 Trace — {total} spans  |  Session: {sid}  │  "
                f"↑↓: nav · ⏎: toggle · r: refresh · F4/Esc close"
            )
        except Exception:
            pass

    def _apply_selection(self) -> None:
        scroller = self.query_one("#trace-list", VerticalScroll)
        for i, child in enumerate(scroller.children):
            if isinstance(child, TraceEntry):
                child.selected = (i == self._current_index)

    @on(TraceEntryClicked)
    def on_trace_entry_clicked(self, event: TraceEntryClicked) -> None:
        scroller = self.query_one("#trace-list", VerticalScroll)
        for i, child in enumerate(scroller.children):
            if child is event.entry:
                self._current_index = i
                self._apply_selection()
                return

    def _current_entry(self) -> TraceEntry | None:
        scroller = self.query_one("#trace-list", VerticalScroll)
        for i, child in enumerate(scroller.children):
            if isinstance(child, TraceEntry) and i == self._current_index:
                return child
        return None

    # ── Actions ─────────────────────────────────────────────────

    def action_next_entry(self) -> None:
        count = len(self._entries)
        if count == 0:
            return
        if self._current_index < 0:
            self._current_index = 0
        else:
            self._current_index = min(count - 1, self._current_index + 1)
        self._apply_selection()

    def action_prev_entry(self) -> None:
        count = len(self._entries)
        if count == 0:
            return
        if self._current_index < 0:
            self._current_index = count - 1
        else:
            self._current_index = max(0, self._current_index - 1)
        self._apply_selection()

    def action_toggle_current(self) -> None:
        entry = self._current_entry()
        if entry is not None:
            entry.expanded = not entry.expanded

    def action_open_current(self) -> None:
        entry = self._current_entry()
        if entry is not None:
            entry.expanded = True

    def action_expand_all(self) -> None:
        for child in self._get_entries():
            child.expanded = True

    def action_collapse_all(self) -> None:
        for child in self._get_entries():
            child.expanded = False

    async def action_refresh(self) -> None:
        await self._load_traces()
        self.app.notify("Trace refreshed", title="Trace")

    def _get_entries(self) -> list[TraceEntry]:
        scroller = self.query_one("#trace-list", VerticalScroll)
        return [c for c in scroller.children if isinstance(c, TraceEntry)]
