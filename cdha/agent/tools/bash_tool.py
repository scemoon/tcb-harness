from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from cdha.agent.tools.file_ops import ShellTool
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
            return ToolResult(name="Bash", output={"error": "command must be a non-empty string"}, is_error=True)
        if "\x00" in command:
            return ToolResult(name="Bash", output={"error": "command contains NUL byte"}, is_error=True)

        for pat in _DANGEROUS_PATTERNS:
            if pat.search(command):
                return ToolResult(name="Bash", output={"error": "refusing to run potentially dangerous command"}, is_error=True)

        result = self._shell.exec(command, timeout=timeout)
        return ToolResult(name="Bash", output=result, is_error=not result.get("success", True))
