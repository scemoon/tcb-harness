from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from cdha.agent.tools.file_ops import ShellTool
from cdha.agent.tools.permissions import PermissionResult, ToolPermissionContext
from cdha.agent.tools.protocol import ToolResult
from cdha.agent.tools.registry import ToolSpec


_DANGEROUS_PATTERNS = [
    re.compile(r"\bsudo\b", re.IGNORECASE),
    re.compile(r"\bshutdown\b", re.IGNORECASE),
    re.compile(r"\breboot\b", re.IGNORECASE),
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r"\bdd\b\s+if=", re.IGNORECASE),
    re.compile(r"\brm\b.*\s+-rf\s+/\s*$", re.IGNORECASE),
    re.compile(r"\brm\b.*\s+-rf\s+/\s+"),
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", re.IGNORECASE),
]


class BashTool:
    def __init__(self, shell: ShellTool):
        self._shell = shell

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="Bash",
            description="Execute a shell command and return stdout/stderr.",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60},
                },
                "required": ["command"],
            },
            is_destructive=True,
            max_result_size_chars=50_000,
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        command = tool_input.get("command", "")
        timeout = tool_input.get("timeout", 60)

        if not isinstance(command, str) or not command.strip():
            return ToolResult(name="Bash", output="command must be a non-empty string", is_error=True, content_type="text")
        if "\x00" in command:
            return ToolResult(name="Bash", output="command contains NUL byte", is_error=True, content_type="text")

        for pat in _DANGEROUS_PATTERNS:
            if pat.search(command):
                return ToolResult(name="Bash", output="refusing to run potentially dangerous command", is_error=True, content_type="text")

        result = self._shell.exec(command, timeout=timeout)
        is_error = not result.get("success", True)
        stdout = result.get("stdout", "") or ""
        stderr = result.get("stderr", "") or ""
        error_msg = result.get("error", "") or ""

        formatted = self._format_bash_output(stdout, stderr, error_msg, is_error)
        return ToolResult(
            name="Bash",
            output=formatted,
            is_error=is_error,
            content_type="text",
            tool_use_id=tool_input.get("tool_use_id"),
        )

    @staticmethod
    def _format_bash_output(stdout: str, stderr: str, error: str, is_error: bool) -> str:
        """Format shell stdout / stderr as a single text block for the TUI.

        Stderr is rendered first when present so failures are visible,
        the underlying ``error`` string is included for non-zero exits /
        transport failures, and both streams are fenced so the TUI
        renders them as code blocks.
        """
        parts: list[str] = []
        if error.strip():
            parts.append(f"[error] {error.strip()}")
        if stderr.strip():
            parts.append(f"```\n[stderr]\n{stderr.rstrip()}\n```")
        if stdout.strip():
            parts.append(f"```\n{stdout.rstrip()}\n```")
        if not parts:
            return "(no output)" if not is_error else "(failed with no output)"
        return "\n\n".join(parts)

    def check_permissions(
        self,
        tool_input: dict[str, Any],
        permission_context: ToolPermissionContext,
    ) -> PermissionResult:
        return PermissionResult.ALLOW
