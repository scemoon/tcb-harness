"""cdh platform skill loader — reads ~/.cdh/skills/<name>/ and produces Skill objects.

This is the loader counterpart of CdhSkillManager. It discovers skills in
the cdh platform shared pool (~/.cdh/skills/) and makes them available for
injection into any plugged-in engine at runtime.
"""

from __future__ import annotations

import re
from typing import Optional

import yaml

from cdh.cdh_skill_manager import CDH_PLATFORM_SKILLS_DIR

from onecode.skills.model import Skill
from onecode.skills.frontmatter import parse_frontmatter


SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class CdhSkillLoader:
    def __init__(self):
        self._cache: dict[str, Skill] | None = None

    def _discover(self) -> dict[str, Skill]:
        if self._cache is not None:
            return self._cache

        skills: dict[str, Skill] = {}

        if not CDH_PLATFORM_SKILLS_DIR.exists():
            self._cache = skills
            return skills

        try:
            for d in sorted(CDH_PLATFORM_SKILLS_DIR.iterdir()):
                if not d.is_dir():
                    continue
                skill_md = d / "SKILL.md"
                if not skill_md.exists():
                    continue

                content = skill_md.read_text(encoding="utf-8")
                cfg = {}
                skill_yaml = d / "skill.yaml"
                if skill_yaml.exists():
                    try:
                        cfg = yaml.safe_load(skill_yaml.read_text(encoding="utf-8")) or {}
                    except Exception:
                        cfg = {}

                frontmatter, body = parse_frontmatter(content)
                raw_name = frontmatter.get("name") or cfg.get("name") or d.name
                name = raw_name.lower()

                if not SKILL_NAME_RE.match(name):
                    continue

                desc = frontmatter.get("description") or cfg.get("description", "")

                skill = Skill(
                    name=name,
                    description=desc,
                    path=d,
                    enabled=frontmatter.get("enabled", cfg.get("enabled", True)),
                    allowed_tools=frontmatter.get("allowed_tools") or cfg.get("allowed_tools", []),
                    arguments=frontmatter.get("arguments") or cfg.get("arguments", []),
                    triggers=frontmatter.get("triggers") or cfg.get("triggers", []),
                    phases=frontmatter.get("phases") or cfg.get("phases", []),
                    content=body if body else content,
                    license=frontmatter.get("license") or cfg.get("license", ""),
                    compatibility=frontmatter.get("compatibility") or cfg.get("compatibility", ""),
                    metadata=frontmatter.get("metadata") or cfg.get("metadata", {}),
                )

                if name not in skills:
                    skills[name] = skill

        except Exception:
            pass

        self._cache = skills
        return skills

    def get_all(self) -> dict[str, Skill]:
        return self._discover()

    def get(self, name: str) -> Optional[Skill]:
        return self._discover().get(name.lower())

    def get_enabled(self) -> list[Skill]:
        return [s for s in self._discover().values() if s.enabled]

    def invalidate_cache(self) -> None:
        self._cache = None
