"""Tests for skill system: create, search, builtin skills."""
from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from onecode.skills.create import create_skill_scaffold
from onecode.skills.loader import SkillLoader
from onecode.skills.manager import SkillManager
from onecode.skills.model import Skill


class TestSkillValidate:
    def test_valid_name_kebab_case(self):
        valid, err = Skill.validate_name("my-skill")
        assert valid
        assert err == ""

    def test_valid_name_single_word(self):
        valid, err = Skill.validate_name("shell")
        assert valid
        assert err == ""

    def test_valid_name_with_multiple_hyphens(self):
        valid, err = Skill.validate_name("ai-dlc-skill")
        assert valid
        assert err == ""

    def test_invalid_name_uppercase(self):
        valid, err = Skill.validate_name("MySkill")
        assert not valid

    def test_invalid_name_empty(self):
        valid, err = Skill.validate_name("")
        assert not valid

    def test_invalid_name_too_long(self):
        valid, err = Skill.validate_name("a" * 65)
        assert not valid

    def test_invalid_name_consecutive_hyphens(self):
        valid, err = Skill.validate_name("my--skill")
        assert not valid

    def test_invalid_name_startswith_hyphen(self):
        valid, err = Skill.validate_name("-my-skill")
        assert not valid

    def test_invalid_name_endswith_hyphen(self):
        valid, err = Skill.validate_name("my-skill-")
        assert not valid

    def test_validate_description_valid(self):
        valid, err = Skill.validate_description("A valid description")
        assert valid
        assert err == ""

    def test_validate_description_empty(self):
        valid, err = Skill.validate_description("")
        assert not valid

    def test_validate_description_too_long(self):
        valid, err = Skill.validate_description("a" * 1025)
        assert not valid


class TestCreateSkillScaffold:
    def test_create_basic_skill(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)
            err = create_skill_scaffold(skills_dir, "my-test-skill", "A test skill")
            assert err is None

            skill_path = skills_dir / "my-test-skill"
            assert skill_path.is_dir()

            skill_md = skill_path / "SKILL.md"
            assert skill_md.exists()
            content = skill_md.read_text()
            assert "name: my-test-skill" in content
            assert "A test skill" in content

            skill_yaml = skill_path / "skill.yaml"
            assert skill_yaml.exists()
            data = yaml.safe_load(skill_yaml.read_text())
            assert data["name"] == "my-test-skill"
            assert data["enabled"] is True

    def test_create_duplicate_skill(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)
            create_skill_scaffold(skills_dir, "dupe-skill", "First")
            err = create_skill_scaffold(skills_dir, "dupe-skill", "Second")
            assert err is not None
            assert "already exists" in err

    def test_create_without_description(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)
            err = create_skill_scaffold(skills_dir, "no-desc-skill")
            assert err is None
            content = (skills_dir / "no-desc-skill" / "SKILL.md").read_text()
            assert "A skill for no-desc-skill" in content


