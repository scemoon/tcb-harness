from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
