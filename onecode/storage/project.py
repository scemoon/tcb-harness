from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml


class ProjectConfig:
    def __init__(self, root: Path):
        self.root = root
        self.config_path = root / "cdh.project.yaml"
        self._data: dict = {}
        if self.config_path.exists():
            self._data = yaml.safe_load(self.config_path.read_text()) or {}

    def save(self):
        self.config_path.write_text(yaml.dump(self._data, default_flow_style=False))

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value

    @staticmethod
    def create(name: str, path: Optional[Path] = None) -> ProjectConfig:
        if path is None:
            path = Path.cwd() / name
        path.mkdir(parents=True, exist_ok=True)
        config = ProjectConfig(path)
        config._data = {"name": name, "version": "0.1.0"}
        config.save()
        return config

    def tree(self, depth: int = 3) -> str:
        lines = []
        self._render_tree(self.root, "", depth, lines)
        return "\n".join(lines)

    def _render_tree(self, path: Path, prefix: str, depth: int, lines: list):
        if depth < 0:
            return
        entries = sorted(
            [e for e in path.iterdir() if not e.name.startswith(".") and e.name != "__pycache__"],
            key=lambda e: (not e.is_dir(), e.name),
        )
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")
            if entry.is_dir():
                ext = "    " if is_last else "│   "
                self._render_tree(entry, prefix + ext, depth - 1, lines)
