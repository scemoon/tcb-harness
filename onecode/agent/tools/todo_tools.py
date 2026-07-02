from __future__ import annotations

from typing import Any

from onecode.agent.tools.protocol import ToolResult
from onecode.agent.tools.registry import Tool, ToolSpec


class TodoCreateTool(Tool):
    def __init__(self, todo_manager):
        self._tm = todo_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TodoCreate",
            description=(
                "Create a todo (plan item) for tracking progress. ALL tasks — simple "
                "or complex — are created via TodoCreate, persisted to .cdh/todos.json, "
                "and mirrored to the sidebar Plan widget. At execution time, route by "
                "complexity: simple todos are executed directly; complex todos are "
                "delegated via `Spawn` (mark with metadata={\"delegate_to\": \"general\"}). "
                "Returns todo id."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Short, action-oriented title (verb + noun, e.g. 'Create User model')"},
                    "description": {"type": "string", "description": "What needs to be done + acceptance criteria"},
                    "activeForm": {"type": "string", "description": "Active form description"},
                    "metadata": {"type": "object", "description": 'Optional metadata. Supports priority (high/medium/low), effort (small/medium/large), and delegate_to (general|explore|scout|main) to flag complex todos for Spawn subagent execution.'},
                },
                "required": ["subject", "description"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        todo = self._tm.create_todo(
            subject=tool_input.get("subject", ""),
            description=tool_input.get("description", ""),
            active_form=tool_input.get("activeForm", ""),
            metadata=tool_input.get("metadata"),
        )
        return ToolResult(name="TodoCreate", output={"task": {"id": todo["id"], "subject": todo["subject"]}})



class TodoGetTool(Tool):
    def __init__(self, todo_manager):
        self._tm = todo_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TodoGet",
            description="Retrieve a todo by ID.",
            input_schema={
                "type": "object",
                "properties": {
                    "taskId": {"type": "string", "description": "Todo id to retrieve"},
                },
                "required": ["taskId"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        todo_id = tool_input.get("taskId", "")
        todo = self._tm.get_todo(todo_id)
        if todo is None:
            return ToolResult(name="TodoGet", output={"task": None})
        info = {k: todo[k] for k in ("id", "subject", "description", "status", "blocks", "blockedBy")}
        return ToolResult(name="TodoGet", output={"task": info})



class TodoListTool(Tool):
    def __init__(self, todo_manager):
        self._tm = todo_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TodoList",
            description="List all todos with their current status and dependencies.",
            input_schema={"type": "object", "properties": {}, "required": []},
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        todos = self._tm.list_todos()
        if not todos:
            return ToolResult(name="TodoList", output={"tasks": []})
        summaries = []
        for t in todos:
            s = {"id": t["id"], "subject": t["subject"], "status": t["status"]}
            if t.get("owner"):
                s["owner"] = t["owner"]
            s["blockedBy"] = list(t.get("blockedBy") or [])
            summaries.append(s)
        return ToolResult(name="TodoList", output={"tasks": summaries})



class TodoUpdateTool(Tool):
    def __init__(self, todo_manager):
        self._tm = todo_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TodoUpdate",
            description="Update a todo: subject, description, status, owner, dependencies, output.",
            input_schema={
                "type": "object",
                "properties": {
                    "taskId": {"type": "string", "description": "Todo id to update"},
                    "subject": {"type": "string"},
                    "description": {"type": "string"},
                    "activeForm": {"type": "string"},
                    "status": {"type": "string", "description": "pending|in_progress|completed|deleted"},
                    "owner": {"type": "string"},
                    "addBlocks": {"type": "array", "items": {"type": "string"}, "description": "Todo IDs this todo blocks"},
                    "addBlockedBy": {"type": "array", "items": {"type": "string"}, "description": "Todo IDs that block this"},
                    "metadata": {"type": "object"},
                    "output": {"type": "string", "description": "Key results to pass to downstream todos"},
                },
                "required": ["taskId"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        todo_id = tool_input.get("taskId", "")
        updates = {k: v for k, v in tool_input.items() if k != "taskId" and v is not None}
        if "subject" not in updates and "title" in updates:
            updates["subject"] = updates.pop("title")
        if "addBlocks" not in updates and "blocks" in updates and isinstance(updates.get("blocks"), list):
            updates["addBlocks"] = updates.pop("blocks")
        result = self._tm.update_todo(todo_id, **updates)
        if result is None:
            return ToolResult(name="TodoUpdate", output={"success": False, "taskId": todo_id, "error": "Todo not found"}, is_error=True)
        if result.get("deleted"):
            return ToolResult(name="TodoUpdate", output={"success": True, "taskId": todo_id, "updatedFields": ["deleted"]})
        return ToolResult(name="TodoUpdate", output={"success": True, "taskId": todo_id, "task": {"id": result["id"], "subject": result["subject"], "status": result["status"]}})



class TodoOutputTool(Tool):
    def __init__(self, todo_manager):
        self._tm = todo_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TodoOutput",
            description="Get output for a todo.",
            input_schema={
                "type": "object",
                "properties": {
                    "taskId": {"type": "string", "description": "Todo id to get output for"},
                },
                "required": ["taskId"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        todo_id = tool_input.get("taskId", "")
        result = self._tm.get_todo_output(todo_id)
        return ToolResult(name="TodoOutput", output=result)



class TodoStopTool(Tool):
    def __init__(self, todo_manager):
        self._tm = todo_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TodoStop",
            description="Stop/cancel a running todo.",
            input_schema={
                "type": "object",
                "properties": {
                    "taskId": {"type": "string", "description": "Todo id to stop"},
                },
                "required": ["taskId"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        todo_id = tool_input.get("taskId", "")
        result = self._tm.update_todo(todo_id, status="completed")
        if result is None:
            return ToolResult(name="TodoStop", output={"success": False, "stopped": False, "error": "Todo not found"}, is_error=True)
        if result.get("deleted"):
            return ToolResult(name="TodoStop", output={"success": True, "stopped": True, "taskId": todo_id})
        return ToolResult(name="TodoStop", output={"success": True, "stopped": True, "taskId": todo_id})
