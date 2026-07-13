from __future__ import annotations

from pathlib import Path

import yaml


ACTIVE_PROJECT_PATH = Path.home() / ".cdh" / "active_project.yaml"


def read_active_project() -> dict | None:
    if not ACTIVE_PROJECT_PATH.exists():
        return None
    try:
        return yaml.safe_load(ACTIVE_PROJECT_PATH.read_text(encoding="utf-8")) or None
    except Exception:
        return None


def write_active_project(name: str, path: str) -> None:
    ACTIVE_PROJECT_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {"name": name, "path": path}
    ACTIVE_PROJECT_PATH.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")


def clear_active_project() -> None:
    if ACTIVE_PROJECT_PATH.exists():
        ACTIVE_PROJECT_PATH.unlink()
