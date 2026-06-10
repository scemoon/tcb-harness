from __future__ import annotations

from pathlib import Path
import subprocess

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static
from textual import containers


class ModifiedFiles(containers.Vertical):
    DEFAULT_CSS = """
    ModifiedFiles {
        height: auto;
        max-height: 15;
        overflow-y: auto;

        Static {
            padding: 0 1;
        }

        .file-added {
            color: $text-success;
        }

        .file-modified {
            color: $text-warning;
        }

        .file-deleted {
            color: $text-error;
        }

        .file-renamed {
            color: $text-secondary;
        }

        .no-changes {
            color: $text-secondary;
            text-style: italic;
        }
    }
    """

    path: reactive[Path | None] = reactive(None)
    files: reactive[list[str]] = reactive([], recompose=True)

    def __init__(
        self,
        path: Path | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.set_reactive(ModifiedFiles.path, path)

    def watch_path(self, path: Path | None) -> None:
        """Run git status when path changes."""
        if path is None:
            self.files = []
            return
        try:
            result = subprocess.run(
                ["git", "-C", str(path), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                self.files = [l for l in result.stdout.strip().split("\n") if l.strip()]
            else:
                self.files = []
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self.files = []

    def refresh_files(self) -> None:
        """Re-run git status manually (e.g. after file system changes)."""
        self.watch_path(self.path)

    def compose(self) -> ComposeResult:
        if not self.files:
            yield Static("No modified files", classes="no-changes")
            return
        for line in self.files:
            status = line[:2]
            filepath = line[3:]
            cls = self._class_for_status(status)
            yield Static(f" {filepath}", classes=cls)

    @staticmethod
    def _class_for_status(status: str) -> str:
        if "?" in status:
            return "file-added"
        if "D" in status:
            return "file-deleted"
        if "A" in status or "C" in status:
            return "file-added"
        if "R" in status:
            return "file-renamed"
        if "M" in status:
            return "file-modified"
        return "file-modified"
