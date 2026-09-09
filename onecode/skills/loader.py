from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from onecode.skills.frontmatter import parse_frontmatter
from onecode.skills.model import Skill

from onecode.config import ONECODE_DIR


USER_SKILLS_DIR = ONECODE_DIR / "skills"
BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent.parent / "builtin_skills"

ENGINE_SKILL_PATHS = {
    "opencode": Path.home() / ".opencode" / "skills",
    "claude": Path.home() / ".claude" / "skills",
    "onecode": Path.home() / ".onecode" / "skills",
}


class SkillLoader:
    def __init__(self, workspace_root: Path | None = None):
        self._workspace_root = workspace_root or Path.cwd()
        self._cache: dict[str, Skill] | None = None

    def _get_search_dirs(self) -> list[tuple[str, Path]]:
        dirs = []

        if USER_SKILLS_DIR.exists():
            dirs.append(("onecode", USER_SKILLS_DIR))

        for engine, path in ENGINE_SKILL_PATHS.items():
            if path.exists():
                dirs.append((engine, path))

        agents_skills = self._workspace_root / ".agents" / "skills"
        if agents_skills.exists():
            dirs.append(("agents", agents_skills))

        if BUILTIN_SKILLS_DIR.exists():
            dirs.append(("builtin", BUILTIN_SKILLS_DIR))

        return dirs

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

    def search(self, keyword: str) -> list[Skill]:
        kw = keyword.lower()
        results: list[tuple[Skill, int]] = []

        for skill in self._discover().values():
            score = 0
            name_lower = skill.name.lower()
            desc_lower = skill.description.lower()

            if kw == name_lower:
                score += 100
            elif kw in name_lower:
                score += 50
            if kw in desc_lower:
                score += 30
                if desc_lower.startswith(kw):
                    score += 10
            for trigger in skill.triggers:
                if kw in trigger.lower():
                    score += 20
                    break
            for phase in skill.phases:
                if kw in phase.lower():
                    score += 10
                    break

            if score > 0:
                results.append((skill, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in results]

    def invalidate_cache(self) -> None:
        self._cache = None

    # Synonym expansion for trigger matching
    TRIGGER_SYNONYMS = {
        "understand": ["intent", "requirement", "spec", "需求", "需求分析"],
        "plan": ["design", "architecture", "task", "dag", "规划", "设计"],
        "verify": ["test", "tdd", "bdd", "quality", "验证", "测试"],
        "deliver": ["deploy", "release", "production", "交付", "部署"],
        "lifecycle": ["process", "workflow", "phase", "流程", "生命周期"],
        "contract": ["api", "openapi", "asyncapi", "接口", "合约"],
        "cross-stack": ["integration", "e2e", "end-to-end", "跨栈", "集成"],
    }

    def match_intent(self, user_input: str) -> list[Skill]:
        """Match user input against skills using trigger synonyms and fuzzy matching.

        Returns skills ordered by relevance score.
        """
        words = set(user_input.lower().split())
        results: list[tuple[Skill, int]] = []

        for skill in self._discover().values():
            score = 0

            # Direct trigger match
            for trigger in skill.triggers:
                trigger_lower = trigger.lower()
                if trigger_lower in user_input.lower():
                    score += 50
                    if trigger_lower == user_input.lower().strip():
                        score += 30

            # Synonym expansion
            expanded = set(words)
            for phase, synonyms in self.TRIGGER_SYNONYMS.items():
                if phase in [p.lower() for p in skill.phases]:
                    for syn in synonyms:
                        if syn in words:
                            expanded.add(phase)
                            score += 15

            # Component prefix detection (NATIVE-FR, WEB-FR, INT-FR, etc.)
            import re
            fr_pattern = r'\b(NATIVE|DESKTOP|WEB|BE|WXA|MYA|TTA|INT)-FR-\d+'
            if re.search(fr_pattern, user_input, re.IGNORECASE):
                score += 40

            # Phase keyword in user input
            for phase in skill.phases:
                if phase.lower() in user_input.lower():
                    score += 25

            if score > 0:
                results.append((skill, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in results]
