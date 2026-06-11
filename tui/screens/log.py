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
_PAGE_SIZE = 50


def _find_log_file() -> Path | None:
    """Return the most recent message log file, or None if empty."""
    log_dir = get_log() / "messages"
    if not log_dir.exists():
        return None
    candidates = [
        p for p in log_dir.iterdir()
        if p.is_file() and p.suffix == ".jsonl" and not p.name.startswith(".")
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


def _summarize_message_log(record: dict) -> str:
    """Extract a one-line summary of a MessageLog event record."""
    event = record.get("event", "")
    turn = record.get("turn", "")
    turn_str = f" [dim](turn {turn})[/dim]" if turn != "" else ""
    if event == "user_input":
        text = record.get("text", "")
        return f"user_input  [dim]\"{text[:60]}{'…' if len(text) > 60 else ''}\"[/dim]{turn_str}"
    if event == "agent_output":
        text = record.get("text", "")
        return f"agent_output  [dim]\"{text[:60]}{'…' if len(text) > 60 else ''}\"[/dim]{turn_str}"
    if event == "agent_thought":
        return f"agent_thought{turn_str}"
    if event == "tool_call":
        name = record.get("tool_name", "")
        return f"tool_call  [bold]{name}[/bold]{turn_str}"
    if event == "tool_result":
        name = record.get("tool_name", "")
        status = record.get("status", "success")
        return f"tool_result  [bold]{name}[/bold] → {status}{turn_str}"
    if event == "turn_end":
        reason = record.get("stop_reason", "")
        return f"turn_end  stop={reason}{turn_str}"
    if event == "error":
        msg = record.get("message", "")
        return f"error: {msg[:60]}{turn_str}"
    return str(record)[:80]


def _summarize(tag: str, raw: str) -> str:
    """Extract a one-line summary of a JSON-RPC or MessageLog message."""
    try:
        obj = json.loads(raw)
    except Exception:
        return raw[:80]
    if not isinstance(obj, dict):
        return str(obj)[:80]
    # MessageLog event record (event-driven format)
    if "event" in obj:
        return _summarize_message_log(obj)
    # Legacy JSON-RPC wire format
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
    """Page-based log viewer (F4). Shows all log entries with 50 per page."""

    BINDINGS = [
        Binding("escape,f4", "dismiss", "Close"),
        # Entry navigation within current page
        Binding("down,j", "next_entry", "Next entry"),
        Binding("up,k", "prev_entry", "Prev entry"),
        # Page navigation (log is newest-first, so PageDown = older entries)
        Binding("pagedown,n", "prev_page", "Prev page", show=False),
        Binding("pageup,p", "next_page", "Next page", show=False),
        Binding("home,g", "first_page", "First page", show=False),
        Binding("end,G", "last_page", "Last page", show=False),
        # Toggle current
        Binding("enter,space,l", "toggle_current", "Toggle", show=False),
        Binding("o", "open_current", "Open", show=False),
        Binding("O", "expand_all", "Open all"),
        Binding("C", "collapse_all", "Close all"),
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
    }
    """

    def __init__(self, log_path: Path | None = None) -> None:
        super().__init__()
        self._log_path = log_path
        self._file_pos = 0
        self._poll_timer: object = None
        self._entries: list[tuple[str, str]] = []
        self._current_page: int = 1
        self._current_index: int = -1
        self._file_was_present: bool = False

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
        if not self._log_path.exists():
            self._append_system(
                f"⌛ Waiting for log file to be created…\n   {self._log_path}"
            )
            self._poll_timer = self.set_interval(0.2, self._poll_new_lines)
            return
        self._begin_tailing()

    # ── Page helpers ───────────────────────────────────────────────

    def _total_pages(self) -> int:
        return max(1, (len(self._entries) + _PAGE_SIZE - 1) // _PAGE_SIZE)

    def _page_range(self) -> tuple[int, int]:
        start = (self._current_page - 1) * _PAGE_SIZE
        end = min(start + _PAGE_SIZE, len(self._entries))
        return start, end

    def _render_page(self) -> None:
        scroller = self.query_one("#log-list", VerticalScroll)
        scroller.remove_children()
        start, end = self._page_range()
        page_entries = self._entries[start:end]
        for tag, raw in page_entries:
            scroller.mount(LogEntry(tag, raw))
        self._current_index = 0 if page_entries else -1
        self._apply_selection()
        self._refresh_header()

    def _navigate_to_page(self, page: int) -> None:
        total = self._total_pages()
        self._current_page = max(1, min(page, total))
        self._render_page()

    # ── File loading ───────────────────────────────────────────────

    def _begin_tailing(self) -> None:
        """Read entire log file and start polling."""
        assert self._log_path is not None
        try:
            with self._log_path.open("r", encoding="utf-8", errors="replace") as f:
                data = f.read()
            self._file_pos = self._log_path.stat().st_size
        except OSError as e:
            self._append_system(f"Failed to open log: {e}")
            return
        self._file_was_present = True
        self._entries = []
        self._ingest(data)
        self._current_page = self._total_pages()
        self._render_page()
        if self._poll_timer is None:
            self._poll_timer = self.set_interval(0.2, self._poll_new_lines)

    def on_unmount(self) -> None:
        if self._poll_timer is not None:
            stop = getattr(self._poll_timer, "stop", None)
            if callable(stop):
                stop()
            self._poll_timer = None

    def _header_text(self) -> str:
        total = len(self._entries)
        pages = self._total_pages()
        start, end = self._page_range()
        display_start = start + 1 if total > 0 else 0
        return (
            f"📋 Session log — Page {self._current_page}/{pages} · "
            f"Showing {display_start}-{end} of {total} entries  │  "
            f"↑↓: entry · n/p: page · g/G: first/last · ⏎ toggle · F4/Esc close"
            if self._log_path
            else "📋 Session log — (no log file found)"
        )

    def _refresh_header(self) -> None:
        try:
            self.query_one("#log-header", Static).update(self._header_text())
        except Exception:
            pass

    def _apply_selection(self) -> None:
        scroller = self.query_one("#log-list", VerticalScroll)
        for i, child in enumerate(scroller.children):
            if isinstance(child, LogEntry):
                child.selected = (i == self._current_index)

    @on(LogEntryClicked)
    def on_log_entry_clicked(self, event: LogEntryClicked) -> None:
        scroller = self.query_one("#log-list", VerticalScroll)
        for i, child in enumerate(scroller.children):
            if child is event.entry:
                self._current_index = i
                self._apply_selection()
                return

    def _append_system(self, msg: str) -> None:
        scroller = self.query_one("#log-list", VerticalScroll)
        scroller.mount(Static(f"[dim]{msg}[/dim]"))

    # ── Polling for new lines ──────────────────────────────────────

    def _poll_new_lines(self) -> None:
        if self._log_path is None:
            return
        if not self._log_path.exists():
            return
        if not self._file_was_present:
            self._append_system(f"── log file appeared: {self._log_path} ──")
            self._begin_tailing()
            return
        try:
            size = self._log_path.stat().st_size
            if size < self._file_pos:
                self._file_pos = 0
            if size == self._file_pos:
                return
            with self._log_path.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(self._file_pos)
                new_text = f.read()
            self._file_pos = size
            if new_text:
                self._ingest(new_text)
        except OSError:
            pass

    def _ingest(self, chunk: str) -> None:
        was_on_last_page = (
            len(self._entries) == 0
            or self._current_page == self._total_pages()
        )
        for line in chunk.splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if isinstance(record, dict) and "event" in record:
                    event = record.get("event", "")
                    if event in ("user_input",):
                        tag = "client"
                    elif event in ("agent_output", "agent_thought", "tool_call", "tool_result", "turn_end"):
                        tag = "agent"
                    else:
                        tag = "error"
                    self._entries.append((tag, line))
                    continue
            except (json.JSONDecodeError, ValueError):
                pass
            m = _TAG_RE.match(line)
            if m:
                self._entries.append((m.group(1), m.group(2)))
            else:
                self._entries.append(("error", line))
        if was_on_last_page:
            self._current_page = self._total_pages()
            self._render_page()
        else:
            self._refresh_header()

    # ── Actions ────────────────────────────────────────────────────

    def _current_entry(self) -> LogEntry | None:
        scroller = self.query_one("#log-list", VerticalScroll)
        for i, child in enumerate(scroller.children):
            if isinstance(child, LogEntry) and i == self._current_index:
                return child
        return None

    def action_next_page(self) -> None:
        if self._current_page < self._total_pages():
            self._navigate_to_page(self._current_page + 1)

    def action_prev_page(self) -> None:
        if self._current_page > 1:
            self._navigate_to_page(self._current_page - 1)

    def action_first_page(self) -> None:
        self._navigate_to_page(1)

    def action_last_page(self) -> None:
        self._navigate_to_page(self._total_pages())

    def action_next_entry(self) -> None:
        scroller = self.query_one("#log-list", VerticalScroll)
        count = sum(1 for c in scroller.children if isinstance(c, LogEntry))
        if count == 0:
            return
        if self._current_index < 0:
            self._current_index = 0
        else:
            self._current_index = min(count - 1, self._current_index + 1)
        self._apply_selection()

    def action_prev_entry(self) -> None:
        scroller = self.query_one("#log-list", VerticalScroll)
        count = sum(1 for c in scroller.children if isinstance(c, LogEntry))
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
        scroller = self.query_one("#log-list", VerticalScroll)
        for child in scroller.children:
            if isinstance(child, LogEntry):
                child.expanded = True

    def action_collapse_all(self) -> None:
        scroller = self.query_one("#log-list", VerticalScroll)
        for child in scroller.children:
            if isinstance(child, LogEntry):
                child.expanded = False

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
