from __future__ import annotations

import fnmatch
import json
import os
import shutil
import tarfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class SnapshotInfo:
    id: str
    name: str
    timestamp: str
    description: str
    size_bytes: int
    file_count: int


class SnapshotManager:
    def __init__(self, base_path: Optional[Path] = None):
        from onecode.config import ONECODE_DIR
        self.base_path = base_path or (ONECODE_DIR / "snapshots")
        self.base_path.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        workspace: Path,
        name: str,
        description: str = "",
        exclude_patterns: Optional[list[str]] = None,
    ) -> SnapshotInfo:
        snapshot_id = str(uuid.uuid4())[:8]
        snapshot_dir = self.base_path / snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        tar_path = snapshot_dir / "snapshot.tar.gz"
        manifest_path = snapshot_dir / "manifest.json"

        exclude_patterns = exclude_patterns or [
            ".git",
            "node_modules",
            "__pycache__",
            "*.pyc",
            ".pytest_cache",
            ".venv",
            "venv",
            ".env",
            "*.egg-info",
            ".cdh",
            "snapshots",
        ]

        file_count = 0
        with tarfile.open(str(tar_path), "w:gz") as tar:
            for root, dirs, files in os.walk(workspace):
                dirs[:] = [d for d in dirs if not self._should_exclude(d, exclude_patterns)]

                for file in files:
                    file_path = Path(root) / file
                    if not self._should_exclude(file_path.name, exclude_patterns):
                        try:
                            tar.add(str(file_path), arcname=str(file_path.relative_to(workspace)))
                            file_count += 1
                        except Exception:
                            pass

        size_bytes = tar_path.stat().st_size

        manifest = {
            "id": snapshot_id,
            "name": name,
            "description": description,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "workspace": str(workspace),
            "file_count": file_count,
            "size_bytes": size_bytes,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        return SnapshotInfo(
            id=snapshot_id,
            name=name,
            timestamp=manifest["timestamp"],
            description=description,
            size_bytes=size_bytes,
            file_count=file_count,
        )

    def restore(self, snapshot_id: str, target_dir: Path) -> bool:
        snapshot_dir = self.base_path / snapshot_id
        if not snapshot_dir.exists():
            return False

        tar_path = snapshot_dir / "snapshot.tar.gz"
        if not tar_path.exists():
            return False

        target_dir.mkdir(parents=True, exist_ok=True)

        with tarfile.open(str(tar_path), "r:gz") as tar:
            tar.extractall(target_dir)

        return True

    def list(self) -> list[SnapshotInfo]:
        snapshots = []
        for snapshot_dir in self.base_path.iterdir():
            if not snapshot_dir.is_dir():
                continue
            manifest_path = snapshot_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                snapshots.append(SnapshotInfo(
                    id=manifest["id"],
                    name=manifest["name"],
                    timestamp=manifest["timestamp"],
                    description=manifest.get("description", ""),
                    size_bytes=manifest.get("size_bytes", 0),
                    file_count=manifest.get("file_count", 0),
                ))
            except Exception:
                continue
        return sorted(snapshots, key=lambda s: s.timestamp, reverse=True)

    def delete(self, snapshot_id: str) -> bool:
        snapshot_dir = self.base_path / snapshot_id
        if snapshot_dir.exists():
            shutil.rmtree(snapshot_dir)
            return True
        return False

    def _should_exclude(self, name: str, patterns: list[str]) -> bool:
        for pattern in patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
        return False