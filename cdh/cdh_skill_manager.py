"""cdh platform skill manager — operates ~/.cdh/skills/<name>/.

This is the cdh platform equivalent of onecode.skills.manager.SkillManager,
but operates strictly on ~/.cdh/skills/ (cdh platform shared pool).
Engines (onecode/opencode/claude) do NOT read this directory directly;
cdh injects platform skills into engines at runtime via prompt or env var.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

import yaml


CDH_PLATFORM_SKILLS_DIR = Path.home() / ".cdh" / "skills"


class CdhSkillManager:
    def __init__(self, skills_dir: Path | None = None):
        self.skills_dir = skills_dir or CDH_PLATFORM_SKILLS_DIR
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._skills: dict[str, dict] = {}

    def install(self, path: Path) -> Optional[str]:
        """Install a skill from source path into the cdh platform skill pool.

        Copies the entire skill directory to ~/.cdh/skills/<name>/,
        and writes .installed_version with the source's metadata.version.
        Returns error message or None on success.
        """
        skill_yaml = path / "skill.yaml"
        if not skill_yaml.exists():
            return "skill.yaml not found in source"

        data = yaml.safe_load(skill_yaml.read_text())
        name = data.get("name", path.name)
        target = self.skills_dir / name
        target.mkdir(parents=True, exist_ok=True)

        for src in path.iterdir():
            if src.name.startswith("."):
                continue
            dst = target / src.name
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)

        # Write version marker
        version = data.get("metadata", {}).get("version", "4.0.0")
        version_file = target / ".installed_version"
        version_file.write_text(version + "\n", encoding="utf-8")

        self._skills[name] = data
        return None

    def list(self) -> list[dict]:
        result = []
        for d in self.skills_dir.iterdir():
            if d.is_dir():
                config_path = d / "skill.yaml"
                if config_path.exists():
                    data = yaml.safe_load(config_path.read_text()) or {}
                    data["name"] = data.get("name", d.name)
                    data["enabled"] = data.get("enabled", True)
                    result.append(data)
        return result

    def enable(self, name: str, enabled: bool = True):
        config_path = self.skills_dir / name / "skill.yaml"
        if config_path.exists():
            data = yaml.safe_load(config_path.read_text()) or {}
            data["enabled"] = enabled
            config_path.write_text(yaml.dump(data, default_flow_style=False))

    def get_installed_version(self, name: str) -> Optional[str]:
        version_file = self.skills_dir / name / ".installed_version"
        if version_file.exists():
            return version_file.read_text(encoding="utf-8").strip()
        return None

    def remove(self, name: str) -> Optional[str]:
        skill_path = self.skills_dir / name
        if not skill_path.exists():
            return f"Skill '{name}' not found"
        if not skill_path.is_dir():
            return f"'{name}' is not a skill directory"
        shutil.rmtree(skill_path)
        self._skills.pop(name, None)
        return None

    def get(self, name: str) -> Optional[dict]:
        if name in self._skills:
            return self._skills[name]
        skill_path = self.skills_dir / name / "skill.yaml"
        if skill_path.exists():
            data = yaml.safe_load(skill_path.read_text()) or {}
            data["name"] = data.get("name", name)
            data["enabled"] = data.get("enabled", True)
            self._skills[name] = data
            return data
        return None
