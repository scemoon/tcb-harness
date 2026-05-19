from __future__ import annotations

import os
import subprocess
from enum import Enum
from pathlib import Path
from typing import Optional, Literal


class Permission(Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class FileOps:
    def __init__(self, workspace: Optional[Path] = None):
        self.workspace = workspace or Path.cwd()

    def read(self, path: str, offset: int = 0, limit: int = 0) -> str:
        p = self._resolve(path)
        if not p.exists():
            return f"File not found: {path}"
        try:
            content = p.read_text(encoding="utf-8")
            lines = content.split("\n")
            if limit > 0:
                lines = lines[offset:offset + limit]
            elif offset > 0:
                lines = lines[offset:]
            return "\n".join(lines)
        except Exception as e:
            return f"Error reading {path}: {e}"

    def write(self, path: str, content: str) -> dict:
        p = self._resolve(path)
        if not self._is_within_workspace(p):
            return {"success": False, "error": "Path outside workspace"}
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return {"success": True, "path": str(p)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def edit(self, path: str, old: str, new: str) -> dict:
        p = self._resolve(path)
        if not p.exists():
            return {"success": False, "error": "File not found"}
        try:
            content = p.read_text(encoding="utf-8")
            if old not in content:
                return {"success": False, "error": "String not found in file"}
            content = content.replace(old, new, 1)
            p.write_text(content, encoding="utf-8")
            return {"success": True, "path": str(p)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def glob(self, pattern: str, path: Optional[str] = None) -> list[str]:
        base = self._resolve(path) if path else self.workspace
        try:
            matches = list(base.glob(pattern))
            return sorted([str(m.relative_to(base)) for m in matches])
        except Exception:
            return []

    def grep(self, pattern: str, include: Optional[str] = None, path: Optional[str] = None) -> list[str]:
        base = self._resolve(path) if path else self.workspace
        cmd = ["grep", "-rn", pattern, str(base)]
        if include:
            cmd.extend(["--include", include])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.stdout.split("\n")
        except Exception:
            return []

    def list(self, path: str = ".") -> list[dict]:
        p = self._resolve(path)
        if not p.exists():
            return [{"error": "Path not found"}]
        if p.is_file():
            return [{"name": p.name, "type": "file", "size": p.stat().st_size}]
        items = []
        for child in p.iterdir():
            items.append({
                "name": child.name,
                "type": "dir" if child.is_dir() else "file",
                "size": child.stat().st_size if child.is_file() else 0
            })
        return sorted(items, key=lambda x: x["name"])

    def _resolve(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = self.workspace / p
        return p

    def _is_within_workspace(self, p: Path) -> bool:
        return str(p).startswith(str(self.workspace))


from cdh.agent.permissions import PermissionChecker, PermissionSet, create_safe_permission_set


class ShellTool:
    def __init__(
        self,
        workspace: Optional[Path] = None,
        permission: Permission = Permission.ALLOW,
        permission_set: Optional[PermissionSet] = None,
    ):
        self.workspace = workspace or Path.cwd()
        self.permission = permission
        self._checker = PermissionChecker(permission_set or create_safe_permission_set())

    def exec(self, cmd: str, cwd: Optional[str] = None, timeout: int = 60) -> dict:
        if self.permission == Permission.DENY:
            return {"success": False, "error": "Shell denied", "requires_approval": False}

        if self.permission == Permission.ASK:
            result = self._checker.check_command(cmd)
            if result.value == "deny":
                return {"success": False, "error": "Command not allowed", "requires_approval": False}
            if result.value == "ask":
                return {"success": False, "error": "Command requires approval", "requires_approval": True}
            return {"success": False, "error": "Shell requires approval", "requires_approval": True}

        result = self._checker.check_command(cmd)
        if result.value == "deny":
            return {"success": False, "error": "Command not allowed", "requires_approval": False}
        if result.value == "ask":
            return {"success": False, "error": "Command requires approval", "requires_approval": True}

        try:
            work_dir = Path(cwd) if cwd else self.workspace
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(work_dir),
                timeout=timeout
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ToolFactory:
    @staticmethod
    def create_file_ops(workspace: Optional[Path] = None) -> FileOps:
        return FileOps(workspace)

    @staticmethod
    def create_shell(workspace: Optional[Path] = None, permission: Permission = Permission.ALLOW) -> ShellTool:
        return ShellTool(workspace, permission)