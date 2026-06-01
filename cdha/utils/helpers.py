from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


def expand_path(path: str, base: Optional[Path] = None) -> Path:
    path = Path(path).expanduser()
    if not path.is_absolute() and base:
        path = base / path
    return path.resolve()


def sanitize_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name).lower()


def truncate(text: str, max_len: int = 100) -> str:
    return text[:max_len] + "..." if len(text) > max_len else text
