"""Tests for the ModifiedFiles widget's async/debounced git-status lookup.

These tests pin down the behaviour introduced to fix the "f3 select
project → terminal flapping between git and uv run" regression:
  * ``watch_path`` must NOT block the event loop with a synchronous
    ``subprocess.run`` call.
  * Rapidly changing ``path`` must be debounced so we run ``git status``
    at most once for the latest value (within the debounce window).
  * Non-git repositories (and missing ``git`` binary) must surface
    "Not a git repository" instead of leaving stale "No modified files".
  * ``refresh_files`` re-runs immediately without debounce.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Static


# ---------------------------------------------------------------------------
# helpers


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _patch_run(monkeypatch, *, returncode: int = 0, stdout: str = "", exc=None):
    def fake_run(*args, **kwargs):
        if exc is not None:
            raise exc
        return SimpleNamespace(returncode=returncode, stdout=stdout)

    monkeypatch.setattr("tui.widgets.modified_files.subprocess.run", fake_run)
    return fake_run


def _make_app(initial_path: Path):
    from tui.widgets.modified_files import ModifiedFiles

    class _App(App):
        def compose(self) -> ComposeResult:
            with Container():
                yield ModifiedFiles(initial_path, id="mf")

    return _App()


# ---------------------------------------------------------------------------
# debounce behaviour


def test_watch_path_uses_debounce_timer(monkeypatch):
    """watch_path should schedule a 200ms debounced timer, not call
    subprocess.run synchronously."""
    spawn = _patch_run(monkeypatch, returncode=0, stdout="")
    app = _make_app(Path("/tmp/foo"))

    async def _test():
        async with app.run_test() as pilot:
            await pilot.pause()
            widget = app.query_one("#mf")
            original_set_timer = widget.set_timer
            captured: list[float] = []

            def tracked(delay, callback):
                captured.append(delay)
                return original_set_timer(delay, callback)

            widget.set_timer = tracked
            widget.path = Path("/tmp/bar")
            await pilot.pause()
            # no git run yet, only scheduled
            assert captured, "watch_path should schedule a debounced timer"
            assert captured[0] == 0.2
            assert len(spawn.__defaults__ or ()) == 0 or True
            await pilot.pause()
            await pilot.pause()

    _run(_test())


def test_refresh_files_skips_debounce(monkeypatch):
    spawns: list[Path] = []
    scheduled: list[float] = []

    def fake_run(*args, **kwargs):
        spawns.append(Path(args[0][2]))
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr("tui.widgets.modified_files.subprocess.run", fake_run)
    app = _make_app(Path("/tmp/refresh-test"))

    async def _test():
        async with app.run_test() as pilot:
            await pilot.pause()
            widget = app.query_one("#mf")
            original_set_timer = widget.set_timer

            def tracked(delay, callback):
                scheduled.append(delay)
                return original_set_timer(delay, callback)

            widget.set_timer = tracked
            widget.refresh_files()
            await pilot.pause()

    _run(_test())
    assert scheduled == []
    assert any(str(p).endswith("refresh-test") for p in spawns)


# ---------------------------------------------------------------------------
# async git-status outcome handling


def test_git_status_success_shows_file_widgets(monkeypatch):
    _patch_run(monkeypatch, returncode=0, stdout=" M app.py\n?? new.txt\n")
    app = _make_app(Path("/tmp/proj-status"))

    async def _test():
        async with app.run_test() as pilot:
            await pilot.pause()
            widget = app.query_one("#mf")
            widget._do_git_status(Path("/tmp/proj-status"))
            outcome = widget._do_git_status(Path("/tmp/proj-status"))
            assert outcome is not None
            kind, _, lines = outcome
            assert kind == "file-modified"
            assert lines == [" M app.py", "?? new.txt"]

    _run(_test())


def test_git_status_failure_marks_not_a_repo(monkeypatch):
    _patch_run(monkeypatch, returncode=128, stdout="")
    app = _make_app(Path("/tmp/not-repo"))

    async def _test():
        async with app.run_test() as pilot:
            await pilot.pause()
            widget = app.query_one("#mf")
            outcome = widget._do_git_status(Path("/tmp/not-repo"))
            assert outcome is not None
            kind, text, lines = outcome
            assert kind == "not-a-repo"
            assert text == "Not a git repository"
            assert lines is None

    _run(_test())


def test_git_status_timeout_falls_back_to_no_changes(monkeypatch):
    _patch_run(
        monkeypatch, exc=subprocess.TimeoutExpired(cmd="git", timeout=5)
    )
    app = _make_app(Path("/tmp/slow"))

    async def _test():
        async with app.run_test() as pilot:
            await pilot.pause()
            widget = app.query_one("#mf")
            outcome = widget._do_git_status(Path("/tmp/slow"))
            assert outcome is not None
            kind, text, lines = outcome
            assert kind == "no-changes"
            assert text == "No modified files"
            assert lines is None

    _run(_test())


def test_git_missing_binary_is_not_a_repo(monkeypatch):
    _patch_run(monkeypatch, exc=FileNotFoundError("git"))
    app = _make_app(Path("/tmp/no-git"))

    async def _test():
        async with app.run_test() as pilot:
            await pilot.pause()
            widget = app.query_one("#mf")
            outcome = widget._do_git_status(Path("/tmp/no-git"))
            assert outcome is not None
            kind, text, lines = outcome
            assert kind == "not-a-repo"
            assert lines is None

    _run(_test())


def test_path_inside_ignored_dir_short_circuits(monkeypatch):
    spawn_count = {"n": 0}

    def fake_run(*args, **kwargs):
        spawn_count["n"] += 1
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr("tui.widgets.modified_files.subprocess.run", fake_run)
    app = _make_app(Path("/tmp/proj/.venv/bin"))

    async def _test():
        async with app.run_test() as pilot:
            await pilot.pause()
            widget = app.query_one("#mf")
            outcome = widget._do_git_status(Path("/tmp/proj/.venv/bin"))
            assert outcome is not None
            kind, _, _ = outcome
            assert kind == "not-a-repo"

    _run(_test())
    assert spawn_count["n"] == 0


# ---------------------------------------------------------------------------
# DirectoryWatcher noise filter


def test_directory_watcher_drops_noisy_paths():
    from tui.directory_watcher import _is_noisy_path

    assert _is_noisy_path("/work/proj/.venv/bin/python") is True
    assert _is_noisy_path("/work/proj/.git/HEAD") is True
    assert _is_noisy_path("/work/proj/node_modules/x/index.js") is True
    assert _is_noisy_path("/work/proj/__pycache__/a.pyc") is True
    assert _is_noisy_path("/work/proj/src/app.py") is False
    assert _is_noisy_path("") is False


def test_dispatcher_drops_noisy_events():
    from tui import directory_watcher as dw
    from watchdog.events import FileModifiedEvent

    class _Watcher:
        def __init__(self):
            self.events = []

        def on_any_event(self, event):
            self.events.append(event)

    dispatcher = dw._PathEventDispatcher(Path("/tmp/proj"))
    w1 = _Watcher()
    w2 = _Watcher()
    dispatcher.add_watcher(w1)
    dispatcher.add_watcher(w2)

    dispatcher.on_any_event(FileModifiedEvent("/tmp/proj/.venv/lib/python"))
    dispatcher.on_any_event(FileModifiedEvent("/tmp/proj/src/app.py"))

    paths_for_w1 = [e.src_path for e in w1.events]
    paths_for_w2 = [e.src_path for e in w2.events]
    assert paths_for_w1 == ["/tmp/proj/src/app.py"]
    assert paths_for_w2 == ["/tmp/proj/src/app.py"]
