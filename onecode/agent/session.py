from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("onecode.session")


@dataclass
class SessionData:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Untitled"
    mode: str = "build"
    project: str = ""
    model: str = ""
    provider: str = ""
    messages: list[dict] = field(default_factory=list)
    lifecycle_state: dict = field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    todos: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "mode": self.mode,
            "project": self.project,
            "model": self.model,
            "provider": self.provider,
            "messages": self.messages,
            "lifecycle_state": self.lifecycle_state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "todos": self.todos,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SessionData:
        # Merge legacy ``tasks`` and ``todos`` fields into the unified
        # ``todos`` list.  Older sessions stored them as two separate lists;
        # TodoManager.from_dict already handles the legacy entry shape, so
        # we just concatenate here.
        legacy_todos: list[dict] = []
        legacy_todos.extend(data.get("tasks") or [])
        legacy_todos.extend(data.get("todos") or [])
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", "Untitled"),
            mode=data.get("mode", "build"),
            project=data.get("project", ""),
            model=data.get("model", ""),
            provider=data.get("provider", ""),
            messages=data.get("messages", []),
            lifecycle_state=data.get("lifecycle_state", {}),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            todos=legacy_todos,
        )


class AgentSession:
    def __init__(self, session_id: Optional[str] = None, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or self._default_storage_path()
        self._data: SessionData = SessionData()
        if session_id:
            self._data.id = session_id

    def _default_storage_path(self) -> Path:
        from onecode.config import CLOUD_DEV_HARNESS_DIR
        return CLOUD_DEV_HARNESS_DIR / "sessions"

    @property
    def id(self) -> str:
        return self._data.id

    @property
    def name(self) -> str:
        return self._data.name

    @name.setter
    def name(self, value: str) -> None:
        self._data.name = value

    @property
    def messages(self) -> list[dict]:
        return self._data.messages

    @messages.setter
    def messages(self, value: list[dict]) -> None:
        self._data.messages = value

    @property
    def lifecycle_state(self) -> dict:
        return self._data.lifecycle_state

    @property
    def todos(self) -> list[dict]:
        return self._data.todos

    @todos.setter
    def todos(self, value: list[dict]) -> None:
        self._data.todos = value

    def add_message(self, role: str, content: str) -> None:
        self._data.messages.append({"role": role, "content": content})
        self._touch()

    def compact_messages(self, summary: str) -> None:
        if len(self._data.messages) <= 2:
            return
        system_msgs = [m for m in self._data.messages if m.get("role") == "system"]
        other_msgs = [m for m in self._data.messages if m.get("role") != "system"]
        self._data.messages = system_msgs + [
            {"role": "system", "content": f"[Previous context summarized]\n{summary}"}
        ]
        self._touch()

    def update_state(self, key: str, value: any) -> None:
        self._data.lifecycle_state[key] = value
        self._touch()

    def get_state(self, key: str, default: any = None) -> any:
        return self._data.lifecycle_state.get(key, default)

    def save(self) -> None:
        self.storage_path.mkdir(parents=True, exist_ok=True)
        file_path = self.storage_path / f"{self._data.id}.json"
        self._data.updated_at = datetime.now(timezone.utc).isoformat()
        file_path.write_text(json.dumps(self._data.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def load(self) -> bool:
        file_path = self.storage_path / f"{self._data.id}.json"
        if not file_path.exists():
            return False
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            self._data = SessionData.from_dict(data)
            return True
        except Exception as e:
            logger.warning("Failed to load session %s: %s", self._data.id, e)
            return False

    def delete(self) -> None:
        file_path = self.storage_path / f"{self._data.id}.json"
        if file_path.exists():
            file_path.unlink()

    def _touch(self) -> None:
        self._data.updated_at = datetime.now(timezone.utc).isoformat()

    @classmethod
    def list_sessions(cls, storage_path: Optional[Path] = None) -> list[SessionData]:
        path = storage_path or cls()._default_storage_path()
        if not path.exists():
            return []
        sessions = []
        for f in path.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                sessions.append(SessionData.from_dict(data))
            except Exception:
                continue
        return sorted(sessions, key=lambda s: s.updated_at or "", reverse=True)

    @classmethod
    def delete_by_id(cls, session_id: str, storage_path: Optional[Path] = None) -> bool:
        path = storage_path or cls()._default_storage_path()
        file_path = path / f"{session_id}.json"
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def to_dict(self) -> dict:
        return self._data.to_dict()