from __future__ import annotations

import re
from typing import Any

from onecode.agent.tools.file_ops import FileOps
from onecode.agent.tools.protocol import ToolResult
from onecode.agent.tools.registry import Tool, ToolSpec


class ApplyPatchTool(Tool):
    def __init__(self, file_ops: FileOps):
        self._file_ops = file_ops

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="ApplyPatch",
            description="Apply a patch to files. Supports creating, updating, moving, and deleting files via patch format.",
            input_schema={
                "type": "object",
                "properties": {
                    "patch": {
                        "type": "string",
                        "description": "Patch content with marker lines:\n"
                                      "*** Add File: <path>\n"
                                      "*** Update File: <path>\n"
                                      "*** Move to: <path>\n"
                                      "*** Delete File: <path>",
                    },
                },
                "required": ["patch"],
            },
            is_destructive=True,
            max_result_size_chars=50_000,
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        patch = tool_input.get("patch", "")
        if not patch:
            return ToolResult(name="ApplyPatch", output={"error": "patch is required"}, is_error=True)

        results = []
        current_file: str | None = None
        current_content: list[str] = []
        patch_type = "update"

        lines = patch.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].rstrip()

            add_match = re.match(r"^\*\*\*\s*Add File:\s*(.+)$", line)
            update_match = re.match(r"^\*\*\*\s*Update File:\s*(.+)$", line)
            move_match = re.match(r"^\*\*\*\s*Move to:\s*(.+)$", line)
            delete_match = re.match(r"^\*\*\*\s*Delete File:\s*(.+)$", line)

            if add_match:
                if current_file and current_content:
                    result = self._write_file(current_file, "\n".join(current_content))
                    results.append(result)
                current_file = add_match.group(1).strip()
                current_content = []
                patch_type = "add"

            elif update_match:
                if current_file and current_content:
                    result = self._write_file(current_file, "\n".join(current_content))
                    results.append(result)
                current_file = update_match.group(1).strip()
                current_content = []
                patch_type = "update"

            elif move_match:
                target = move_match.group(1).strip()
                if current_file:
                    result = self._move_file(current_file, target)
                    results.append(result)
                    current_file = target
                patch_type = "move"

            elif delete_match:
                target = delete_match.group(1).strip()
                result = self._delete_file(target)
                results.append(result)
                current_file = None
                current_content = []
                patch_type = "delete"

            else:
                if current_file is not None:
                    current_content.append(line)

            i += 1

        if current_file and current_content:
            result = self._write_file(current_file, "\n".join(current_content))
            results.append(result)

        if not results:
            return ToolResult(name="ApplyPatch", output={"error": "No patches applied"}, is_error=True)

        success_count = sum(1 for r in results if r.get("success"))
        return ToolResult(
            name="ApplyPatch",
            output={"applied": len(results), "success": success_count, "results": results},
            is_error=False,
        )

    def _write_file(self, path: str, content: str) -> dict:
        return self._file_ops.write(path, content)

    def _move_file(self, src: str, dst: str) -> dict:
        p_src = self._file_ops._resolve(src)
        p_dst = self._file_ops._resolve(dst)

        if not p_src.exists():
            return {"success": False, "error": f"Source file not found: {src}"}

        if not self._file_ops._is_within_workspace(p_dst):
            return {"success": False, "error": "Path outside workspace"}

        try:
            p_dst.parent.mkdir(parents=True, exist_ok=True)
            p_src.rename(p_dst)
            return {"success": True, "operation": "move", "from": src, "to": dst}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _delete_file(self, path: str) -> dict:
        p = self._file_ops._resolve(path)

        if not p.exists():
            return {"success": False, "error": f"File not found: {path}"}

        if not self._file_ops._is_within_workspace(p):
            return {"success": False, "error": "Path outside workspace"}

        try:
            p.unlink()
            return {"success": True, "operation": "delete", "path": path}
        except Exception as e:
            return {"success": False, "error": str(e)}

