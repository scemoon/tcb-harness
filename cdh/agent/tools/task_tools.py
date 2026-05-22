from __future__ import annotations

from typing import Any

from cdh.agent.tools.protocol import ToolResult
from cdh.agent.tools.registry import ToolSpec


class TaskCreateTool:
    def __init__(self, task_manager):
        self._tm = task_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TaskCreate",
            description="Create a task with dependency tracking. Returns task id.",
            input_schema={
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Task subject/title"},
                    "description": {"type": "string", "description": "Detailed task description"},
                    "activeForm": {"type": "string", "description": "Active form description"},
                    "metadata": {"type": "object", "description": "Optional metadata"},
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
        return ToolResult(name="TaskCreate", output={"task": {"id": task["id"], "subject": task["subject"]}})


class TaskGetTool:
    def __init__(self, task_manager):
        self._tm = task_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TaskGet",
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
            return ToolResult(name="TaskGet", output={"task": None})
        info = {k: task[k] for k in ("id", "subject", "description", "status", "blocks", "blockedBy")}
        return ToolResult(name="TaskGet", output={"task": info})


class TaskListTool:
    def __init__(self, task_manager):
        self._tm = task_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TaskList",
            description="List all tasks with their current status and dependencies.",
            input_schema={"type": "object", "properties": {}, "required": []},
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        tasks = self._tm.list_tasks()
        if not tasks:
            return ToolResult(name="TaskList", output={"tasks": []})
        summaries = []
        for t in tasks:
            s = {"id": t["id"], "subject": t["subject"], "status": t["status"]}
            if t.get("owner"):
                s["owner"] = t["owner"]
            s["blockedBy"] = list(t.get("blockedBy") or [])
            summaries.append(s)
        return ToolResult(name="TaskList", output={"tasks": summaries})


class TaskUpdateTool:
    def __init__(self, task_manager):
        self._tm = task_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TaskUpdate",
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
                    "output": {"type": "string"},
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
            return ToolResult(name="TaskUpdate", output={"success": False, "taskId": task_id, "error": "Task not found"}, is_error=True)
        if result.get("deleted"):
            return ToolResult(name="TaskUpdate", output={"success": True, "taskId": task_id, "updatedFields": ["deleted"]})
        return ToolResult(name="TaskUpdate", output={"success": True, "taskId": task_id, "task": {"id": result["id"], "subject": result["subject"], "status": result["status"]}})


class TaskOutputTool:
    def __init__(self, task_manager):
        self._tm = task_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TaskOutput",
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
        return ToolResult(name="TaskOutput", output=result)


class TaskStopTool:
    def __init__(self, task_manager):
        self._tm = task_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TaskStop",
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
            return ToolResult(name="TaskStop", output={"success": False, "stopped": False, "error": "Task not found"}, is_error=True)
        if result.get("deleted"):
            return ToolResult(name="TaskStop", output={"success": True, "stopped": True, "task_id": task_id})
        return ToolResult(name="TaskStop", output={"success": True, "stopped": True, "task_id": task_id})


class TodoCreateTool:
    def __init__(self, task_manager):
        self._tm = task_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TodoCreate",
            description="Create a todo item. Returns todo id.",
            input_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Todo item text"},
                },
                "required": ["text"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        text = tool_input.get("text", "")
        todo_id = self._tm.add_todo(text)
        return ToolResult(name="TodoCreate", output={"id": todo_id, "text": text})


class TodoListTool:
    def __init__(self, task_manager):
        self._tm = task_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TodoList",
            description="List all todo items.",
            input_schema={"type": "object", "properties": {}, "required": []},
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        todos = self._tm.list_todos()
        return ToolResult(name="TodoList", output=todos)


class TodoCompleteTool:
    def __init__(self, task_manager):
        self._tm = task_manager

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="TodoComplete",
            description="Mark a todo as completed.",
            input_schema={
                "type": "object",
                "properties": {
                    "todo_id": {"type": "string", "description": "Todo id to complete"},
                },
                "required": ["todo_id"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        todo_id = tool_input.get("todo_id", tool_input.get("id", ""))
        ok = self._tm.complete_todo(str(todo_id))
        return ToolResult(name="TodoComplete", output={"success": ok, "todo_id": todo_id}, is_error=not ok)
