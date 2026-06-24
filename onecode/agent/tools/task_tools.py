from __future__ import annotations

from typing import Any

from onecode.agent.tools.protocol import ToolResult
from onecode.agent.tools.registry import ToolSpec


class TaskCreateTool:
    def __init__(self, task_manager):
        self._tm = task_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TodoCreate",
            description="Create a fine-grained task (1-3 tool calls each). For large work, split into multiple smaller tasks with dependencies. Returns task id.",
            input_schema={
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Short, action-oriented title (verb + noun, e.g. 'Create User model')"},
                    "description": {"type": "string", "description": "What needs to be done + acceptance criteria"},
                    "activeForm": {"type": "string", "description": "Active form description"},
                    "metadata": {"type": "object", "description": 'Optional metadata. Supports priority (high/medium/low) and effort (small/medium/large)'},
                },
                "required": ["subject", "description"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        task = self._tm.create_task(
            subject=tool_input.get("subject", ""),
            description=tool_input.get("description", ""),
            active_form=tool_input.get("activeForm", ""),
            metadata=tool_input.get("metadata"),
        )
        return ToolResult(name="TodoCreate", output={"task": {"id": task["id"], "subject": task["subject"]}})



class TaskGetTool:
    def __init__(self, task_manager):
        self._tm = task_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TodoGet",
            description="Retrieve a task by ID.",
            input_schema={
                "type": "object",
                "properties": {
                    "taskId": {"type": "string", "description": "Task id to retrieve"},
                },
                "required": ["taskId"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        task_id = tool_input.get("taskId", "")
        task = self._tm.get_task(task_id)
        if task is None:
            return ToolResult(name="TodoGet", output={"task": None})
        info = {k: task[k] for k in ("id", "subject", "description", "status", "blocks", "blockedBy")}
        return ToolResult(name="TodoGet", output={"task": info})



class TaskListTool:
    def __init__(self, task_manager):
        self._tm = task_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TodoList",
            description="List all tasks with their current status and dependencies.",
            input_schema={"type": "object", "properties": {}, "required": []},
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        tasks = self._tm.list_tasks()
        if not tasks:
            return ToolResult(name="TodoList", output={"tasks": []})
        summaries = []
        for t in tasks:
            s = {"id": t["id"], "subject": t["subject"], "status": t["status"]}
            if t.get("owner"):
                s["owner"] = t["owner"]
            s["blockedBy"] = list(t.get("blockedBy") or [])
            summaries.append(s)
        return ToolResult(name="TodoList", output={"tasks": summaries})



class TaskUpdateTool:
    def __init__(self, task_manager):
        self._tm = task_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TodoUpdate",
            description="Update a task: subject, description, status, owner, dependencies, output.",
            input_schema={
                "type": "object",
                "properties": {
                    "taskId": {"type": "string", "description": "Task id to update"},
                    "subject": {"type": "string"},
                    "description": {"type": "string"},
                    "activeForm": {"type": "string"},
                    "status": {"type": "string", "description": "pending|in_progress|completed|deleted"},
                    "owner": {"type": "string"},
                    "addBlocks": {"type": "array", "items": {"type": "string"}, "description": "Task IDs this task blocks"},
                    "addBlockedBy": {"type": "array", "items": {"type": "string"}, "description": "Task IDs that block this"},
                    "metadata": {"type": "object"},
                    "output": {"type": "string", "description": "Key results to pass to downstream tasks"},
                },
                "required": ["taskId"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        task_id = tool_input.get("taskId", "")
        updates = {k: v for k, v in tool_input.items() if k != "taskId" and v is not None}
        if "subject" not in updates and "title" in updates:
            updates["subject"] = updates.pop("title")
        if "addBlocks" not in updates and "blocks" in updates and isinstance(updates.get("blocks"), list):
            updates["addBlocks"] = updates.pop("blocks")
        result = self._tm.update_task(task_id, **updates)
        if result is None:
            return ToolResult(name="TodoUpdate", output={"success": False, "taskId": task_id, "error": "Task not found"}, is_error=True)
        if result.get("deleted"):
            return ToolResult(name="TodoUpdate", output={"success": True, "taskId": task_id, "updatedFields": ["deleted"]})
        return ToolResult(name="TodoUpdate", output={"success": True, "taskId": task_id, "task": {"id": result["id"], "subject": result["subject"], "status": result["status"]}})



class TaskOutputTool:
    def __init__(self, task_manager):
        self._tm = task_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TodoOutput",
            description="Get output for a task.",
            input_schema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task id to get output for"},
                },
                "required": ["task_id"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        task_id = tool_input.get("task_id", "")
        result = self._tm.get_task_output(task_id)
        return ToolResult(name="TodoOutput", output=result)



class TaskStopTool:
    def __init__(self, task_manager):
        self._tm = task_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TodoStop",
            description="Stop/cancel a running task.",
            input_schema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task id to stop"},
                },
                "required": ["task_id"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        task_id = tool_input.get("task_id", "")
        result = self._tm.update_task(task_id, status="completed")
        if result is None:
            return ToolResult(name="TodoStop", output={"success": False, "stopped": False, "error": "Task not found"}, is_error=True)
        if result.get("deleted"):
            return ToolResult(name="TodoStop", output={"success": True, "stopped": True, "task_id": task_id})
        return ToolResult(name="TodoStop", output={"success": True, "stopped": True, "task_id": task_id})




