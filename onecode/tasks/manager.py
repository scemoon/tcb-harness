from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("onecode.tasks")

from onecode.tasks.models import (
    TaskRecord,
    TaskStatus,
    TaskChecklistState,
    TaskGateRecord,
    TaskToolCallSummary,
)


class TaskExecutor(Callable[..., Any]):
    async def execute(
        self,
        task: "ExecutionTask",
        events: asyncio.Queue,
        cancel: asyncio.Event,
    ) -> dict[str, Any]:
        raise NotImplementedError


@dataclass
class ExecutionTask:
    id: str
    prompt: str
    model: str
    workspace: Path


@dataclass
class TaskExecutionResult:
    task_id: str
    success: bool
    output: str = ""
    error: Optional[str] = None
    duration_ms: int = 0


class TaskManager:
    def __init__(self, storage_path: Optional[Path] = None):
        self._tasks: dict[str, TaskRecord] = {}
        self._queue: asyncio.Queue[ExecutionTask] = asyncio.Queue()
        self._running: dict[str, asyncio.Task] = {}
        self._storage_path = storage_path or Path.home() / ".cdh" / "tasks"
        self._executor: Optional[TaskExecutor] = None
        self._worker_task: Optional[asyncio.Task] = None

    def set_executor(self, executor: TaskExecutor) -> None:
        self._executor = executor

    def add_task(
        self,
        prompt: str,
        model: str = "MiniMax-M2.7",
        workspace: Optional[Path] = None,
        checklist: Optional[TaskChecklistState] = None,
    ) -> TaskRecord:
        task = TaskRecord(
            id=str(uuid.uuid4())[:8],
            prompt=prompt,
            model=model,
            workspace=workspace or Path.cwd(),
            checklist=checklist or TaskChecklistState(),
        )
        self._tasks[task.id] = task
        self._queue.put_nowait(
            ExecutionTask(
                id=task.id,
                prompt=prompt,
                model=model,
                workspace=task.workspace,
            )
        )
        return task

    async def start_worker(self) -> None:
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker_loop())

    async def _worker_loop(self) -> None:
        while True:
            try:
                task = await self._queue.get()
                if task.id not in self._running:
                    self._running[task.id] = asyncio.create_task(self._run_task(task))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Task worker error: %s", e)

    async def _run_task(self, execution: ExecutionTask) -> None:
        task_record = self._tasks.get(execution.id)
        if not task_record:
            return

        task_record.status = TaskStatus.RUNNING
        task_record.started_at = datetime.utcnow()

        try:
            if self._executor:
                cancel = asyncio.Event()
                events: asyncio.Queue = asyncio.Queue()
                result = await self._executor.execute(execution, events, cancel)
                task_record.status = TaskStatus.COMPLETED if result.get("success") else TaskStatus.FAILED
                task_record.error = result.get("error")
            else:
                await asyncio.sleep(0.1)
                task_record.status = TaskStatus.COMPLETED
        except Exception as e:
            task_record.status = TaskStatus.FAILED
            task_record.error = str(e)
        finally:
            task_record.ended_at = datetime.utcnow()
            if task_record.started_at:
                task_record.duration_ms = int(
                    (task_record.ended_at - task_record.started_at).total_seconds() * 1000
                )
            self._running.pop(execution.id, None)

    def cancel_task(self, task_id: str) -> bool:
        if task_id in self._running:
            self._running[task_id].cancel()
            task_record = self._tasks.get(task_id)
            if task_record:
                task_record.status = TaskStatus.CANCELED
                task_record.ended_at = datetime.utcnow()
            return True
        return False

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        return self._tasks.get(task_id)

    def list_tasks(self, status: Optional[TaskStatus] = None) -> list[TaskRecord]:
        if status is None:
            return list(self._tasks.values())
        return [t for t in self._tasks.values() if t.status == status]

    def add_todo_to_task(self, task_id: str, content: str, status: str = "pending") -> Optional["TaskChecklistItem"]:  # noqa: F821
        task = self._tasks.get(task_id)
        if not task:
            return None
        return task.checklist.add(content, status)

    def update_todo_status(self, task_id: str, todo_id: int, status: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        return task.checklist.update_status(todo_id, status)

    def add_gate(
        self,
        task_id: str,
        gate: str,
        command: str,
    ) -> Optional[TaskGateRecord]:
        task = self._tasks.get(task_id)
        if not task:
            return None
        gate_record = TaskGateRecord(
            id=str(uuid.uuid4())[:8],
            gate=gate,
            command=command,
        )
        task.gates.append(gate_record)
        return gate_record

    def add_tool_call(
        self,
        task_id: str,
        tool_id: str,
        name: str,
        input: dict[str, Any],
    ) -> Optional[TaskToolCallSummary]:
        task = self._tasks.get(task_id)
        if not task:
            return None
        tc = TaskToolCallSummary(id=tool_id, name=name, input=input)
        task.tool_calls.append(tc)
        return tc

    def update_tool_call_output(self, task_id: str, tool_id: str, output: str, duration_ms: int) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        for tc in task.tool_calls:
            if tc.id == tool_id:
                tc.output = output
                tc.duration_ms = duration_ms
                return True
        return False

    def add_timeline_entry(self, task_id: str, event: str, detail: str = "") -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        from onecode.tasks.models import TaskTimelineEntry
        task.timeline.append(TaskTimelineEntry(timestamp=datetime.utcnow(), event=event, detail=detail))
        return True

    async def stop(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass