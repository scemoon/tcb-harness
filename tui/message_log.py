from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tui import paths


def sanitize_filename(name: str) -> str:
    """Replace characters that are problematic in file names with underscores."""
    return re.sub(r'[<>:"/\\|?*]', "_", name)


class MessageLog:
    """Structured JSON message log for recording user input and agent output.

    Writes one JSON line per event to a session-scoped log file for
    diagnostic analysis (e.g. why the agent returned no response).
    Logs are grouped by session_id — one file per session.
    """

    def __init__(self, session_id: str, agent_name: str, log_dir: Path | None = None) -> None:
        self._session_id = session_id
        self._agent_name = agent_name
        dir = (log_dir or paths.get_log()) / "messages"
        dir.mkdir(parents=True, exist_ok=True)
        self._path = dir / f"{sanitize_filename(session_id)}.jsonl"
        self._file: Any = None

    def _write(self, event: str, data: dict[str, Any]) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": self._session_id,
            "agent": self._agent_name,
            "event": event,
            **data,
        }
        if self._file is None:
            self._file = self._path.open("at", buffering=1)
        self._file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def user_input(self, text: str, turn: int) -> None:
        self._write("user_input", {"text": text, "turn": turn})

    def agent_output(self, text: str, turn: int) -> None:
        self._write("agent_output", {"text": text, "turn": turn})

    def agent_thought(self, text: str, turn: int) -> None:
        self._write("agent_thought", {"text": text, "turn": turn})

    def tool_call(self, name: str, tool_id: str, turn: int, **extra: Any) -> None:
        self._write("tool_call", {"tool_name": name, "tool_id": tool_id, "turn": turn, **extra})

    def tool_result(self, name: str, tool_id: str, turn: int, status: str = "success") -> None:
        self._write("tool_result", {"tool_name": name, "tool_id": tool_id, "turn": turn, "status": status})

    def turn_end(self, turn: int, stop_reason: str | None) -> None:
        self._write("turn_end", {"turn": turn, "stop_reason": stop_reason})

    def error(self, message: str, turn: int | None = None, **extra: Any) -> None:
        self._write("error", {"message": message, "turn": turn, **extra})

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
