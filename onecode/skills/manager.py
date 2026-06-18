from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from onecode.config import CLOUD_DEV_HARNESS_DIR


class SkillManager:
    def __init__(self):
        self.skills_dir = CLOUD_DEV_HARNESS_DIR / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._skills: dict[str, dict] = {}

    def install(self, path: Path) -> Optional[str]:
        skill_yaml = path / "skill.yaml"
        if not skill_yaml.exists():
            return "skill.yaml not found"
        data = yaml.safe_load(skill_yaml.read_text())
        name = data.get("name", path.name)
        target = self.skills_dir / name
        target.mkdir(parents=True, exist_ok=True)
        for src in path.iterdir():
            (target / src.name).write_bytes(src.read_bytes())
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

    def remove(self, name: str) -> Optional[str]:
        """Remove a skill by name.

        Returns error message or None on success.
        """
        skill_path = self.skills_dir / name
        if not skill_path.exists():
            return f"Skill '{name}' not found"
        if not skill_path.is_dir():
            return f"'{name}' is not a skill directory"
        import shutil
        shutil.rmtree(skill_path)
        self._skills.pop(name, None)
        return None

    def get(self, name: str) -> Optional[dict]:
        """Get a skill by name."""
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
