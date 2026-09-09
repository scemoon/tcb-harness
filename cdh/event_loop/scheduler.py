from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cdh.event_loop.bus import EventBus, EventLoopState
from cdh.event_loop.events import Event, EventTypes

logger = logging.getLogger("cdh.event_loop.scheduler")


@dataclass
class ScheduledJob:
    name: str
    interval_seconds: int
    command: str
    args: dict[str, Any] = field(default_factory=dict)
    engine: str = "onecode"
    next_run: datetime | None = None
    last_run: datetime | None = None
    active: bool = True
    run_count: int = 0


class Scheduler:
    def __init__(self, db_path: Path | None = None):
        self.state = EventLoopState.IDLE
        self._jobs: dict[str, ScheduledJob] = {}
        self._db_path = db_path or (Path.home() / ".cdh" / "scheduler.db")
        self._task: asyncio.Task | None = None

    def add(self, job: ScheduledJob) -> str:
        now = datetime.now(timezone.utc)
        job.next_run = now + timedelta(seconds=job.interval_seconds)
        self._jobs[job.name] = job
        self._save_jobs()
        return job.name

    def remove(self, name: str) -> bool:
        result = self._jobs.pop(name, None) is not None
        if result:
            self._save_jobs()
        return result

    def pause(self, name: str) -> bool:
        job = self._jobs.get(name)
        if job:
            job.active = False
            self._save_jobs()
            return True
        return False

    def resume(self, name: str) -> bool:
        job = self._jobs.get(name)
        if job:
            job.active = True
            job.next_run = datetime.now(timezone.utc) + timedelta(seconds=job.interval_seconds)
            self._save_jobs()
            return True
        return False

    def list(self) -> list[dict]:
        return [
            {
                "name": j.name,
                "interval_seconds": j.interval_seconds,
                "command": j.command,
                "engine": j.engine,
                "active": j.active,
                "run_count": j.run_count,
                "next_run": j.next_run.isoformat() if j.next_run else None,
                "last_run": j.last_run.isoformat() if j.last_run else None,
            }
            for j in self._jobs.values()
        ]

    async def start(self, bus: EventBus) -> None:
        self.state = EventLoopState.RUNNING
        self._load_jobs()

        async def _tick() -> None:
            while self.state == EventLoopState.RUNNING:
                now = datetime.now(timezone.utc)
                for job in list(self._jobs.values()):
                    if job.active and job.next_run and now >= job.next_run:
                        job.last_run = now
                        job.next_run = now + timedelta(seconds=job.interval_seconds)
                        job.run_count += 1
                        bus.publish(Event(
                            type=EventTypes.CRON_TICK,
                            source="cdh.scheduler",
                            payload={
                                "job_name": job.name,
                                "command": job.command,
                                "args": job.args,
                                "engine": job.engine,
                            },
                        ))
                await asyncio.sleep(1)

        self._task = asyncio.create_task(_tick())
        logger.info("Scheduler started with %d jobs", len(self._jobs))

    def stop(self) -> None:
        self.state = EventLoopState.COMPLETED
        if self._task:
            self._task.cancel()
            self._task = None
        self._save_jobs()
        logger.info("Scheduler stopped")

    def _save_jobs(self) -> None:
        data = {}
        for name, j in self._jobs.items():
            entry = {
                "name": j.name,
                "interval_seconds": j.interval_seconds,
                "command": j.command,
                "args": j.args,
                "engine": j.engine,
                "active": j.active,
                "run_count": j.run_count,
            }
            if j.next_run:
                entry["next_run"] = j.next_run.isoformat()
            if j.last_run:
                entry["last_run"] = j.last_run.isoformat()
            data[name] = entry
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path.write_text(json.dumps(data, indent=2))

    def _load_jobs(self) -> None:
        if not self._db_path.exists():
            return
        try:
            data = json.loads(self._db_path.read_text())
            for name, j in data.items():
                job = ScheduledJob(
                    name=j.get("name", name),
                    interval_seconds=j.get("interval_seconds", 300),
                    command=j.get("command", ""),
                    args=j.get("args", {}),
                    engine=j.get("engine", "onecode"),
                    active=j.get("active", True),
                    run_count=j.get("run_count", 0),
                )
                if j.get("next_run"):
                    job.next_run = datetime.fromisoformat(j["next_run"])
                if j.get("last_run"):
                    job.last_run = datetime.fromisoformat(j["last_run"])
                self._jobs[name] = job
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("Failed to load scheduler jobs: %s", e)