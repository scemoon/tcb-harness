from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from cdh.agent.tools.protocol import ToolResult
from cdh.agent.tools.registry import ToolSpec


class WorktreeTool:
    """Manage git worktrees (Clawd-Code pattern)."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="Worktree",
            description="Manage git worktrees: create, list, prune. Worktrees allow checking out multiple branches simultaneously.",
            input_schema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "add", "prune"],
                        "description": "List worktrees, add a new worktree, or prune stale ones",
                    },
                    "path": {"type": "string", "description": "Path for the new worktree (required for add)"},
                    "branch": {"type": "string", "description": "Branch to checkout (default: new branch named after path)"},
                    "commitish": {"type": "string", "description": "Commit, tag, or branch to base the worktree on"},
                },
                "required": ["action"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        action = tool_input.get("action", "list")
        try:
            if action == "list":
                result = subprocess.run(
                    ["git", "worktree", "list"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    return ToolResult(name="Worktree", output={"error": result.stderr.strip()}, is_error=True)
                worktrees = []
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parts = line.split()
                        worktrees.append({"path": parts[0], "branch": parts[1] if len(parts) > 1 else ""})
                return ToolResult(name="Worktree", output={"worktrees": worktrees})

            elif action == "add":
                wt_path = tool_input.get("path", "")
                if not wt_path:
                    return ToolResult(name="Worktree", output={"error": "path required for add"}, is_error=True)
                branch = tool_input.get("branch")
                commitish = tool_input.get("commitish")
                cmd = ["git", "worktree", "add", wt_path]
                if branch:
                    cmd.extend(["-b", branch])
                if commitish:
                    cmd.append(commitish)
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode != 0:
                    return ToolResult(name="Worktree", output={"error": result.stderr.strip()}, is_error=True)
                return ToolResult(name="Worktree", output={"path": wt_path, "status": "created", "output": result.stdout.strip()})

            elif action == "prune":
                result = subprocess.run(
                    ["git", "worktree", "prune"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    return ToolResult(name="Worktree", output={"error": result.stderr.strip()}, is_error=True)
                return ToolResult(name="Worktree", output={"status": "pruned"})

            return ToolResult(name="Worktree", output={"error": f"unknown action: {action}"}, is_error=True)
        except subprocess.TimeoutExpired:
            return ToolResult(name="Worktree", output={"error": "git worktree command timed out"}, is_error=True)
        except FileNotFoundError:
            return ToolResult(name="Worktree", output={"error": "git not found"}, is_error=True)
        except Exception as e:
            return ToolResult(name="Worktree", output={"error": str(e)}, is_error=True)
