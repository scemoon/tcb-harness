from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import yaml

from cdha.skills.frontmatter import parse_frontmatter
from cdha.skills.model import Skill

from cdha.config import CLOUD_DEV_HARNESS_DIR


USER_SKILLS_DIR = CLOUD_DEV_HARNESS_DIR / "skills"


SKILL_LOCATIONS = [
    ("user", USER_SKILLS_DIR),
    (".opencode", ".opencode/skills"),
    (".claude", ".claude/skills"),
    (".agents", ".agents/skills"),
]


class SkillLoader:
    def __init__(self, workspace_root: Path | None = None):
        self._workspace_root = workspace_root or Path.cwd()
        self._cache: dict[str, Skill] | None = None

    def _get_search_dirs(self) -> list[tuple[str, Path]]:
        dirs = []
        if USER_SKILLS_DIR.exists():
            dirs.append(("user", USER_SKILLS_DIR))

        search_paths = [
            (".opencode", ".claude", ".agents"),
        ]
        for group in search_paths:
            for name in group:
                pattern = f"{name}/skills"
                for parent in self._walk_up_parents():
                    candidate = parent / pattern
                    if candidate.exists():
                        dirs.append((f"{name}/skills", candidate))
                        break

        return dirs

    def _walk_up_parents(self):
        current = self._workspace_root.resolve()
        yield current
        try:
            git_root = next(
                (p for p in current.parents if (p / ".git").exists() or (p / ".hg").exists()),
                None,
            )
            if git_root:
                yield git_root
        except StopIteration:
            pass
        yield Path.home()

    def _discover(self) -> dict[str, Skill]:
        if self._cache is not None:
            return self._cache

        skills: dict[str, Skill] = {}
        seen_names: set[str] = set()

        for source, skills_dir in self._get_search_dirs():
            if not skills_dir.exists():
                continue
            try:
                for d in sorted(skills_dir.iterdir()):
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

                    valid, err = Skill.validate_name(name)
                    if not valid:
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

                    if name not in seen_names:
                        skills[name] = skill
                        seen_names.add(name)

            except Exception:
                continue

        self._cache = skills
        return skills

    def get_all(self) -> dict[str, Skill]:
        return self._discover()

    def get(self, name: str) -> Optional[Skill]:
        return self._discover().get(name.lower())

    def get_enabled(self) -> list[Skill]:
        return [s for s in self._discover().values() if s.enabled]

    def get_by_source(self, source_prefix: str) -> list[Skill]:
        return [
            s for s in self._discover().values()
            if s.path and str(s.path).startswith(source_prefix)
        ]

    def invalidate_cache(self) -> None:
        self._cache = None
