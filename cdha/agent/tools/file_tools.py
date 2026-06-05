from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from cdha.agent.tools.file_ops import FileOps, Permission
from cdha.agent.tools.permissions import PermissionResult, ToolPermissionContext
from cdha.agent.tools.protocol import ToolResult
from cdha.agent.tools.registry import ToolSpec


class ReadTool:
    def __init__(self, file_ops: FileOps):
        self._file_ops = file_ops

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="Read",
            description="Read file contents with optional line range. Returns content with line numbers.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to workspace"},
                    "offset": {"type": "integer", "description": "Starting line offset (0-based)", "default": 0},
                    "limit": {"type": "integer", "description": "Max lines to read (0 = all)", "default": 0},
                },
                "required": ["path"],
            },
            is_read_only=True,
            max_result_size_chars=200_000,
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        path = tool_input.get("path", "")
        offset = tool_input.get("offset", 0)
        limit = tool_input.get("limit", 0)
        content = self._file_ops.read(path, offset, limit)
        is_error = str(content).startswith("Error") or str(content).startswith("File not found")
        return ToolResult(name="Read", output=str(content), is_error=is_error)

    def check_permissions(
        self,
        tool_input: dict[str, Any],
        permission_context: ToolPermissionContext,
    ) -> PermissionResult:
        return PermissionResult.ALLOW


class WriteTool:
    def __init__(self, file_ops: FileOps):
        self._file_ops = file_ops

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="Write",
            description="Create or overwrite a file with content.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to workspace"},
                    "content": {"type": "string", "description": "Full file content to write"},
                },
                "required": ["path", "content"],
            },
            is_destructive=True,
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        path = tool_input.get("path", "")
        content = tool_input.get("content", "")
        result = self._file_ops.write(path, content)
        return ToolResult(name="Write", output=result, is_error=not result.get("success", True))

    def check_permissions(
        self,
        tool_input: dict[str, Any],
        permission_context: ToolPermissionContext,
    ) -> PermissionResult:
        return PermissionResult.ALLOW


class EditTool:
    def __init__(self, file_ops: FileOps):
        self._file_ops = file_ops

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="Edit",
            description="Replace exact string in file. old_string MUST be unique — provide enough context.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to workspace"},
                    "old_string": {"type": "string", "description": "Exact text to replace — must be unique"},
                    "new_string": {"type": "string", "description": "Replacement text"},
                },
                "required": ["path", "old_string", "new_string"],
            },
            is_destructive=True,
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        path = tool_input.get("path", "")
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        result = self._file_ops.edit(path, old, new)
        return ToolResult(name="Edit", output=result, is_error=not result.get("success", True))

    def check_permissions(
        self,
        tool_input: dict[str, Any],
        permission_context: ToolPermissionContext,
    ) -> PermissionResult:
        return PermissionResult.ALLOW


class InsertTool:
    def __init__(self, file_ops: FileOps):
        self._file_ops = file_ops

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="Insert",
            description="Insert text at a specific line. line=-1 for beginning.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to workspace"},
                    "line": {"type": "integer", "description": "Line number to insert after (-1 for beginning)"},
                    "text": {"type": "string", "description": "Text to insert"},
                },
                "required": ["path", "line", "text"],
            },
            is_destructive=True,
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        path = tool_input.get("path", "")
        line = tool_input.get("line", -1)
        text = tool_input.get("text", "")
        result = self._file_ops.insert(path, line, text)
        return ToolResult(name="Insert", output=result, is_error=not result.get("success", True))

    def check_permissions(
        self,
        tool_input: dict[str, Any],
        permission_context: ToolPermissionContext,
    ) -> PermissionResult:
        return PermissionResult.ALLOW


class UndoEditTool:
    def __init__(self, file_ops: FileOps):
        self._file_ops = file_ops

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="UndoEdit",
            description="Undo the most recent Edit/Insert operation on a file.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to undo last edit on"},
                },
                "required": ["path"],
            },
            is_destructive=True,
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        path = tool_input.get("path", "")
        result = self._file_ops.undo_edit(path)
        return ToolResult(name="UndoEdit", output=result, is_error=not result.get("success", True))

    def check_permissions(
        self,
        tool_input: dict[str, Any],
        permission_context: ToolPermissionContext,
    ) -> PermissionResult:
        return PermissionResult.ALLOW


class GlobTool:
    def __init__(self, file_ops: FileOps):
        self._file_ops = file_ops

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="Glob",
            description="Find files matching a glob pattern (e.g. **/*.py).",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern to match"},
                },
                "required": ["pattern"],
            },
            is_read_only=True,
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        pattern = tool_input.get("pattern", "")
        result = self._file_ops.glob(pattern)
        return ToolResult(name="Glob", output=str(result))

    def check_permissions(
        self,
        tool_input: dict[str, Any],
        permission_context: ToolPermissionContext,
    ) -> PermissionResult:
        return PermissionResult.ALLOW


class GrepTool:
    def __init__(self, file_ops: FileOps):
        self._file_ops = file_ops

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="Grep",
            description="Search for regex pattern in files.",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search"},
                    "include": {"type": "string", "description": "File pattern to filter (e.g. *.py)"},
                },
                "required": ["pattern"],
            },
            is_read_only=True,
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        pattern = tool_input.get("pattern", "")
        include = tool_input.get("include")
        result = self._file_ops.grep(pattern, include)
        return ToolResult(name="Grep", output=str(result))

    def check_permissions(
        self,
        tool_input: dict[str, Any],
        permission_context: ToolPermissionContext,
    ) -> PermissionResult:
        return PermissionResult.ALLOW


class ListTool:
    def __init__(self, file_ops: FileOps):
        self._file_ops = file_ops

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="List",
            description="List directory contents.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path", "default": "."},
                },
                "required": [],
            },
            is_read_only=True,
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        path = tool_input.get("path", ".")
        result = self._file_ops.list(path)
        return ToolResult(name="List", output=str(result))

    def check_permissions(
        self,
        tool_input: dict[str, Any],
        permission_context: ToolPermissionContext,
    ) -> PermissionResult:
        return PermissionResult.ALLOW
