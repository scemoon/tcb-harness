from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pathlib import Path


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class TodoStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class TaskChecklistItem:
    id: int
    content: str
    status: str = "pending"

    def to_dict(self) -> dict:
        return {"id": self.id, "content": self.content, "status": self.status}

    @classmethod
    def from_dict(cls, data: dict) -> TaskChecklistItem:
        return cls(
            id=data["id"],
            content=data["content"],
            status=data.get("status", "pending"),
        )


@dataclass
class TodoItem:
    id: int
    content: str
    status: TodoStatus = TodoStatus.PENDING

    def to_dict(self) -> dict:
        return {"id": self.id, "content": self.content, "status": self.status.value}

    @classmethod
    def from_dict(cls, data: dict) -> TodoItem:
        return cls(
            id=data["id"],
            content=data["content"],
            status=TodoStatus(data.get("status", "pending")),
        )


@dataclass
class TaskChecklistState:
    items: list[TaskChecklistItem] = field(default_factory=list)
    completion_pct: int = 0
    in_progress_id: Optional[int] = None
    updated_at: Optional[datetime] = None

    def add(self, content: str, status: str = "pending") -> TaskChecklistItem:
        next_id = max([0] + [item.id for item in self.items]) + 1
        item = TaskChecklistItem(id=next_id, content=content, status=status)
        self.items.append(item)
        self._recalc()
        return item

    def update_status(self, item_id: int, status: str) -> bool:
        for item in self.items:
            if item.id == item_id:
                item.status = status
                self._recalc()
                return True
        return False

    def remove(self, item_id: int) -> bool:
        for i, item in enumerate(self.items):
            if item.id == item_id:
                self.items.pop(i)
                self._recalc()
                return True
        return False

    def _recalc(self) -> None:
        if not self.items:
            self.completion_pct = 0
            self.in_progress_id = None
        else:
            completed = sum(1 for item in self.items if item.status == "completed")
            self.completion_pct = int(100 * completed / len(self.items))
            in_progress = next((item.id for item in self.items if item.status == "in_progress"), None)
            self.in_progress_id = in_progress
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "items": [item.to_dict() for item in self.items],
            "completion_pct": self.completion_pct,
            "in_progress_id": self.in_progress_id,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TaskChecklistState:
        return cls(
            items=[TaskChecklistItem.from_dict(d) for d in data.get("items", [])],
            completion_pct=data.get("completion_pct", 0),
            in_progress_id=data.get("in_progress_id"),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
        )


@dataclass
class TaskGateRecord:
    id: str
    gate: str
    command: str
    exit_code: Optional[int] = None
    status: str = "pending"
    classification: str = ""
    duration_ms: int = 0
    summary: str = ""
    log_path: Optional[Path] = None


@dataclass
class TaskToolCallSummary:
    id: str
    name: str
    input: dict[str, Any]
    output: str = ""
    duration_ms: int = 0


@dataclass
class TaskTimelineEntry:
    timestamp: datetime
    event: str
    detail: str = ""


@dataclass
class TaskRecord:
    id: str
    prompt: str
    model: str
    workspace: Path
    status: TaskStatus = TaskStatus.QUEUED
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    checklist: TaskChecklistState = field(default_factory=TaskChecklistState)
    gates: list[TaskGateRecord] = field(default_factory=list)
    tool_calls: list[TaskToolCallSummary] = field(default_factory=list)
    timeline: list[TaskTimelineEntry] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "model": self.model,
            "workspace": str(self.workspace),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_ms": self.duration_ms,
            "checklist": self.checklist.to_dict(),
            "gates": [
                {
                    "id": g.id,
                    "gate": g.gate,
                    "command": g.command,
                    "exit_code": g.exit_code,
                    "status": g.status,
                    "classification": g.classification,
                    "duration_ms": g.duration_ms,
                    "summary": g.summary,
                    "log_path": str(g.log_path) if g.log_path else None,
                }
                for g in self.gates
            ],
            "tool_calls": [
                {
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.input,
                    "output": tc.output,
                    "duration_ms": tc.duration_ms,
                }
                for tc in self.tool_calls
            ],
            "timeline": [
                {
                    "timestamp": t.timestamp.isoformat(),
                    "event": t.event,
                    "detail": t.detail,
                }
                for t in self.timeline
            ],
            "artifacts": self.artifacts,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TaskRecord:
        from datetime import datetime
        return cls(
            id=data["id"],
            prompt=data["prompt"],
            model=data["model"],
            workspace=Path(data["workspace"]),
            status=TaskStatus(data.get("status", "queued")),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            ended_at=datetime.fromisoformat(data["ended_at"]) if data.get("ended_at") else None,
            duration_ms=data.get("duration_ms"),
            checklist=TaskChecklistState.from_dict(data.get("checklist", {})),
            gates=[TaskGateRecord(**g) for g in data.get("gates", [])],
            tool_calls=[TaskToolCallSummary(**tc) for tc in data.get("tool_calls", [])],
            timeline=[
                TaskTimelineEntry(
                    timestamp=datetime.fromisoformat(t["timestamp"]),
                    event=t["event"],
                    detail=t.get("detail", ""),
                )
                for t in data.get("timeline", [])
            ],
            artifacts=data.get("artifacts", []),
            error=data.get("error"),
        )