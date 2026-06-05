"""Log Screen — collapsible per-message view of the JSON-RPC log (F4)."""
from __future__ import annotations

import json
import re
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

from tui.paths import get_log


_TAG_RE = re.compile(r"^\[(client|agent|error)\]\s*(.*)$", re.DOTALL)
_PREVIEW_BYTES = 4000
_MAX_ENTRIES = 2000


def _find_log_file() -> Path | None:
    """Return the most recent agent log file, or None if empty."""
    log_dir = get_log()
    if not log_dir.exists():
        return None
    candidates = [
        p for p in log_dir.iterdir()
        if p.is_file() and p.suffix == ".txt" and not p.name.startswith(".")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


# ── JSON syntax highlighting (ANSI) ───────────────────────────────

_ANSI_HIGHLIGHT = re.compile(
    r'("(?:[^"\\]|\\.)*")(\s*:)?'
    r'|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'
    r'|\b(true|false|null)\b',
)


def _ansi_repl(m: re.Match) -> str:
    s, colon, num, lit = m.group(1), m.group(2), m.group(3), m.group(4)
    if s is not None:
        if colon:
            return f"\x1b[36m{s}\x1b[0m{colon}"
        return f"\x1b[33m{s}\x1b[0m"
    if num is not None:
        return f"\x1b[35m{num}\x1b[0m"
    if lit is not None:
        return f"\x1b[32m{lit}\x1b[0m"
    return m.group(0)


def _highlight_json(raw: str) -> str:
    """Return a pretty-printed JSON string with ANSI color escapes."""
    try:
        obj = json.loads(raw)
        formatted = json.dumps(obj, indent=2, ensure_ascii=False)
    except Exception:
        return raw
    return _ANSI_HIGHLIGHT.sub(_ansi_repl, formatted)


def _summarize(tag: str, raw: str) -> str:
    """Extract a one-line summary of a JSON-RPC message."""
    try:
        obj = json.loads(raw)
    except Exception:
        return raw[:80]
    if not isinstance(obj, dict):
        return str(obj)[:80]
    if tag == "agent" and "method" in obj:
        method = obj.get("method", "")
        params = obj.get("params", {})
        if isinstance(params, dict):
            update = params.get("update", {})
            if isinstance(update, dict):
                kind = update.get("sessionUpdate", "")
                if kind:
                    return f"{method} → {kind}"
            sid = params.get("sessionId", "")
            if method == "session/update" and sid:
                return f"{method}  [dim]({sid[:8]}…)[/dim]"
        return method
    if tag == "client":
        method = obj.get("method", "")
        params = obj.get("params", {})
        if isinstance(params, dict):
            if method == "session/prompt":
                prompt = params.get("prompt", [])
                if isinstance(prompt, list) and prompt:
                    first = prompt[0]
                    if isinstance(first, dict):
                        text = first.get("text", "")
                        return f"{method}  [dim]\"{text[:40]}{'…' if len(text) > 40 else ''}\"[/dim]"
        return method
    if "error" in obj:
        err = obj.get("error", {})
        return f"error: {err.get('message', '?')}" if isinstance(err, dict) else "error"
    return obj.get("method", raw[:60])


# ── LogEntry: a single collapsible message ────────────────────────

class LogEntryClicked(Message):
    """Posted when a LogEntry is clicked. Carries the entry reference."""

    def __init__(self, entry: "LogEntry") -> None:
        super().__init__()
        self.entry = entry


class LogEntry(Static):
    """One log line: collapsed = summary, expanded = full pretty JSON."""

    DEFAULT_CSS = """
    LogEntry {
        height: auto;
        padding: 0 1;
    }
    LogEntry > .log-summary {
        height: 1;
    }
    LogEntry > .log-summary:hover {
        background: $panel;
    }
    LogEntry.-selected > .log-summary {
        background: $accent;
        color: $text;
        text-style: bold;
    }
    LogEntry > .log-body {
        height: auto;
        padding: 0 0 0 4;
    }
    LogEntry.-collapsed > .log-body {
        display: none;
    }
    """

    expanded: reactive[bool] = reactive(False)
    selected: reactive[bool] = reactive(False)

    def __init__(self, tag: str, raw: str) -> None:
        super().__init__()
        self.tag = tag
        self.raw = raw

    def compose(self) -> ComposeResult:
        yield Static(self._summary_text(), classes="log-summary")
        yield Static(self._body_text(), classes="log-body", markup=False)

    def on_mount(self) -> None:
        self.set_class(not self.expanded, "-collapsed")

    def _summary_text(self) -> Text:
        marker = "▼" if self.expanded else "▶"
        if self.tag == "client":
            style = "bold cyan"
            tag_label = "[→]"
        elif self.tag == "agent":
            style = "bold green"
            tag_label = "[←]"
        else:
            style = "bold red"
            tag_label = "[!]"
        t = Text()
        t.append(f" {marker} ", style="dim")
        t.append(tag_label, style=style)
        t.append(" ")
        # render the summary as markup
        from rich.markup import render as render_markup
        try:
            rendered = render_markup(self._summary_markup())
            t.append_text(rendered)
        except Exception:
            t.append(self._summary_markup())
        return t

    def _summary_markup(self) -> str:
        return _summarize(self.tag, self.raw)

    def _body_text(self) -> Text:
        return Text.from_ansi(_highlight_json(self.raw))

    def watch_expanded(self, expanded: bool) -> None:
        self.set_class(not expanded, "-collapsed")
        # Refresh the summary to update the ▼ / ▶ marker
        try:
            self.query_one(".log-summary", Static).update(self._summary_text())
        except Exception:
            pass

    def on_click(self) -> None:
        self.expanded = not self.expanded
        # Notify the screen to update its current_index
        self.post_message(LogEntryClicked(self))

    def watch_selected(self, selected: bool) -> None:
        self.set_class(selected, "-selected")
        if selected:
            self.scroll_visible()


# ── LogScreen ──────────────────────────────────────────────────────

class LogScreen(ModalScreen[None]):
    """Real-time tail of the agent's JSON-RPC log; per-message collapsible."""

    BINDINGS = [
        Binding("escape,f4", "dismiss", "Close"),
        # Navigation
        Binding("down,j", "next_entry", "Next", show=False),
        Binding("up,k", "prev_entry", "Prev", show=False),
        Binding("home,g", "first_entry", "First", show=False),
        Binding("end,G", "last_entry", "Last", show=False),
        # Toggle current
        Binding("enter,space,l", "toggle_current", "Toggle", show=False),
        Binding("o", "open_current", "Open", show=False),
        Binding("O", "expand_all", "Open all"),
        Binding("C", "collapse_all", "Close all"),
        # Order
        Binding("r", "toggle_reversed", "Reverse"),
        # Misc
        Binding("c", "copy_all", "Copy"),
    ]

    DEFAULT_CSS = """
    LogScreen {
        align: center middle;
    }

    LogScreen > Vertical {
        width: 95%;
        height: 90%;
        border: thick $primary;
        background: $surface;
    }

    LogScreen #log-header {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }

    LogScreen VerticalScroll {
        height: 1fr;
        background: $surface;
        scrollbar-gutter: stable;
    }
    """

    def __init__(self, log_path: Path | None = None) -> None:
        super().__init__()
        self._log_path = log_path
        self._file_pos = 0
        self._poll_timer: object = None
        self._entry_count = 0
        self._entries: list[LogEntry] = []
        self._current_index: int = -1
        self._reversed: bool = False

    def compose(self) -> ComposeResult:
        path = self._log_path or _find_log_file()
        self._log_path = path
        with Vertical():
            yield Static(self._header_text(), id="log-header")
            yield VerticalScroll(id="log-list")

    def on_mount(self) -> None:
        if self._log_path is None:
            self._append_system("No log file yet. Start an agent to begin logging.")
            return
        try:
            size = self._log_path.stat().st_size
            start = max(0, size - _PREVIEW_BYTES)
            with self._log_path.open("rb") as f:
                if start > 0:
                    f.seek(start)
                    f.readline()
                data = f.read().decode("utf-8", errors="replace")
            self._file_pos = self._log_path.stat().st_size
            self._ingest(data, scroll=False)
        except OSError as e:
            self._append_system(f"Failed to open log: {e}")
            return
        self._poll_timer = self.set_interval(0.2, self._poll_new_lines)

    def on_unmount(self) -> None:
        if self._poll_timer is not None:
            stop = getattr(self._poll_timer, "stop", None)
            if callable(stop):
                stop()
            self._poll_timer = None

    def _header_text(self) -> str:
        path = self._log_path
        order = "⏷ reverse" if self._reversed else "⏵ forward"
        return (
            f"📡 Agent log — {path}  [dim]│  {order}  │  "
            f"{self._entry_count} msgs  │  j/k nav · ⏎ toggle · r reverse · "
            f"O open all · C close all · F4/Esc close[/dim]"
            if path
            else "📡 Agent log — (no log file found)"
        )

    def _refresh_header(self) -> None:
        try:
            self.query_one("#log-header", Static).update(self._header_text())
        except Exception:
            pass

    def _scroll_to_end(self) -> None:
        scroller = self.query_one("#log-list", VerticalScroll)
        # In reverse mode, the "end" visually is the top of the scroller
        if self._reversed:
            scroller.scroll_home(animate=False)
        else:
            scroller.scroll_end(animate=False)

    def _scroll_to_index(self, idx: int) -> None:
        if not (0 <= idx < len(self._entries)):
            return
        try:
            self.query_one("#log-list", VerticalScroll).scroll_to_widget(
                self._entries[idx], animate=False
            )
        except Exception:
            pass

    def _trim_if_needed(self) -> None:
        if self._entry_count <= _MAX_ENTRIES:
            return
        scroller = self.query_one("#log-list", VerticalScroll)
        to_remove = max(1, _MAX_ENTRIES // 10)
        # Remove from the "oldest" side: bottom in forward, top in reverse
        if self._reversed:
            victims = list(scroller.children)[-to_remove:]
        else:
            victims = list(scroller.children)[:to_remove]
        for child in victims:
            child.remove()
            if child in self._entries:
                self._entries.remove(child)
        self._entry_count -= to_remove
        if self._current_index >= len(self._entries):
            self._current_index = len(self._entries) - 1
            self._apply_selection()

    def _append_entry(self, tag: str, raw: str, *, scroll: bool = True) -> None:
        self._trim_if_needed()
        scroller = self.query_one("#log-list", VerticalScroll)
        entry = LogEntry(tag, raw)
        # Was the user "following the tail" (i.e., on the newest entry)?
        following_tail = (
            self._current_index < 0
            or (not self._reversed and self._current_index == len(self._entries) - 1)
            or (self._reversed and self._current_index == 0)
        )
        if self._reversed:
            scroller.mount(entry, before=0)
            self._entries.insert(0, entry)
            if self._current_index >= 0:
                self._current_index += 1
        else:
            scroller.mount(entry)
            self._entries.append(entry)
        self._entry_count += 1
        if following_tail and self._entries:
            self._current_index = 0 if self._reversed else len(self._entries) - 1
            self._apply_selection()
        self._refresh_header()
        if scroll:
            self.call_after_refresh(self._scroll_to_end)

    def _apply_selection(self) -> None:
        for i, entry in enumerate(self._entries):
            entry.selected = (i == self._current_index)
        if 0 <= self._current_index < len(self._entries):
            self._scroll_to_index(self._current_index)

    @on(LogEntryClicked)
    def on_log_entry_clicked(self, event: LogEntryClicked) -> None:
        if event.entry in self._entries:
            self._current_index = self._entries.index(event.entry)
            self._apply_selection()

    def _append_system(self, msg: str) -> None:
        scroller = self.query_one("#log-list", VerticalScroll)
        scroller.mount(Static(f"[dim]{msg}[/dim]"))

    def _poll_new_lines(self) -> None:
        if self._log_path is None or not self._log_path.exists():
            return
        try:
            size = self._log_path.stat().st_size
            if size < self._file_pos:
                self._file_pos = 0
                self._append_system("── log rotated ──")
            if size == self._file_pos:
                return
            with self._log_path.open("rb") as f:
                f.seek(self._file_pos)
                data = f.read().decode("utf-8", errors="replace")
            self._file_pos = size
            self._ingest(data, scroll=True)
        except OSError:
            pass

    def _ingest(self, chunk: str, *, scroll: bool) -> None:
        for line in chunk.splitlines():
            if not line.strip():
                continue
            m = _TAG_RE.match(line)
            if m:
                self._append_entry(m.group(1), m.group(2), scroll=scroll)
            else:
                self._append_entry("error", line, scroll=scroll)

    # ── Actions ────────────────────────────────────────────────────

    def _current_entry(self) -> LogEntry | None:
        if 0 <= self._current_index < len(self._entries):
            return self._entries[self._current_index]
        return None

    def action_next_entry(self) -> None:
        if not self._entries:
            return
        if self._current_index < 0:
            # No selection yet: in forward mode start from end (newest),
            # in reverse mode start from 0 (newest).
            self._current_index = 0 if self._reversed else len(self._entries) - 1
        else:
            step = 1
            self._current_index = min(len(self._entries) - 1, self._current_index + step)
        self._apply_selection()

    def action_prev_entry(self) -> None:
        if not self._entries:
            return
        if self._current_index < 0:
            self._current_index = 0 if self._reversed else len(self._entries) - 1
        else:
            self._current_index = max(0, self._current_index - 1)
        self._apply_selection()

    def action_first_entry(self) -> None:
        if not self._entries:
            return
        # "First" in display order = index 0 when forward, last when reversed
        self._current_index = len(self._entries) - 1 if self._reversed else 0
        self._apply_selection()

    def action_last_entry(self) -> None:
        if not self._entries:
            return
        # "Last" in display order = last when forward, 0 when reversed
        self._current_index = 0 if self._reversed else len(self._entries) - 1
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
        for entry in self._entries:
            entry.expanded = True

    def action_collapse_all(self) -> None:
        for entry in self._entries:
            entry.expanded = False

    async def action_toggle_reversed(self) -> None:
        new_reversed = not self._reversed
        self._reversed = new_reversed
        self._refresh_header()
        # The internal _entries list mirrors the display order, so flip it
        # whenever the order toggles. (Forward = oldest-first.)
        self._entries = list(reversed(self._entries)) if new_reversed else list(reversed(self._entries))
        scroller = self.query_one("#log-list", VerticalScroll)
        for entry in list(self._entries):
            await entry.remove()
        for entry in self._entries:
            await scroller.mount(entry)
        if self._entries:
            self._current_index = 0 if new_reversed else len(self._entries) - 1
            self._apply_selection()
            self.call_after_refresh(self._scroll_to_end)

    def action_copy_all(self) -> None:
        try:
            import pyperclip
        except ImportError:
            self.app.notify("pyperclip not installed", title="Log", severity="warning")
            return
        if self._log_path is None:
            return
        try:
            text = self._log_path.read_text(errors="replace")
            pyperclip.copy(text)
            self.app.notify("Log copied to clipboard", title="Log")
        except Exception as e:
            self.app.notify(f"Copy failed: {e}", title="Log", severity="error")
