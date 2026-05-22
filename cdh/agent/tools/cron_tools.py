from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from cdh.agent.tools.protocol import ToolResult
from cdh.agent.tools.registry import ToolSpec


@dataclass
class CronJob:
    name: str
    interval_seconds: int
    command: str
    args: dict[str, Any] = field(default_factory=dict)
    last_run: datetime | None = None
    next_run: datetime | None = None
    active: bool = True
    run_count: int = 0


class CronScheduler:
    """Simple in-process cron scheduler for periodic tool execution."""

    def __init__(self):
        self._jobs: dict[str, CronJob] = {}
        self._task: asyncio.Task | None = None

    def add(self, name: str, interval_seconds: int, command: str, args: dict | None = None) -> str:
        now = datetime.now()
        job = CronJob(
            name=name,
            interval_seconds=interval_seconds,
            command=command,
            args=args or {},
            next_run=now + timedelta(seconds=interval_seconds),
        )
        self._jobs[name] = job
        return name

    def remove(self, name: str) -> bool:
        return self._jobs.pop(name, None) is not None

    def list(self) -> list[dict]:
        return [
            {
                "name": j.name,
                "interval_seconds": j.interval_seconds,
                "command": j.command,
                "active": j.active,
                "run_count": j.run_count,
                "next_run": j.next_run.isoformat() if j.next_run else None,
            }
            for j in self._jobs.values()
        ]

    def pause(self, name: str) -> bool:
        job = self._jobs.get(name)
        if job:
            job.active = False
            return True
        return False

    def resume(self, name: str) -> bool:
        job = self._jobs.get(name)
        if job:
            job.active = True
            job.next_run = datetime.now() + timedelta(seconds=job.interval_seconds)
            return True
        return False

    async def start_loop(self, executor: Callable[[str, dict], None] | None = None) -> None:
        async def _tick():
            while True:
                now = datetime.now()
                for job in list(self._jobs.values()):
                    if job.active and job.next_run and now >= job.next_run:
                        job.last_run = now
                        job.next_run = now + timedelta(seconds=job.interval_seconds)
                        job.run_count += 1
                        if executor:
                            try:
                                executor(job.command, job.args)
                            except Exception:
                                pass
                await asyncio.sleep(1)
        self._task = asyncio.create_task(_tick())

    def stop_loop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None


class CronCreateTool:
    """Create a scheduled cron job (Clawd-Code pattern)."""

    def __init__(self, scheduler: CronScheduler):
        self._scheduler = scheduler

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="CronCreate",
            description="Create a scheduled job that runs periodically. The command is a tool name; args are passed to it.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Unique job name"},
                    "interval_seconds": {"type": "integer", "description": "Interval in seconds"},
                    "command": {"type": "string", "description": "Tool name to execute"},
                    "args": {"type": "object", "description": "Arguments to pass to the tool"},
                },
                "required": ["name", "interval_seconds", "command"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        name = tool_input["name"]
        if name in self._scheduler._jobs:
            return ToolResult(name="CronCreate", output={"error": f"job '{name}' already exists"}, is_error=True)
        self._scheduler.add(
            name=name,
            interval_seconds=tool_input["interval_seconds"],
            command=tool_input["command"],
            args=tool_input.get("args"),
        )
        return ToolResult(name="CronCreate", output={"name": name, "status": "created"})


class CronListTool:
    """List all cron jobs."""

    def __init__(self, scheduler: CronScheduler):
        self._scheduler = scheduler

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="CronList",
            description="List all registered cron jobs with their status and next run time.",
            input_schema={
                "type": "object",
                "properties": {},
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        return ToolResult(name="CronList", output={"jobs": self._scheduler.list()})


class CronRemoveTool:
    """Remove a cron job."""

    def __init__(self, scheduler: CronScheduler):
        self._scheduler = scheduler

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="CronRemove",
            description="Remove a cron job by name.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Job name to remove"},
                },
                "required": ["name"],
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        name = tool_input.get("name", "")
        if self._scheduler.remove(name):
            return ToolResult(name="CronRemove", output={"name": name, "status": "removed"})
        return ToolResult(name="CronRemove", output={"error": f"job '{name}' not found"}, is_error=True)
