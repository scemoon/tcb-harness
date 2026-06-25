from __future__ import annotations

from pathlib import Path
import subprocess

from textual import work
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.timer import Timer
from textual.widgets import Static
from textual import containers
from rich.text import Text
from rich.style import Style


GIT_STATUS_TIMEOUT = 5.0
GIT_STATUS_DEBOUNCE = 0.2

NOT_A_REPO_TEXT = "Not a git repository"
NO_CHANGES_TEXT = "No modified files"
LOADING_TEXT = "Checking…"

IGNORED_DIRS = frozenset(
    {
        ".venv",
        ".git",
        ".pytest_cache",
        "__pycache__",
        ".mypy_cache",
        "node_modules",
        ".uv-cache",
        "dist",
        "build",
        ".idea",
    }
)


def _style_for_status(status: str) -> Style:
    if "?" in status:
        return Style(color="green")
    if "D" in status:
        return Style(color="red")
    if "A" in status or "C" in status:
        return Style(color="green")
    if "R" in status:
        return Style(color="#888888")
    return Style(color="yellow")


class ModifiedFiles(containers.Vertical):
    DEFAULT_CSS = """
    ModifiedFiles {
        height: auto;
        overflow-y: auto;
        padding: 0 0 0 0;

        #mf-files {
            height: auto;
            padding: 0 1;
        }
    }
    """

    path: reactive[Path | None] = reactive(None)
    files: reactive[list[str]] = reactive(list, recompose=False)

    def __init__(
        self,
        path: Path | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._debounce_timer: Timer | None = None
        self._status_kind: str = "no-changes"
        self._status_text: str = NO_CHANGES_TEXT
        self._initial_path: Path | None = path

    def on_mount(self) -> None:
        initial = self._initial_path
        self._initial_path = None
        if initial is not None:
            self.path = initial

    def watch_path(self, path: Path | None) -> None:
        self._cancel_debounce()
        if path is None:
            self._show_status("no-changes", NO_CHANGES_TEXT)
            return
        self._show_status("-loading", LOADING_TEXT)
        self._schedule_run(path)

    def refresh_files(self) -> None:
        if self.path is not None:
            self._cancel_debounce()
            self._show_status("-loading", LOADING_TEXT)
            self._run_git_status(self.path)

    def _schedule_run(self, path: Path) -> None:
        timer = self.set_timer(
            GIT_STATUS_DEBOUNCE,
            lambda p=path: self._run_git_status(p),
        )
        self._debounce_timer = timer

    def _cancel_debounce(self) -> None:
        timer = self._debounce_timer
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
            self._debounce_timer = None

    @work(exclusive=True, group="modified-files-git-status", thread=True)
    def _run_git_status(self, path: Path) -> None:
        app = self.app
        outcome = self._do_git_status(path)
        if outcome is None:
            return
        kind, text, lines = outcome
        if lines is None:
            app.call_from_thread(self._show_status, kind, text)
        else:
            app.call_from_thread(self._render_lines, lines)

    def _do_git_status(
        self, path: Path
    ) -> tuple[str, str, list[str] | None] | None:
        if any(part in IGNORED_DIRS for part in path.parts):
            return ("not-a-repo", NOT_A_REPO_TEXT, None)
        try:
            result = subprocess.run(
                ["git", "-C", str(path), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=GIT_STATUS_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return ("no-changes", NO_CHANGES_TEXT, None)
        except FileNotFoundError:
            return ("not-a-repo", NOT_A_REPO_TEXT, None)
        except Exception:
            return ("no-changes", NO_CHANGES_TEXT, None)
        if result.returncode != 0:
            return ("not-a-repo", NOT_A_REPO_TEXT, None)
        lines = [
            line for line in result.stdout.splitlines() if line.strip()
        ]
        if not lines:
            return ("no-changes", NO_CHANGES_TEXT, [])
        return ("file-modified", "", lines)

    def _render_lines(self, lines: list[str]) -> None:
        self.files = list(lines)
        if not lines:
            self._show_status("no-changes", NO_CHANGES_TEXT)
            return
        self._show_status("file-modified", "")
        text = Text()
        for i, line in enumerate(lines):
            if i > 0:
                text.append("\n")
            filepath = line[3:]
            style = _style_for_status(line[:2])
            text.append(f" {filepath}", style=style)
        files_widget = self.query_one("#mf-files", Static)
        files_widget.update(text)

    def _show_status(self, kind: str, text: str) -> None:
        self._status_kind = kind
        self._status_text = text
        status = self.query_one("#mf-status", Static)
        status.update(text)

    def compose(self) -> ComposeResult:
        yield Static(self._status_text, id="mf-status")
        yield Static("", id="mf-files")
