"""cdh platform session aggregator — cross-engine session registry.

Maintains a session registry at ~/.cdh/sessions/sessions.db (SQLite).
Provides a cross-engine view across all registered engines.
Engines register sessions via the aggregator API.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("cdh.session")

CDH_SESSIONS_DIR = Path.home() / ".cdh" / "sessions"


class CdhSessionAggregator:
    def __init__(self, sessions_dir: Path | None = None):
        self.sessions_dir = sessions_dir or CDH_SESSIONS_DIR
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.sessions_dir / "sessions.db"
        self._init_db()

    def _init_db(self) -> None:
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    engine TEXT NOT NULL,
                    engine_session_id TEXT NOT NULL,
                    project_name TEXT DEFAULT '',
                    agent TEXT NOT NULL,
                    title TEXT NOT NULL,
                    protocol TEXT DEFAULT 'acp',
                    prompt_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    last_used TEXT NOT NULL,
                    meta_json TEXT DEFAULT '{}',
                    UNIQUE(engine, engine_session_id)
                )
                """
            )
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error("Failed to init session db: %s", e)

    def register(
        self,
        engine: str,
        engine_session_id: str,
        agent: str,
        title: str,
        project_name: str = "",
        protocol: str = "acp",
        meta: dict[str, Any] | None = None,
    ) -> Optional[int]:
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute(
                """
                INSERT OR REPLACE INTO sessions
                    (engine, engine_session_id, project_name, agent, title, protocol,
                     prompt_count, created_at, last_used, meta_json)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    engine,
                    engine_session_id,
                    project_name,
                    agent,
                    title,
                    protocol,
                    now,
                    now,
                    json.dumps(meta or {}),
                ),
            )
            conn.commit()
            cursor = conn.execute("SELECT last_insert_rowid()")
            row_id = cursor.fetchone()[0]
            conn.close()
            return row_id
        except sqlite3.Error as e:
            logger.error("Failed to register session: %s", e)
            return None

    def update_last_used(self, engine: str, engine_session_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute(
                "UPDATE sessions SET last_used = ? WHERE engine = ? AND engine_session_id = ?",
                (now, engine, engine_session_id),
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.Error:
            return False

    def increment_prompt_count(self, engine: str, engine_session_id: str) -> bool:
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute(
                "UPDATE sessions SET prompt_count = prompt_count + 1 WHERE engine = ? AND engine_session_id = ?",
                (engine, engine_session_id),
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.Error:
            return False

    def get(self, session_id: int) -> Optional[dict]:
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None
        except sqlite3.Error:
            return None

    def get_by_engine_id(self, engine: str, engine_session_id: str) -> Optional[dict]:
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE engine = ? AND engine_session_id = ?",
                (engine, engine_session_id),
            )
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None
        except sqlite3.Error:
            return None

    def get_recent(self, max_results: int = 100) -> list[dict]:
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM sessions ORDER BY last_used DESC LIMIT ?",
                (max_results,),
            )
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except sqlite3.Error:
            return []

    def get_by_engine(self, engine: str, max_results: int = 100) -> list[dict]:
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE engine = ? ORDER BY last_used DESC LIMIT ?",
                (engine, max_results),
            )
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except sqlite3.Error:
            return []

    def get_by_project(self, project_name: str, max_results: int = 100) -> list[dict]:
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE project_name = ? ORDER BY last_used DESC LIMIT ?",
                (project_name, max_results),
            )
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except sqlite3.Error:
            return []

    def delete(self, session_id: int) -> bool:
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
            conn.close()
            return True
        except sqlite3.Error:
            return False

    def count(self) -> int:
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.execute("SELECT COUNT(*) FROM sessions")
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except sqlite3.Error:
            return 0

    def list_engines(self) -> list[str]:
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.execute("SELECT DISTINCT engine FROM sessions ORDER BY engine")
            rows = cursor.fetchall()
            conn.close()
            return [r[0] for r in rows]
        except sqlite3.Error:
            return []

    def import_from_tui_db(self, tui_db_path: Path) -> int:
        """Import sessions from a tui.db into the aggregator.

        Returns the number of sessions imported.
        """
        if not tui_db_path.exists():
            logger.info("No tui.db found at %s", tui_db_path)
            return 0

        imported = 0
        try:
            tui_conn = sqlite3.connect(str(tui_db_path))
            tui_conn.row_factory = sqlite3.Row
            cursor = tui_conn.execute(
                "SELECT * FROM sessions ORDER BY id"
            )
            rows = cursor.fetchall()
            tui_conn.close()

            for row in rows:
                sess = dict(row)
                engine = sess.get("agent_identity", "tui").lower()
                engine_session_id = sess.get("agent_session_id", str(sess["id"]))
                if self.get_by_engine_id(engine, engine_session_id) is None:
                    self.register(
                        engine=engine,
                        engine_session_id=engine_session_id,
                        agent=sess.get("agent", engine),
                        title=sess.get("title", f"Session {sess['id']}"),
                        protocol=sess.get("protocol", "acp"),
                        meta={"imported_from": str(tui_db_path), "original_id": sess["id"]},
                    )
                    imported += 1

            logger.info("Imported %d sessions from %s", imported, tui_db_path)
        except sqlite3.Error as e:
            logger.error("Failed to import from tui.db: %s", e)

        return imported
