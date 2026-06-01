from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from cdha.skills.frontmatter import parse_frontmatter
from cdha.skills.model import Skill

from cdha.config import CLOUD_DEV_HARNESS_DIR


USER_SKILLS_DIR = CLOUD_DEV_HARNESS_DIR / "skills"


class SkillLoader:
    """Discovers skills from multiple directories (Clawd-Code pattern).

    Searches:
      1. User skills: ~/.cdh/skills/<name>/
      2. Workspace skills: <workspace>/skills/<name>/
    """

    def __init__(self, workspace_skills_dir: Path | None = None):
        self._workspace_skills_dir = workspace_skills_dir
        self._cache: dict[str, Skill] | None = None

    def _get_search_dirs(self) -> list[Path]:
        dirs = []
        if USER_SKILLS_DIR.exists():
            dirs.append(USER_SKILLS_DIR)
        if self._workspace_skills_dir and self._workspace_skills_dir.exists():
            dirs.append(self._workspace_skills_dir)
        return dirs

    def _discover(self) -> dict[str, Skill]:
        if self._cache is not None:
            return self._cache

        skills: dict[str, Skill] = {}
        for skills_dir in self._get_search_dirs():
            for d in sorted(skills_dir.iterdir()):
                if not d.is_dir():
                    continue
                skill_md = d / "SKILL.md"
                skill_yaml = d / "skill.yaml"
                if not skill_md.exists():
                    continue

                content = skill_md.read_text(encoding="utf-8")
                cfg = {}
                if skill_yaml.exists():
                    try:
                        cfg = yaml.safe_load(skill_yaml.read_text(encoding="utf-8")) or {}
                    except Exception:
                        cfg = {}

                # Parse inline frontmatter from SKILL.md (overrides skill.yaml)
                frontmatter, body = parse_frontmatter(content)

                name = frontmatter.get("name") or cfg.get("name") or d.name
                skill = Skill(
                    name=name,
                    description=frontmatter.get("description") or cfg.get("description", ""),
                    path=d,
                    enabled=frontmatter.get("enabled", cfg.get("enabled", True)),
                    allowed_tools=frontmatter.get("allowed_tools") or cfg.get("allowed_tools", []),
                    arguments=frontmatter.get("arguments") or cfg.get("arguments", []),
                    triggers=frontmatter.get("triggers") or cfg.get("triggers", []),
                    phases=frontmatter.get("phases") or cfg.get("phases", []),
                    content=body if body else content,
                )
                skills[name] = skill

        self._cache = skills
        return skills

    def get_all(self) -> dict[str, Skill]:
        return self._discover()

    def get(self, name: str) -> Optional[Skill]:
        return self._discover().get(name)

    def get_enabled(self) -> list[Skill]:
        return [s for s in self._discover().values() if s.enabled]

    def invalidate_cache(self) -> None:
        self._cache = None
