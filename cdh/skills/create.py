from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml


SKILL_TEMPLATE = """---
name: {name}
description: {description}
enabled: true
---

# {name} Skill

## Description
{description}

## Usage
When the user asks about {name}, follow these instructions:

## Guidelines
- Follow the project conventions
- Use appropriate tools
"""


def create_skill_scaffold(
    skills_dir: Path,
    name: str,
    description: str = "",
) -> Optional[str]:
    """Create a new skill directory with SKILL.md and skill.yaml.

    Returns error message or None on success.
    """
    skill_path = skills_dir / name
    if skill_path.exists():
        return f"Skill '{name}' already exists at {skill_path}"

    skill_path.mkdir(parents=True, exist_ok=True)

    skill_md = skill_path / "SKILL.md"
    skill_md.write_text(
        SKILL_TEMPLATE.format(name=name, description=description or f"A skill for {name}"),
        encoding="utf-8",
    )

    skill_yaml = skill_path / "skill.yaml"
    skill_yaml.write_text(
        yaml.dump({"name": name, "description": description, "enabled": True}, default_flow_style=False),
        encoding="utf-8",
    )

    return None
