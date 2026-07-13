"""Tests for cdh platform / onecode engine split.

Covers:
- Migration migrate_legacy_cdh_to_onecode
- Path separation symmetry (cdh ~/.cdh/ vs onecode ~/.onecode/)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import yaml


# ---------------------------------------------------------------------------
# Path separation: cdh platform vs onecode engine
# ---------------------------------------------------------------------------


def test_onecode_dir_is_dot_onecode():
    """ONECODE_DIR must be ~/.onecode/, not ~/.cdh/."""
    from onecode.config import ONECODE_DIR

    assert ONECODE_DIR == Path.home() / ".onecode"


# ---------------------------------------------------------------------------
# Migration: migrate_legacy_cdh_to_onecode
# ---------------------------------------------------------------------------


class TestMigration:
    def test_no_legacy_dir_returns_none(self, tmp_path):
        from onecode.migrate import migrate_legacy_cdh_to_onecode

        result = migrate_legacy_cdh_to_onecode(
            legacy_dir=tmp_path / "ghost",
            target_dir=tmp_path / ".onecode",
        )
        assert result is None

    def test_already_migrated_returns_none(self, tmp_path):
        from onecode.migrate import migrate_legacy_cdh_to_onecode

        legacy = tmp_path / ".cdh"
        target = tmp_path / ".onecode"
        legacy.mkdir(parents=True)
        target.mkdir(parents=True)
        (target / ".migrated_from").write_text("{}")

        result = migrate_legacy_cdh_to_onecode(
            legacy_dir=legacy,
            target_dir=target,
        )
        assert result is None

    def test_migrates_private_dirs(self, tmp_path):
        from onecode.migrate import migrate_legacy_cdh_to_onecode

        legacy = tmp_path / ".cdh"
        target = tmp_path / ".onecode"
        legacy.mkdir()

        # Create onecode-private dirs (sessions is deliberately excluded —
        # it belongs to cdh platform, see B mapping mode)
        for d in ["logs", "traces", "memory", "mcps", "models"]:
            (legacy / d).mkdir()
            (legacy / d / "test.txt").write_text(d)

        # Create cdh platform dirs (should NOT migrate)
        for d in ["projects", "state"]:
            (legacy / d).mkdir()
            (legacy / d / "keep.txt").write_text(d)

        # Create onecode dotfile
        (legacy / "onecode.config.yaml").write_text("key: val")

        # sessions is a cdh platform dir — should NOT migrate
        (legacy / "sessions").mkdir()
        (legacy / "sessions" / "session.json").write_text("{}")

        result = migrate_legacy_cdh_to_onecode(
            legacy_dir=legacy,
            target_dir=target,
        )
        assert result is not None
        assert "sessions" not in result
        assert "logs" in result
        assert "traces" in result
        assert "memory" in result
        assert "mcps" in result
        assert "models" in result

        # Verify private dirs moved
        for d in ["logs", "traces", "memory", "mcps", "models"]:
            assert (target / d).is_dir()
            assert (target / d / "test.txt").exists()

        # sessions should NOT be moved (cdh platform layer)
        assert not (target / "sessions").exists()
        assert (legacy / "sessions").is_dir()  # stays in cdh

        # Verify platform dirs remain at legacy
        for d in ["projects", "state"]:
            assert (legacy / d).is_dir(), f"{d} should remain in legacy"
            assert (legacy / d / "keep.txt").exists()

        # Verify dotfile migrated
        assert (target / "onecode.config.yaml").exists()

        # Verify migration marker
        assert (target / ".migrated_from").exists()
        marker = json.loads((target / ".migrated_from").read_text())
        assert marker["migrated_from"] == str(legacy)
        assert marker["migrated_to"] == str(target)

    def test_both_exist_independently_returns_none(self, tmp_path):
        """If both ~/.cdh/ and ~/.onecode/ exist with content, skip migration."""
        from onecode.migrate import migrate_legacy_cdh_to_onecode

        legacy = tmp_path / ".cdh"
        target = tmp_path / ".onecode"
        legacy.mkdir()
        target.mkdir()
        (legacy / "traces").mkdir()
        (target / "traces").mkdir()
        (legacy / "sessions").mkdir()  # sessions is cdh — not in _ONECODE_PRIVATE_DIRS
        (target / "sessions").mkdir()

        result = migrate_legacy_cdh_to_onecode(
            legacy_dir=legacy,
            target_dir=target,
        )
        assert result is None

    def test_target_empty_but_exists_proceeds(self, tmp_path):
        from onecode.migrate import migrate_legacy_cdh_to_onecode

        legacy = tmp_path / ".cdh"
        target = tmp_path / ".onecode"
        legacy.mkdir()
        target.mkdir()  # empty target
        (legacy / "traces").mkdir()
        (legacy / "traces" / "trace.txt").write_text("trace")

        result = migrate_legacy_cdh_to_onecode(
            legacy_dir=legacy,
            target_dir=target,
        )
        assert result is not None
        assert (target / "traces" / "trace.txt").exists()

    def test_marker_contains_correct_data(self, tmp_path):
        from onecode.migrate import migrate_legacy_cdh_to_onecode

        legacy = tmp_path / ".cdh"
        target = tmp_path / ".onecode"
        legacy.mkdir()
        (legacy / "traces").mkdir()
        (legacy / "memory").mkdir()
        (legacy / "sessions").mkdir()  # cdh platform — not migrated

        migrate_legacy_cdh_to_onecode(legacy_dir=legacy, target_dir=target)

        marker = json.loads((target / ".migrated_from").read_text())
        # sessions is NOT migrated — it belongs to cdh platform
        assert sorted(marker["items"]) == ["memory", "traces"]

    def test_no_private_dirs_returns_none(self, tmp_path):
        from onecode.migrate import migrate_legacy_cdh_to_onecode

        legacy = tmp_path / ".cdh"
        target = tmp_path / ".onecode"
        legacy.mkdir()

        result = migrate_legacy_cdh_to_onecode(
            legacy_dir=legacy,
            target_dir=target,
        )
        # No onecode private dirs → no migration needed
        assert result is None
        # No private dirs should have been migrated
        for d in ["sessions", "logs", "traces", "memory", "snapshots", "mcps", "models"]:
            assert not (target / d).exists()


# ---------------------------------------------------------------------------
# Session storage: cdh platform owns sessions, not individual engines
# ---------------------------------------------------------------------------


class TestSessionStorage:
    def test_get_sessions_returns_cdh_dir(self):
        """Sessions JSON belongs to cdh platform (~/.cdh/sessions/)."""
        from tui.paths import get_sessions

        path = get_sessions()
        assert ".cdh" in str(path)
        assert "sessions" in str(path)
        assert ".onecode" not in str(path)

    def test_default_storage_path_is_cdh_sessions(self):
        """AgentSession._default_storage_path returns ~/.cdh/sessions/."""
        from onecode.agent.session import AgentSession

        path = AgentSession()._default_storage_path()
        assert path == Path.home() / ".cdh" / "sessions"

    def test_default_storage_path_self_heals_onecode_sessions(self, tmp_path):
        """Sessions incorrectly saved to ~/.onecode/sessions/ are moved to cdh."""
        from unittest.mock import patch
        from onecode.agent.session import AgentSession

        # Simulate stale onecode sessions
        fake_cdh = tmp_path / ".cdh" / "sessions"
        fake_oc = tmp_path / ".onecode" / "sessions"
        fake_oc.mkdir(parents=True)
        (fake_oc / "stale.json").write_text('{"id": "stale"}')
        (fake_oc / "recent.json").write_text('{"id": "recent"}')
        # Place a file in cdh that conflicts — should NOT be overwritten
        fake_cdh.mkdir(parents=True)
        (fake_cdh / "recent.json").write_text('{"id": "recent-cdh"}')

        with patch.object(Path, "home", return_value=tmp_path):
            path = AgentSession()._default_storage_path()

        assert path == fake_cdh
        # stale.json was moved
        assert (fake_cdh / "stale.json").exists()
        assert not (fake_oc / "stale.json").exists()
        # recent.json was NOT overwritten (cdh version wins)
        assert (fake_cdh / "recent.json").read_text() == '{"id": "recent-cdh"}'
        # Marker exists
        assert (fake_cdh / ".migrated_from_onecode").exists()

    def test_migrate_excludes_sessions_from_private_dirs(self):
        """sessions must NOT be in _ONECODE_PRIVATE_DIRS."""
        from onecode.migrate import _ONECODE_PRIVATE_DIRS

        assert "sessions" not in _ONECODE_PRIVATE_DIRS