class TestSkillLoaderSearch:
    def _make_skill(
        self,
        base_dir: Path,
        name: str,
        description: str,
        triggers: list[str] | None = None,
        phases: list[str] | None = None,
    ) -> Path:
        skill_dir = base_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        frontmatter: dict = {"name": name, "description": description, "enabled": True}
        if triggers:
            frontmatter["triggers"] = triggers
        if phases:
            frontmatter["phases"] = phases
        fm_text = yaml.dump(frontmatter)
        body = f"# {name}\n\n{description}\n"
        (skill_dir / "SKILL.md").write_text(f"---\n{fm_text}---\n{body}")
        (skill_dir / "skill.yaml").write_text(
            yaml.dump({"name": name, "description": description, "enabled": True})
        )
        return skill_dir

    def test_search_by_name_exact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._make_skill(base, "git-workflow", "Git workflow helpers")
            self._make_skill(base, "python-test", "Python testing patterns")
            self._make_skill(base, "deploy-aws", "AWS deployment guides")

            loader = SkillLoader()
            loader._get_search_dirs = lambda: [("test", base)]
            loader.invalidate_cache()

            results = loader.search("git-workflow")
            assert len(results) == 1
            assert results[0].name == "git-workflow"

    def test_search_by_name_partial(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._make_skill(base, "git-workflow", "Git helpers")
            self._make_skill(base, "git-sync", "Sync repos")

            loader = SkillLoader()
            loader._get_search_dirs = lambda: [("test", base)]
            loader.invalidate_cache()

            results = loader.search("git")
            assert len(results) == 2

    def test_search_by_description(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._make_skill(base, "skill-a", "Browser automation")
            self._make_skill(base, "skill-b", "Database migrations")

            loader = SkillLoader()
            loader._get_search_dirs = lambda: [("test", base)]
            loader.invalidate_cache()

            results = loader.search("browser")
            assert len(results) == 1
            assert results[0].name == "skill-a"

    def test_search_by_triggers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._make_skill(base, "deploy-skill", "Deployment", triggers=["deploy", "k8s"])
            self._make_skill(base, "test-skill", "Testing", triggers=["test", "pytest"])

            loader = SkillLoader()
            loader._get_search_dirs = lambda: [("test", base)]
            loader.invalidate_cache()

            results = loader.search("deploy")
            assert len(results) == 1
            assert results[0].name == "deploy-skill"

    def test_search_by_phases(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._make_skill(base, "plan-skill", "Planning", phases=["plan"])
            self._make_skill(base, "verify-skill", "Verification", phases=["verify", "deliver"])

            loader = SkillLoader()
            loader._get_search_dirs = lambda: [("test", base)]
            loader.invalidate_cache()

            results = loader.search("verify")
            assert len(results) == 1
            assert results[0].name == "verify-skill"

    def test_search_no_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._make_skill(base, "my-skill", "Something")

            loader = SkillLoader()
            loader._get_search_dirs = lambda: [("test", base)]
            loader.invalidate_cache()

            results = loader.search("nonexistent")
            assert len(results) == 0

    def test_search_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._make_skill(base, "my-skill", "Deployment Guide")

            loader = SkillLoader()
            loader._get_search_dirs = lambda: [("test", base)]
            loader.invalidate_cache()

            assert len(loader.search("DEPLOYMENT")) == 1
            assert len(loader.search("deployment")) == 1

    def test_search_score_ordering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._make_skill(base, "git-helper", "Some tool that mentions git")
            self._make_skill(base, "git-core", "The git core skill")

            loader = SkillLoader()
            loader._get_search_dirs = lambda: [("test", base)]
            loader.invalidate_cache()

            results = loader.search("git-core")
            assert len(results) >= 1
            assert results[0].name == "git-core"


class TestSkillManager:
    def test_list_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SkillManager()
            mgr.skills_dir = Path(tmpdir)
            result = mgr.list()
            assert result == []

    def test_install_and_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "source"
            skills_dir = Path(tmpdir) / "skills"
            mgr = SkillManager()
            mgr.skills_dir = skills_dir

            src = src_dir / "source-skill"
            src.mkdir(parents=True)
            (src / "skill.yaml").write_text(
                yaml.dump({"name": "test-skill", "description": "A test", "enabled": True})
            )
            (src / "SKILL.md").write_text("# Test Skill\n\nHello.\n")

            err = mgr.install(src)
            assert err is None
            skills = mgr.list()
            assert len(skills) == 1
            assert skills[0]["name"] == "test-skill"

    def test_enable_disable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SkillManager()
            mgr.skills_dir = Path(tmpdir)

            mgr.skills_dir.mkdir(parents=True, exist_ok=True)
            skill_dir = mgr.skills_dir / "my-skill"
            skill_dir.mkdir()
            (skill_dir / "skill.yaml").write_text(
                yaml.dump({"name": "my-skill", "enabled": True})
            )

            mgr.enable("my-skill", False)
            data = yaml.safe_load((skill_dir / "skill.yaml").read_text())
            assert data["enabled"] is False

            mgr.enable("my-skill", True)
            data = yaml.safe_load((skill_dir / "skill.yaml").read_text())
            assert data["enabled"] is True

    def test_remove(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SkillManager()
            mgr.skills_dir = Path(tmpdir)

            mgr.skills_dir.mkdir(parents=True, exist_ok=True)
            skill_dir = mgr.skills_dir / "rm-skill"
            skill_dir.mkdir()
            (skill_dir / "skill.yaml").write_text(
                yaml.dump({"name": "rm-skill", "enabled": True})
            )

            err = mgr.remove("rm-skill")
            assert err is None
            assert not skill_dir.exists()

    def test_remove_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SkillManager()
            mgr.skills_dir = Path(tmpdir)
            err = mgr.remove("no-such-skill")
            assert err is not None
            assert "not found" in err


class TestMultiPathDiscovery:
    """Verify .agents/skills/ and builtin_skills/ are in the search path."""

    def test_search_dirs_includes_agents(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            agents_skills = root / ".agents" / "skills"
            agents_skills.mkdir(parents=True)

            loader = SkillLoader(workspace_root=root)
            dirs = loader._get_search_dirs()

            assert any(source == "agents" for source, _ in dirs)
            assert any(path == agents_skills for _, path in dirs)

    def test_search_dirs_includes_builtin(self):
        from onecode.skills.loader import BUILTIN_SKILLS_DIR
        loader = SkillLoader()
        dirs = loader._get_search_dirs()
        assert any(source == "builtin" for source, _ in dirs)
        assert any(path == BUILTIN_SKILLS_DIR for _, path in dirs)

    def test_agents_skills_discovered(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skill_dir = root / ".agents" / "skills" / "test-agent-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: test-agent-skill\ndescription: An agent skill\n---\n\n# Test\n"
            )
            (skill_dir / "skill.yaml").write_text(
                yaml.dump({"name": "test-agent-skill", "description": "An agent skill"})
            )

            loader = SkillLoader(workspace_root=root)
            loader.invalidate_cache()
            skills = loader.get_all()

            assert "test-agent-skill" in skills
            assert skills["test-agent-skill"].description == "An agent skill"

    def test_cloudbase_found_via_builtin(self):
        from onecode.skills.loader import BUILTIN_SKILLS_DIR
        assert BUILTIN_SKILLS_DIR.exists()
        cloudbase_dir = BUILTIN_SKILLS_DIR / "cloudbase"
        assert cloudbase_dir.is_dir()
        assert (cloudbase_dir / "skill.yaml").exists()
        assert (cloudbase_dir / "SKILL.md").exists()

        loader = SkillLoader()
        loader._get_search_dirs = lambda: [("builtin", BUILTIN_SKILLS_DIR)]
        loader.invalidate_cache()
        skills = loader.get_all()
        assert "cloudbase" in skills, \
            "cloudbase should be discoverable via builtin_skills path"
        assert skills["cloudbase"].path == cloudbase_dir

    def test_user_skill_overrides_agents_skill(self):
        """同名技能：用户技能优先于 .agents/skills/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            user_skills = Path(tmpdir) / "user-skills" / "overlap"
            user_skills.mkdir(parents=True)
            (user_skills / "SKILL.md").write_text(
                "---\nname: overlap\ndescription: User version\n---\n\nUser\n"
            )
            (user_skills / "skill.yaml").write_text(
                yaml.dump({"name": "overlap", "description": "User version"})
            )

            agents_skills = root / ".agents" / "skills" / "overlap"
            agents_skills.mkdir(parents=True)
            (agents_skills / "SKILL.md").write_text(
                "---\nname: overlap\ndescription: Agent version\n---\n\nAgent\n"
            )
            (agents_skills / "skill.yaml").write_text(
                yaml.dump({"name": "overlap", "description": "Agent version"})
            )

            loader = SkillLoader(workspace_root=root)
            loader._get_search_dirs = lambda: [
                ("onecode", Path(tmpdir) / "user-skills"),
                ("agents", root / ".agents" / "skills"),
            ]
            loader.invalidate_cache()
            skills = loader.get_all()

            assert "overlap" in skills
            assert skills["overlap"].description == "User version"

    def test_agents_skill_overrides_builtin(self):
        """.agents/skills/ 同名技能覆盖内置技能."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            agents_skills = root / ".agents" / "skills" / "git"
            agents_skills.mkdir(parents=True)
            (agents_skills / "SKILL.md").write_text(
                "---\nname: git\ndescription: Custom git from .agents\n---\n\nCustom\n"
            )
            (agents_skills / "skill.yaml").write_text(
                yaml.dump({"name": "git", "description": "Custom git from .agents"})
            )

            from onecode.skills.loader import BUILTIN_SKILLS_DIR

            loader = SkillLoader(workspace_root=root)
            loader._get_search_dirs = lambda: [
                ("agents", root / ".agents" / "skills"),
                ("builtin", BUILTIN_SKILLS_DIR),
            ]
            loader.invalidate_cache()
            skills = loader.get_all()

            assert "git" in skills
            assert skills["git"].description == "Custom git from .agents"


class TestBuiltinSkills:
    """Verify builtin skill files exist and are well-formed."""

    def test_skill_creator_exists(self):
        builtin = (
            Path(__file__).resolve().parent.parent
            / "onecode" / "builtin_skills" / "skill-creator"
        )
        assert builtin.is_dir()
        assert (builtin / "skill.yaml").exists()
        assert (builtin / "SKILL.md").exists()

    def test_agent_browser_exists(self):
        builtin = (
            Path(__file__).resolve().parent.parent
            / "onecode" / "builtin_skills" / "agent-browser"
        )
        assert builtin.is_dir()
        assert (builtin / "skill.yaml").exists()
        assert (builtin / "SKILL.md").exists()

    def test_git_exists(self):
        builtin = (
            Path(__file__).resolve().parent.parent
            / "onecode" / "builtin_skills" / "git"
        )
        assert builtin.is_dir()
        assert (builtin / "skill.yaml").exists()
        assert (builtin / "SKILL.md").exists()

    def test_shell_exists(self):
        builtin = (
            Path(__file__).resolve().parent.parent
            / "onecode" / "builtin_skills" / "shell"
        )
        assert builtin.is_dir()
        assert (builtin / "skill.yaml").exists()
        assert (builtin / "SKILL.md").exists()

    def test_all_builtin_skills_have_valid_metadata(self):
        builtin_root = (
            Path(__file__).resolve().parent.parent
            / "onecode" / "builtin_skills"
        )
        for d in sorted(builtin_root.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            skill_yaml = d / "skill.yaml"
            assert skill_yaml.exists(), f"{d.name} missing skill.yaml"
            data = yaml.safe_load(skill_yaml.read_text())
            assert "name" in data, f"{d.name} skill.yaml missing name"
            valid, err = Skill.validate_name(data["name"])
            assert valid, f"{d.name}: {err}"
            assert (d / "SKILL.md").exists(), f"{d.name} missing SKILL.md"
