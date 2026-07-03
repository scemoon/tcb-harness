"""Tests for cdh platform / onecode engine split.

Covers:
- CdhSkillManager install/list/remove/version
- Bootstrap ensure_ai_dlc_skill
- Migration migrate_legacy_cdh_to_onecode
- Path separation symmetry (cdh ~/.cdh/skills/ vs onecode ~/.onecode/)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

import yaml


# ---------------------------------------------------------------------------
# Path separation: cdh platform vs onecode engine
# ---------------------------------------------------------------------------


def test_cdh_platform_skills_dir_is_dot_cdh():
    """CDH_PLATFORM_SKILLS_DIR must be under ~/.cdh/skills/, not ~/.onecode/."""
    from cdh.cdh_skill_manager import CDH_PLATFORM_SKILLS_DIR

    assert CDH_PLATFORM_SKILLS_DIR == Path.home() / ".cdh" / "skills"


def test_onecode_dir_is_dot_onecode():
    """ONECODE_DIR must be ~/.onecode/, not ~/.cdh/."""
    from onecode.config import ONECODE_DIR

    assert ONECODE_DIR == Path.home() / ".onecode"


def test_paths_are_different():
    """cdh platform and onecode engine must use distinct paths."""
    from cdh.cdh_skill_manager import CDH_PLATFORM_SKILLS_DIR
    from onecode.config import ONECODE_DIR

    assert CDH_PLATFORM_SKILLS_DIR != ONECODE_DIR
    assert str(CDH_PLATFORM_SKILLS_DIR).count(".cdh") == 1
    assert str(ONECODE_DIR).count(".onecode") == 1


# ---------------------------------------------------------------------------
# CdhSkillManager: install / list / remove / version
# ---------------------------------------------------------------------------


def _make_source_skill(tmp_path: Path, name: str = "test-skill", version: str = "1.0.0") -> Path:
    src = tmp_path / name
    src.mkdir()
    skill_yaml = src / "skill.yaml"
    skill_data = {"name": name, "metadata": {"version": version}}
    skill_yaml.write_text(yaml.dump(skill_data))
    (src / "SKILL.md").write_text(f"# {name} skill")
    (src / "components").mkdir()
    (src / "components" / "web.md").write_text("# Web component")
    return src


class TestCdhSkillManager:
    def test_install_copies_files(self, tmp_path):
        skills_dir = tmp_path / ".cdh" / "skills"
        mgr = _make_mgr(skills_dir)
        src = _make_source_skill(tmp_path, "my-skill", "2.0.0")

        err = mgr.install(src)
        assert err is None

        target = skills_dir / "my-skill"
        assert target.is_dir()
        assert (target / "skill.yaml").exists()
        assert (target / "SKILL.md").exists()
        assert (target / "components" / "web.md").exists()
        assert (target / ".installed_version").exists()
        assert (target / ".installed_version").read_text().strip() == "2.0.0"

    def test_install_missing_skill_yaml(self, tmp_path):
        skills_dir = tmp_path / ".cdh" / "skills"
        mgr = _make_mgr(skills_dir)
        src = tmp_path / "no-yaml"
        src.mkdir()
        (src / "SKILL.md").write_text("# orphan")

        err = mgr.install(src)
        assert err is not None
        assert "skill.yaml" in err

    def test_install_skips_dotfiles(self, tmp_path):
        skills_dir = tmp_path / ".cdh" / "skills"
        mgr = _make_mgr(skills_dir)
        src = _make_source_skill(tmp_path, "clean-skill")
        (src / ".secret").write_text("hidden")

        mgr.install(src)
        target = skills_dir / "clean-skill"
        assert not (target / ".secret").exists()

    def test_list_returns_installed_skills(self, tmp_path):
        skills_dir = tmp_path / ".cdh" / "skills"
        mgr = _make_mgr(skills_dir)
        src_a = _make_source_skill(tmp_path, "skill-a", "1.0.0")
        src_b = _make_source_skill(tmp_path, "skill-b", "2.0.0")
        mgr.install(src_a)
        mgr.install(src_b)

        skills = mgr.list()
        names = {s.get("name") for s in skills}
        assert "skill-a" in names
        assert "skill-b" in names

    def test_get_installed_version(self, tmp_path):
        skills_dir = tmp_path / ".cdh" / "skills"
        mgr = _make_mgr(skills_dir)
        src = _make_source_skill(tmp_path, "ver-skill", "3.0.0")
        mgr.install(src)

        version = mgr.get_installed_version("ver-skill")
        assert version == "3.0.0"

    def test_get_installed_version_none_when_missing(self, tmp_path):
        skills_dir = tmp_path / ".cdh" / "skills"
        mgr = _make_mgr(skills_dir)
        assert mgr.get_installed_version("nonexistent") is None

    def test_remove_deletes_skill(self, tmp_path):
        skills_dir = tmp_path / ".cdh" / "skills"
        mgr = _make_mgr(skills_dir)
        src = _make_source_skill(tmp_path, "remove-me")
        mgr.install(src)
        assert (skills_dir / "remove-me").exists()

        err = mgr.remove("remove-me")
        assert err is None
        assert not (skills_dir / "remove-me").exists()

    def test_remove_nonexistent_returns_error(self, tmp_path):
        skills_dir = tmp_path / ".cdh" / "skills"
        mgr = _make_mgr(skills_dir)
        err = mgr.remove("ghost")
        assert err is not None
        assert "not found" in err

    def test_list_empty_when_no_skills(self, tmp_path):
        skills_dir = tmp_path / ".cdh" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        mgr = _make_mgr(skills_dir)
        assert mgr.list() == []


# ---------------------------------------------------------------------------
# Bootstrap: ensure_ai_dlc_skill
# ---------------------------------------------------------------------------


def _make_skill_yaml(path: Path, name: str = "ai-dlc-skill", version: str = "4.0.0"):
    path.mkdir(parents=True, exist_ok=True)
    data = {"name": name, "metadata": {"version": version}}
    (path / "skill.yaml").write_text(yaml.dump(data))
    (path / "SKILL.md").write_text(f"# {name} v{version}")
    return path


class TestBootstrap:
    def test_get_source_skill_dir_finds_at_root(self, tmp_path):
        from onecode.skills.bootstrap import get_source_skill_dir

        skill = _make_skill_yaml(tmp_path / "ai-dlc-skill")
        result = get_source_skill_dir(tmp_path)
        assert result == skill

    def test_get_source_skill_dir_finds_at_parent(self, tmp_path):
        from onecode.skills.bootstrap import get_source_skill_dir

        # workspace one level below the skill
        child = tmp_path / "sub"
        child.mkdir(parents=True)
        skill = _make_skill_yaml(tmp_path / "ai-dlc-skill")
        result = get_source_skill_dir(child)
        assert result == skill

    def test_get_source_skill_dir_finds_at_git_root(self, tmp_path):
        from onecode.skills.bootstrap import get_source_skill_dir

        (tmp_path / ".git").mkdir()
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        skill = _make_skill_yaml(tmp_path / "ai-dlc-skill")
        result = get_source_skill_dir(deep)
        assert result == skill

    def test_get_source_skill_dir_returns_none_when_missing(self, tmp_path):
        from onecode.skills.bootstrap import get_source_skill_dir

        assert get_source_skill_dir(tmp_path) is None

    def test_get_source_skill_dir_ignores_missing_skill_yaml(self, tmp_path):
        from onecode.skills.bootstrap import get_source_skill_dir

        (tmp_path / "ai-dlc-skill").mkdir()
        result = get_source_skill_dir(tmp_path)
        assert result is None

    def test_get_source_version_reads_from_yaml(self, tmp_path):
        from onecode.skills.bootstrap import get_source_version

        skill = _make_skill_yaml(tmp_path / "ai-dlc-skill", version="5.0.0")
        assert get_source_version(skill) == "5.0.0"

    def test_get_source_version_fallback(self, tmp_path):
        from onecode.skills.bootstrap import DEFAULT_VERSION, get_source_version

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        assert get_source_version(empty_dir) == DEFAULT_VERSION

    def test_ensure_ai_dlc_skill_skips_when_up_to_date(self, tmp_path, caplog):
        from onecode.skills.bootstrap import ensure_ai_dlc_skill

        _make_skill_yaml(tmp_path / "ai-dlc-skill", version="4.0.0")
        skills_pool = tmp_path / ".cdh" / "skills"
        skills_pool.mkdir(parents=True)
        # Pre-install same version
        (skills_pool / "ai-dlc-skill").mkdir()
        (skills_pool / "ai-dlc-skill" / ".installed_version").write_text("4.0.0\n")

        caplog.set_level(logging.DEBUG)
        with patch("onecode.skills.bootstrap.Path.cwd", return_value=tmp_path):
            with patch(
                "cdh.cdh_skill_manager.CDH_PLATFORM_SKILLS_DIR",
                skills_pool,
            ):
                ensure_ai_dlc_skill(tmp_path)

        assert any("current" in r.message for r in caplog.records)

    def test_ensure_ai_dlc_skill_installs_when_missing(self, tmp_path):
        from onecode.skills.bootstrap import ensure_ai_dlc_skill

        _make_skill_yaml(tmp_path / "ai-dlc-skill", version="4.0.0")
        skills_pool = tmp_path / ".cdh" / "skills"
        skills_pool.mkdir(parents=True)

        with patch("onecode.skills.bootstrap.Path.cwd", return_value=tmp_path):
            with patch(
                "cdh.cdh_skill_manager.CDH_PLATFORM_SKILLS_DIR",
                skills_pool,
            ):
                ensure_ai_dlc_skill(tmp_path)

            assert (skills_pool / "ai-dlc-skill").exists()
            assert (skills_pool / "ai-dlc-skill" / ".installed_version").exists()

    def test_ensure_ai_dlc_skill_warns_when_source_not_found(self, caplog):
        from onecode.skills.bootstrap import ensure_ai_dlc_skill

        with patch("onecode.skills.bootstrap.Path.cwd", return_value=Path("/tmp/nonexistent")):
            ensure_ai_dlc_skill(Path("/tmp/nonexistent"))

        assert any(
            "not found" in r.message.lower() for r in caplog.records
        )


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

        # Create onecode-private dirs
        for d in ["sessions", "logs", "traces", "memory", "mcps", "models"]:
            (legacy / d).mkdir()
            (legacy / d / "test.txt").write_text(d)

        # Create cdh platform dirs (should NOT migrate)
        for d in ["skills", "projects", "state"]:
            (legacy / d).mkdir()
            (legacy / d / "keep.txt").write_text(d)

        # Create onecode dotfile
        (legacy / "onecode.config.yaml").write_text("key: val")

        result = migrate_legacy_cdh_to_onecode(
            legacy_dir=legacy,
            target_dir=target,
        )
        assert result is not None
        assert "sessions" in result
        assert "logs" in result
        assert "traces" in result
        assert "memory" in result
        assert "mcps" in result
        assert "models" in result

        # Verify private dirs moved
        for d in ["sessions", "logs", "traces", "memory", "mcps", "models"]:
            assert (target / d).is_dir()
            assert (target / d / "test.txt").exists()

        # Verify platform dirs remain at legacy
        for d in ["skills", "projects", "state"]:
            assert (legacy / d).is_dir(), f"{d} should remain in legacy"
            assert (legacy / d / "keep.txt").exists()

        # Verify dotfile migrated
        assert (target / "onecode.config.yaml").exists()

        # Verify migration marker
        assert (target / ".migrated_from").exists()
        marker = json.loads((target / ".migrated_from").read_text())
        assert marker["migrated_from"] == str(legacy)
        assert marker["migrated_to"] == str(target)
        assert "skills" in marker["preserved_on_legacy"]

    def test_both_exist_with_content_returns_warning(self, tmp_path):
        from onecode.migrate import migrate_legacy_cdh_to_onecode

        legacy = tmp_path / ".cdh"
        target = tmp_path / ".onecode"
        legacy.mkdir()
        target.mkdir()
        (legacy / "sessions").mkdir()
        (target / "sessions").mkdir()

        result = migrate_legacy_cdh_to_onecode(
            legacy_dir=legacy,
            target_dir=target,
        )
        assert result is not None
        assert "Both" in result

    def test_target_empty_but_exists_proceeds(self, tmp_path):
        from onecode.migrate import migrate_legacy_cdh_to_onecode

        legacy = tmp_path / ".cdh"
        target = tmp_path / ".onecode"
        legacy.mkdir()
        target.mkdir()  # empty target
        (legacy / "sessions").mkdir()
        (legacy / "sessions" / "session.json").write_text("{}")

        result = migrate_legacy_cdh_to_onecode(
            legacy_dir=legacy,
            target_dir=target,
        )
        assert result is not None
        assert (target / "sessions" / "session.json").exists()

    def test_marker_contains_correct_data(self, tmp_path):
        from onecode.migrate import migrate_legacy_cdh_to_onecode

        legacy = tmp_path / ".cdh"
        target = tmp_path / ".onecode"
        legacy.mkdir()
        (legacy / "sessions").mkdir()
        (legacy / "traces").mkdir()
        (legacy / "skills").mkdir()  # platform dir

        migrate_legacy_cdh_to_onecode(legacy_dir=legacy, target_dir=target)

        marker = json.loads((target / ".migrated_from").read_text())
        assert sorted(marker["items"]) == ["sessions", "traces"]
        assert "skills" in marker["preserved_on_legacy"]

    def test_no_private_dirs_returns_none(self, tmp_path):
        from onecode.migrate import migrate_legacy_cdh_to_onecode

        legacy = tmp_path / ".cdh"
        target = tmp_path / ".onecode"
        legacy.mkdir()
        (legacy / "skills").mkdir()  # only platform dir

        result = migrate_legacy_cdh_to_onecode(
            legacy_dir=legacy,
            target_dir=target,
        )
        # Only platform dirs exist, no onecode private dirs → no migration needed
        assert result is None
        # No private dirs should have been migrated
        for d in ["sessions", "logs", "traces", "memory", "snapshots", "mcps", "models"]:
            assert not (target / d).exists()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mgr(skills_dir: Path):
    from cdh.cdh_skill_manager import CdhSkillManager

    return CdhSkillManager(skills_dir=skills_dir)
