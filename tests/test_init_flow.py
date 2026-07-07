"""Regression tests for the f3 -> ProjectsScreen -> Init flow.

These cover the bug where using the Init configuration in the project
screen did not actually convert the specified directory into a cdh
project, and the initialized project did not show up in the project
list.  The tests pin down the behaviour of the underlying methods
without launching a full Textual app.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml


# ---------------------------------------------------------------------------
# helpers


def _build_screen(home_dot_cdh: Path):
    """Return a ProjectsScreen instance wired against a mock app/grid.

    The screen is created without ``__init__`` so the textual
    ModalScreen base is bypassed; we only need the methods under test.
    The projects dir is resolved at runtime via ``Path.home()``, so
    the caller must patch ``Path.home`` via monkeypatch (see
    ``sandbox`` fixture).
    """
    from tui.screens import projects_screen
    from tui.widgets.project_grid_select import ProjectGridSelect

    screen = projects_screen.ProjectsScreen.__new__(projects_screen.ProjectsScreen)
    screen.app = MagicMock()
    screen.notify = MagicMock()
    screen._delete_confirm_time = 0.0

    grid = MagicMock(spec=ProjectGridSelect)
    grid.children = []
    grid.highlighted = None
    grid.mount = MagicMock()
    screen.project_grid_select = grid

    return screen


def _build_grid(home_dot_cdh: Path):
    """Return a ProjectGridSelect instance with a sandboxed projects dir."""
    from tui.widgets import project_grid_select

    return project_grid_select.ProjectGridSelect.__new__(
        project_grid_select.ProjectGridSelect
    )


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    """Per-test sandbox with an isolated ``~/.cdh/projects`` directory."""
    test_home = tmp_path / "home"
    test_home.mkdir(parents=True)
    home_dot_cdh = test_home / ".cdh"
    home_dot_cdh.mkdir(parents=True)
    (home_dot_cdh / "projects").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", lambda: test_home)
    return home_dot_cdh


# ---------------------------------------------------------------------------
# init_dlc_project contract


def test_init_dlc_project_raises_when_skill_missing(monkeypatch, tmp_path):
    """When ai-dlc-skill cannot be located, init_dlc_project must raise
    a RuntimeError instead of silently returning False (which left the
    caller thinking the project was scaffolded)."""
    from cdh import scaffold

    monkeypatch.setattr(scaffold, "_detect_dlc_skill", lambda *_a, **_kw: False)

    with pytest.raises(RuntimeError):
        scaffold.init_dlc_project(tmp_path, "demo")

    # nothing should have been written
    assert not (tmp_path / "aidlc" / "project.yaml").exists()
    assert not (tmp_path / ".cdh").exists()


def test_init_dlc_project_writes_metadata_when_skill_available(
    monkeypatch, tmp_path
):
    from cdh import scaffold

    monkeypatch.setattr(scaffold, "_detect_dlc_skill", lambda *_a, **_kw: True)
    assert scaffold.init_dlc_project(tmp_path, "demo") is True
    assert (tmp_path / "aidlc" / "project.yaml").exists()
    assert (tmp_path / "aidlc" / "requirements.md").exists()
    assert (tmp_path / ".gitignore").exists()


# ---------------------------------------------------------------------------
# _on_init_components: cancel must abort


def test_picker_cancel_aborts_init(sandbox, tmp_path, monkeypatch):
    """Canceling the ComponentPicker must NOT create any files or
    mount a widget.  This is the most likely cause of the user
    confusion: pressing Esc in the picker still triggered init because
    the lambda passed `None` straight through to _do_init_project."""
    target = tmp_path / "cancel_target"
    target.mkdir()
    projects_dir = sandbox / "projects"

    screen = _build_screen(sandbox)
    screen._on_init_components(target, None)

    assert not (projects_dir / "cancel_target.yaml").exists()
    assert not (target / ".cdh").exists()
    assert not screen.project_grid_select.mount.called

    notify_msgs = [c.args[0] for c in screen.notify.call_args_list if c.args]
    assert any("cancel" in m.lower() for m in notify_msgs)


def test_picker_empty_selection_still_initialises(sandbox, tmp_path, monkeypatch):
    """allow_empty=True for the Init picker means an empty list is a
    valid user choice, not a cancel."""
    from cdh import scaffold

    monkeypatch.setattr(scaffold, "_detect_dlc_skill", lambda *_a, **_kw: True)

    target = tmp_path / "empty_init"
    target.mkdir()
    projects_dir = sandbox / "projects"

    screen = _build_screen(sandbox)
    screen._on_init_components(target, [])

    assert (target / "aidlc" / "project.yaml").exists()
    assert (target / ".cdh" / "config.yaml").exists()
    assert (projects_dir / "empty_init.yaml").exists()
    assert screen.project_grid_select.mount.called


# ---------------------------------------------------------------------------
# _do_init_project: skill failure visible


def test_init_dlc_failure_surfaces(sandbox, tmp_path, monkeypatch):
    """If init_dlc_project raises (skill missing), no .cdh/ should be
    written and no widget mounted.  Previously the failure was silent
    and the caller proceeded with CdhProjectLoader.init_project, leaving
    a half-initialized project."""
    from onecode.agent import cdh_loader
    from cdh import scaffold

    monkeypatch.setattr(scaffold, "_detect_dlc_skill", lambda *_a, **_kw: False)
    init_project_mock = MagicMock()
    monkeypatch.setattr(
        cdh_loader.CdhProjectLoader, "init_project", staticmethod(init_project_mock)
    )

    target = tmp_path / "fail_target"
    target.mkdir()
    projects_dir = sandbox / "projects"

    screen = _build_screen(sandbox)
    screen._do_init_project(target, [])

    assert not (target / ".cdh").exists()
    assert not (projects_dir / "fail_target.yaml").exists()
    assert not screen.project_grid_select.mount.called
    assert not init_project_mock.called

    notify_msgs = [c.args[0] for c in screen.notify.call_args_list if c.args]
    assert any("ai-dlc-skill" in m for m in notify_msgs)


# ---------------------------------------------------------------------------
# _do_init_project: FileNotFoundError from add_component caught


def test_add_component_file_not_found_caught(sandbox, tmp_path, monkeypatch):
    """add_component raises FileNotFoundError if project.yaml doesn't
    exist.  Previously this was uncaught and would crash the modal."""
    from cdh import scaffold

    monkeypatch.setattr(scaffold, "_detect_dlc_skill", lambda *_a, **_kw: True)

    target = tmp_path / "fnf_target"
    target.mkdir()

    original_add_component = scaffold.add_component

    def patched_add_component(root, component_id):
        (root / "aidlc" / "project.yaml").unlink()
        return original_add_component(root, component_id)

    monkeypatch.setattr(scaffold, "add_component", patched_add_component)

    screen = _build_screen(sandbox)
    # must not raise
    screen._do_init_project(target, ["web"])

    notify_msgs = [c.args[0] for c in screen.notify.call_args_list if c.args]
    assert any("not found" in m.lower() or "project.yaml" in m for m in notify_msgs)


# ---------------------------------------------------------------------------
# _do_init_project: duplicate name detection


def test_duplicate_project_name_aborts(sandbox, tmp_path, monkeypatch):
    """Re-init with the same name must NOT clobber the existing entry
    or crash with DuplicateIds."""
    from cdh import scaffold

    monkeypatch.setattr(scaffold, "_detect_dlc_skill", lambda *_a, **_kw: True)

    target = tmp_path / "dup_target"
    target.mkdir()
    projects_dir = sandbox / "projects"
    # pre-existing project entry
    (projects_dir / "dup_target.yaml").write_text(
        yaml.dump({"name": "dup_target", "path": "/somewhere", "description": ""})
    )

    screen = _build_screen(sandbox)
    screen._do_init_project(target, [])

    assert not screen.project_grid_select.mount.called
    notify_msgs = [c.args[0] for c in screen.notify.call_args_list if c.args]
    assert any("already" in m for m in notify_msgs)

    # the pre-existing file should be untouched
    pre_existing = yaml.safe_load((projects_dir / "dup_target.yaml").read_text())
    assert pre_existing["path"] == "/somewhere"


# ---------------------------------------------------------------------------
# _do_init_project: normal happy path


def test_do_init_project_creates_files(sandbox, tmp_path, monkeypatch):
    from cdh import scaffold

    monkeypatch.setattr(scaffold, "_detect_dlc_skill", lambda *_a, **_kw: True)

    target = tmp_path / "happy_path"
    target.mkdir()
    projects_dir = sandbox / "projects"

    screen = _build_screen(sandbox)
    screen._do_init_project(target, [])

    assert (target / "aidlc" / "project.yaml").exists()
    assert (target / "aidlc" / "requirements.md").exists()
    assert (target / ".cdh" / "config.yaml").exists()
    assert (projects_dir / "happy_path.yaml").exists()
    assert screen.project_grid_select.mount.called
    widget = screen.project_grid_select.mount.call_args[0][0]
    assert widget.id == "happy_path"
    assert widget._project_path == str(target)


def test_do_init_project_with_components_creates_apps_dirs(
    sandbox, tmp_path, monkeypatch
):
    from cdh import scaffold

    monkeypatch.setattr(scaffold, "_detect_dlc_skill", lambda *_a, **_kw: True)

    target = tmp_path / "with_components"
    target.mkdir()
    projects_dir = sandbox / "projects"

    screen = _build_screen(sandbox)
    screen._do_init_project(target, ["web", "backend"])

    assert (target / "apps" / "web").is_dir()
    assert (target / "apps" / "backend").is_dir()
    assert (projects_dir / "with_components.yaml").exists()


# ---------------------------------------------------------------------------
# db (project list) pre-checks in the path handlers


def test_on_init_path_rejects_db_existing(sandbox, tmp_path):
    """If the project is already in ~/.cdh/projects/, the init path
    handler must reject the input early — no picker should pop up,
    no .cdh/ should be created."""

    target = tmp_path / "already_in_db"
    target.mkdir()
    projects_dir = sandbox / "projects"
    (projects_dir / "already_in_db.yaml").write_text(
        yaml.dump({"name": "already_in_db", "path": "/somewhere"})
    )

    screen = _build_screen(sandbox)
    pushed = []
    screen.app.push_screen = lambda s, cb=None: pushed.append(s)  # type: ignore[assignment]
    screen._on_init_path(str(target))

    # no ComponentPicker should have been pushed
    assert not pushed, "picker should not be pushed when project is already in db"
    assert not (target / ".cdh").exists()
    notify_msgs = [c.args[0] for c in screen.notify.call_args_list if c.args]
    assert any("already" in m for m in notify_msgs)


def test_on_new_project_path_rejects_db_existing(sandbox, tmp_path):
    """Same as init: New path handler must reject when the project is
    already in the project list."""
    target = tmp_path / "new_already_in_db"
    target.mkdir()
    projects_dir = sandbox / "projects"
    (projects_dir / "new_already_in_db.yaml").write_text(
        yaml.dump({"name": "new_already_in_db", "path": "/elsewhere"})
    )

    screen = _build_screen(sandbox)
    pushed = []
    screen.app.push_screen = lambda s, cb=None: pushed.append(s)  # type: ignore[assignment]
    screen._on_new_project_path(str(target))

    assert not pushed, "picker should not be pushed when project is already in db"
    notify_msgs = [c.args[0] for c in screen.notify.call_args_list if c.args]
    assert any("already" in m for m in notify_msgs)


def test_db_check_supports_all_extensions(sandbox):
    """The pre-check must look at .yaml/.yml/.json, matching the
    other places that iterate over the same extensions."""
    projects_dir = sandbox / "projects"
    (projects_dir / "jsonproj.json").write_text(
        json.dumps({"name": "jsonproj", "path": "/x"})
    )
    (projects_dir / "ymlproj.yml").write_text("name: ymlproj\npath: /y\n")

    _screen = _build_screen(sandbox)
    # jsonproj should be detected

    from tui.screens.projects_screen import _project_db_path

    assert _project_db_path("jsonproj") is not None
    assert _project_db_path("ymlproj") is not None
    assert _project_db_path("not_in_db") is None


# ---------------------------------------------------------------------------
# _do_new_project: also requires non-empty and rejects duplicates


def test_new_project_cancelled_picks_aborts(sandbox, tmp_path, monkeypatch):

    target = tmp_path / "new_cancel"
    target.mkdir()
    projects_dir = sandbox / "projects"

    screen = _build_screen(sandbox)
    screen._on_new_project_components(target, None)

    assert not (projects_dir / "new_cancel.yaml").exists()
    assert not (target / ".cdh").exists()
    assert not screen.project_grid_select.mount.called
    notify_msgs = [c.args[0] for c in screen.notify.call_args_list if c.args]
    assert any("cancel" in m.lower() for m in notify_msgs)


def test_new_project_empty_selection_aborts(sandbox, tmp_path, monkeypatch):
    """New (unlike Init) must reject empty selection — allow_empty=False."""

    target = tmp_path / "new_empty"
    target.mkdir()
    projects_dir = sandbox / "projects"

    screen = _build_screen(sandbox)
    screen._on_new_project_components(target, [])

    assert not (projects_dir / "new_empty.yaml").exists()
    assert not screen.project_grid_select.mount.called


# ---------------------------------------------------------------------------
# EditFieldScreen strips whitespace


def test_edit_field_screen_strips_input(tmp_path, monkeypatch):
    """The path input on the EditFieldScreen must be stripped before
    being passed to the callback.  Otherwise trailing whitespace breaks
    Path.is_dir() checks."""
    from onecode.config_screen import EditFieldScreen

    target_dir = tmp_path / "strip_target"
    target_dir.mkdir()
    captured: list[str | None] = []

    screen = EditFieldScreen.__new__(EditFieldScreen)
    screen.field_label = "x"
    screen.current_value = ""

    fake_input = MagicMock()
    fake_input.value = f"  {target_dir}  \n"

    screen.query_one = lambda selector, _type: fake_input  # type: ignore[assignment]
    screen.dismiss = lambda value: captured.append(value)  # type: ignore[assignment]

    screen.on_input_submitted()
    assert captured == [str(target_dir)]

    captured.clear()
    fake_input.value = "   \n   "
    screen.on_input_submitted()
    assert captured == [None]


# ---------------------------------------------------------------------------
# ProjectGridSelect reads project path from yaml


def test_grid_select_uses_project_path_field(sandbox):
    """ProjectGridSelect must display the project directory path stored
    in the yaml file's ``path`` field, not the path to the yaml file
    itself."""
    from tui.widgets.project_grid_select import (
        _read_project_path,
    )

    projects_dir = sandbox / "projects"

    real = "/private/tmp/some_real_project"
    (projects_dir / "good.yaml").write_text(
        yaml.dump({"name": "good", "path": real, "description": ""})
    )
    (projects_dir / "jsonproj.json").write_text(
        json.dumps({"name": "jsonproj", "path": "/tmp/json_proj"})
    )
    (projects_dir / "fallback.yaml").write_text("name: fallback\n")

    assert _read_project_path(projects_dir / "good.yaml") == real
    assert _read_project_path(projects_dir / "jsonproj.json") == "/tmp/json_proj"
    # fallback returns the yaml file path
    assert _read_project_path(projects_dir / "fallback.yaml") == str(
        projects_dir / "fallback.yaml"
    )

    grid = _build_grid(sandbox)
    summaries = list(grid.compose())
    by_id = {s.id: s for s in summaries}
    assert "good" in by_id
    assert "jsonproj" in by_id
    assert "fallback" in by_id
    assert by_id["good"]._project_path == real
    assert by_id["jsonproj"]._project_path == "/tmp/json_proj"


def test_grid_select_handles_corrupt_yaml(sandbox):
    """A corrupt yaml file must not crash compose() or _read_project_path."""
    from tui.widgets.project_grid_select import _read_project_path

    projects_dir = sandbox / "projects"
    (projects_dir / "broken.yaml").write_text(":\n  - [unterminated")

    assert _read_project_path(projects_dir / "broken.yaml") == str(
        projects_dir / "broken.yaml"
    )
