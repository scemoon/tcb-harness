from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from onecode.agent.permissions import PermissionChecker, PermissionSet, create_safe_permission_set
from onecode.agent.tools.sandbox import Sandbox, SandboxConfig, SandboxMode, ResourceLimits, create_sandbox


class FileOps:
    def __init__(self, workspace: Optional[Path] = None):
        self.workspace = workspace or Path.cwd()
        self._undo_stack: list[dict] = []

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
            count = content.count(old)
            if count > 1:
                return {
                    "success": False,
                    "error": f"old_string matches {count} locations in file. "
                             f"Provide a larger string with more surrounding context to make it unique.",
                }
            self._undo_stack.append({"path": str(p), "content": content})
            content = content.replace(old, new, 1)
            p.write_text(content, encoding="utf-8")
            return {"success": True, "path": str(p)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def insert(self, path: str, line: int, text: str) -> dict:
        p = self._resolve(path)
        if not p.exists():
            return {"success": False, "error": "File not found"}
        try:
            content = p.read_text(encoding="utf-8")
            lines = content.split("\n")
            self._undo_stack.append({"path": str(p), "content": content})
            if line == -1:
                lines.insert(0, text)
            elif line < len(lines):
                lines.insert(line + 1, text)
            else:
                lines.append(text)
            new_content = "\n".join(lines)
            p.write_text(new_content, encoding="utf-8")
            return {"success": True, "path": str(p)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def undo_edit(self, path: str) -> dict:
        p = self._resolve(path)
        if not self._undo_stack:
            return {"success": False, "error": "No edit history to undo"}
        try:
            for i in range(len(self._undo_stack) - 1, -1, -1):
                snapshot = self._undo_stack[i]
                if snapshot["path"] == str(p):
                    p.write_text(snapshot["content"], encoding="utf-8")
                    self._undo_stack.pop(i)
                    return {"success": True, "path": str(p), "message": "Edit undone"}
            return {"success": False, "error": f"No edit history for {path}"}
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
        return p.resolve()

    def _is_within_workspace(self, p: Path) -> bool:
        try:
            p.resolve().relative_to(self.workspace.resolve())
            return True
        except ValueError:
            return False


class ShellTool:
    """Shell execution with safety checks.

    Permission (ALLOW / ASK / DENY) is handled at the engine level via
    ``_check_tool_permission``.  This class only enforces command-level
    safety rules (dangerous patterns, sandboxing).
    """

    def __init__(
        self,
        workspace: Optional[Path] = None,
        permission_set: Optional[PermissionSet] = None,
        sandbox_mode: str = "auto",
    ):
        self.workspace = workspace or Path.cwd()
        self._checker = PermissionChecker(permission_set or create_safe_permission_set())
        self._sandbox = create_sandbox(self.workspace, mode=sandbox_mode)

    def exec(self, cmd: str, cwd: Optional[str] = None, timeout: int = 60) -> dict:
        result = self._checker.check_command(cmd)
        if result.value == "deny":
            return {"success": False, "error": "Command not allowed", "requires_approval": False}
        if result.value == "ask":
            return {"success": False, "error": "Command requires approval", "requires_approval": True}

        work_dir = Path(cwd) if cwd else self.workspace
        if not work_dir.is_relative_to(self.workspace.resolve()):
            return {"success": False, "error": "CWD outside workspace"}

        return self._sandbox.exec(cmd, timeout=timeout)


class ToolFactory:
    @staticmethod
    def create_file_ops(workspace: Optional[Path] = None) -> FileOps:
        return FileOps(workspace)

    @staticmethod
    def create_shell(workspace: Optional[Path] = None) -> ShellTool:
        return ShellTool(workspace)