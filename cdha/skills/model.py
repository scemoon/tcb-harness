from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


@dataclass
class Skill:
    name: str
    description: str = ""
    path: Path | None = None
    enabled: bool = True
    allowed_tools: list[str] = field(default_factory=list)
    arguments: list[dict[str, Any]] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    phases: list[str] = field(default_factory=list)
    content: str = ""
    license: str = ""
    compatibility: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    @classmethod
    def validate_name(cls, name: str) -> tuple[bool, str]:
        if not name:
            return False, "name is required"
        if len(name) < 1 or len(name) > 64:
            return False, "name must be 1-64 characters"
        if not SKILL_NAME_RE.match(name):
            return False, "name must be lowercase alphanumeric with single hyphens, cannot start/end with hyphen or have consecutive hyphens"
        return True, ""

    @classmethod
    def validate_description(cls, desc: str) -> tuple[bool, str]:
        if not desc:
            return False, "description is required"
        if len(desc) > 1024:
            return False, "description must be 1-1024 characters"
        return True, ""
