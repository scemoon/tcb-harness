from __future__ import annotations

import difflib
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CheckpointManifest:
    id: str
    timestamp: str
    agent: str
    reason: str
    files: list[str]
    tool_call_id: str
    description: str = ""


class CheckpointManager:
    """Manages checkpoints for protecting file state before destructive operations."""

    def __init__(self, workspace_root: Path):
        self._workspace = workspace_root
        self._checkpoints_dir = workspace_root / ".cdh" / "checkpoints"
        self._checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._checkpoints_dir / "index.json"
        self._init_index()

    def _init_index(self) -> None:
        if not self._index_path.exists():
            self._save_index([])

    def _load_index(self) -> list[dict]:
        try:
            return json.loads(self._index_path.read_text("utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_index(self, index: list[dict]) -> None:
        self._index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), "utf-8")

    def create(
        self,
        agent: str,
        reason: str,
        files: list[str],
        tool_call_id: str,
        description: str = "",
    ) -> str:
        """Create a checkpoint, returns checkpoint ID."""
        checkpoint_id = f"ckpt_{int(time.time() * 1000)}"
        checkpoint_dir = self._checkpoints_dir / checkpoint_id
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        manifest = CheckpointManifest(
            id=checkpoint_id,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            agent=agent,
            reason=reason,
            files=files,
            tool_call_id=tool_call_id,
            description=description,
        )

        files_dir = checkpoint_dir / "files"
        files_dir.mkdir()

        for file_path in files:
            full_path = self._workspace / file_path
            if full_path.exists() and full_path.is_file():
                dest = files_dir / file_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(full_path, dest)

        manifest_path = checkpoint_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "id": manifest.id,
                    "timestamp": manifest.timestamp,
                    "agent": manifest.agent,
                    "reason": manifest.reason,
                    "files": manifest.files,
                    "tool_call_id": manifest.tool_call_id,
                    "description": manifest.description,
                },
                indent=2,
                ensure_ascii=False,
            ),
            "utf-8",
        )

        index = self._load_index()
        index.insert(0, {"id": checkpoint_id, "timestamp": manifest.timestamp, "reason": reason})
        self._save_index(index)

        return checkpoint_id

    def restore(self, checkpoint_id: str) -> bool:
        """Restore files from a checkpoint."""
        checkpoint_dir = self._checkpoints_dir / checkpoint_id
        if not checkpoint_dir.exists():
            return False

        manifest_path = checkpoint_dir / "manifest.json"
        if not manifest_path.exists():
            return False

        try:
            manifest = json.loads(manifest_path.read_text("utf-8"))
        except json.JSONDecodeError:
            return False

        files_dir = checkpoint_dir / "files"
        for file_path in manifest.get("files", []):
            src = files_dir / file_path
            if src.exists():
                dest = self._workspace / file_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
            else:
                dest = self._workspace / file_path
                if dest.exists():
                    dest.unlink()

        return True

    def get_diff(self, checkpoint_id: str, file_path: str) -> str:
        """Get diff for a specific file between checkpoint and current state."""
        checkpoint_dir = self._checkpoints_dir / checkpoint_id
        checkpoint_file = checkpoint_dir / "files" / file_path
        current_file = self._workspace / file_path

        if not checkpoint_file.exists():
            if current_file.exists():
                return self._generate_new_file_diff(current_file)
            return ""

        if not current_file.exists():
            return f"File was deleted (checkpoint has content):\n{checkpoint_file.read_text('utf-8')[:500]}"

        old_content = checkpoint_file.read_text("utf-8")
        new_content = current_file.read_text("utf-8")

        if old_content == new_content:
            return ""

        return self._unified_diff(file_path, old_content, new_content)

    def generate_preview_diff(
        self,
        tool_name: str,
        tool_input: dict,
        current_files: list[str],
    ) -> dict[str, str]:
        """Generate diff preview for files that would be modified.

        Returns dict of file_path -> diff string
        """
        diffs = {}

        if tool_name == "Edit":
            path = tool_input.get("path", "")
            old_str = tool_input.get("old_string", "")
            new_str = tool_input.get("new_string", "")
            if path:
                current = (self._workspace / path).read_text("utf-8") if (self._workspace / path).exists() else ""
                diffs[path] = self._unified_diff(path, current, current.replace(old_str, new_str, 1))

        elif tool_name == "Write":
            path = tool_input.get("path", "")
            new_content = tool_input.get("content", "")
            if path:
                current = (self._workspace / path).read_text("utf-8") if (self._workspace / path).exists() else ""
                if current:
                    diffs[path] = self._unified_diff(path, current, new_content)
                else:
                    diffs[path] = f"New file:\n{new_content[:500]}..."

        elif tool_name == "Bash":
            cmd = tool_input.get("command", "")
            for file_path in current_files:
                full_path = self._workspace / file_path
                if full_path.exists():
                    diffs[file_path] = f"Command would execute: {cmd[:100]}"

        return diffs

    def _unified_diff(self, path: str, old: str, new: str) -> str:
        """Generate unified diff format."""
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        diff = difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="")
        result = "".join(diff)
        if not result:
            result = f"No changes in {path}"
        return result

    def _generate_new_file_diff(self, path: Path) -> str:
        content = path.read_text("utf-8")
        return f"New file:\n{content[:500]}..." if len(content) > 500 else f"New file:\n{content}"

    def list(self, limit: int = 10) -> list[dict]:
        """List recent checkpoints."""
        index = self._load_index()
        return index[:limit]

    def cleanup(self, keep_last: int = 10) -> None:
        """Remove old checkpoints, keeping the most recent ones."""
        index = self._load_index()
        if len(index) <= keep_last:
            return

        to_remove = index[keep_last:]
        index = index[:keep_last]
        self._save_index(index)

        for entry in to_remove:
            checkpoint_id = entry.get("id")
            if checkpoint_id:
                shutil.rmtree(self._checkpoints_dir / checkpoint_id, ignore_errors=True)

    def should_checkpoint(self, tool_name: str, tool_input: dict, affected_files: list[str]) -> tuple[bool, str]:
        """Determine if a checkpoint should be created for this operation.

        Returns (should_create, reason)
        """
        if tool_name == "Bash":
            cmd = tool_input.get("command", "")
            if "rm " in cmd or "git reset --hard" in cmd or "git checkout --" in cmd:
                return True, "dangerous_bash"
            if len(affected_files) >= 3:
                return True, "multi_file_bash"

        if tool_name in ("Write", "Edit"):
            if len(affected_files) >= 3:
                return True, "multi_file_edit"

        critical_patterns = (
            "package.json",
            "Cargo.toml",
            "go.mod",
            "requirements.txt",
            "pyproject.toml",
            "Makefile",
            "Dockerfile",
            ".gitignore",
            "config",
        )
        for f in affected_files:
            if any(p in f for p in critical_patterns):
                return True, "critical_file"

        return False, ""


def merge_checkpoints(checkpoint_manager: CheckpointManager, ids: list[str], description: str) -> Optional[str]:
    """Merge multiple checkpoints into one."""
    if not ids:
        return None

    first_dir = checkpoint_manager._checkpoints_dir / ids[0]
    if not first_dir.exists():
        return None

    manifest = json.loads((first_dir / "manifest.json").read_text("utf-8"))
    all_files = set(manifest.get("files", []))

    for ckpt_id in ids[1:]:
        ckpt_dir = checkpoint_manager._checkpoints_dir / ckpt_id
        if ckpt_dir.exists():
            m = json.loads((ckpt_dir / "manifest.json").read_text("utf-8"))
            all_files.update(m.get("files", []))

    return checkpoint_manager.create(
        agent=manifest.get("agent", "unknown"),
        reason="merged",
        files=list(all_files),
        tool_call_id="merge",
        description=description,
    )
