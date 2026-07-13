from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cdh.optimizer.mutation import ConfigMutation
from cdh.optimizer.reward import RewardCalculator, SessionMetrics


@dataclass
class TrackedMutation:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    config: dict[str, Any] = field(default_factory=dict)
    reward: float = 0.0
    session_count: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class OptimizationTracker:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or (Path.home() / ".cdh" / "optimizer.db")
        self._reward_calc = RewardCalculator()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                test_pass_rate REAL,
                task_completion_pct REAL,
                tool_efficiency REAL,
                turn_count INTEGER,
                reward REAL,
                timestamp TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mutations (
                id TEXT PRIMARY KEY,
                params_json TEXT,
                reward REAL,
                session_count INTEGER,
                timestamp TEXT
            )
        """)
        conn.commit()
        conn.close()

    def record(self, metrics: SessionMetrics) -> None:
        reward = self._reward_calc.compute(metrics)
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            "INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), metrics.session_id,
             metrics.test_pass_rate, metrics.task_completion_pct,
             metrics.tool_efficiency, metrics.turn_count,
             reward, metrics.timestamp),
        )
        conn.commit()
        conn.close()

    def get_all(self) -> list[SessionMetrics]:
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute("SELECT * FROM sessions ORDER BY timestamp").fetchall()
        conn.close()
        return [
            SessionMetrics(
                session_id=r[1], test_pass_rate=r[2],
                task_completion_pct=r[3], tool_efficiency=r[4],
                turn_count=r[5], timestamp=r[7],
            )
            for r in rows
        ]

    def count(self) -> int:
        conn = sqlite3.connect(str(self.db_path))
        cnt = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()
        return cnt

    def clear(self) -> None:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("DELETE FROM sessions")
        conn.commit()
        conn.close()

    def save_mutation(self, mutation: ConfigMutation) -> None:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            "INSERT OR REPLACE INTO mutations VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), json.dumps(mutation.params),
             mutation.parent_reward, 0, mutation.timestamp),
        )
        conn.commit()
        conn.close()

    def get_best_mutation(self) -> TrackedMutation | None:
        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute(
            "SELECT * FROM mutations ORDER BY reward DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            return TrackedMutation(
                id=row[0],
                config=json.loads(row[1]),
                reward=row[2],
                session_count=row[3],
                timestamp=row[4],
            )
        return None