"""Tests for cdh platform session aggregator.

Covers:
- CdhSessionAggregator register/get/update/delete
- Cross-engine query (get_by_engine, get_by_project, get_recent)
- import_from_tui_db
- Path separation
"""

from __future__ import annotations

import sqlite3
from pathlib import Path



class TestCdhSessionAggregator:
    def test_register_creates_session(self, tmp_path):
        agg = _make_agg(tmp_path)
        sid = agg.register("onecode", "sess-1", "agent-a", "Test Session")
        assert sid is not None
        assert isinstance(sid, int)

    def test_get_returns_session(self, tmp_path):
        agg = _make_agg(tmp_path)
        sid = agg.register("onecode", "sess-1", "agent-a", "Test Session")
        sess = agg.get(sid)
        assert sess is not None
        assert sess["engine"] == "onecode"
        assert sess["title"] == "Test Session"

    def test_get_returns_none_when_missing(self, tmp_path):
        agg = _make_agg(tmp_path)
        assert agg.get(999) is None

    def test_get_by_engine_id(self, tmp_path):
        agg = _make_agg(tmp_path)
        agg.register("onecode", "sess-abc", "agent-a", "Sess")
        sess = agg.get_by_engine_id("onecode", "sess-abc")
        assert sess is not None
        assert sess["title"] == "Sess"

    def test_get_by_engine_id_returns_none_when_missing(self, tmp_path):
        agg = _make_agg(tmp_path)
        assert agg.get_by_engine_id("ghost", "x") is None

    def test_register_prevents_duplicate(self, tmp_path):
        agg = _make_agg(tmp_path)
        agg.register("onecode", "sess-1", "agent-a", "First")
        agg.register("onecode", "sess-1", "agent-b", "Second")
        # Should be an upsert — same engine+engine_session_id
        sess = agg.get_by_engine_id("onecode", "sess-1")
        assert sess is not None
        assert sess["agent"] == "agent-b"
        assert sess["title"] == "Second"

    def test_update_last_used(self, tmp_path):
        agg = _make_agg(tmp_path)
        sid = agg.register("onecode", "sess-1", "agent-a", "Sess")
        assert agg.update_last_used("onecode", "sess-1") is True
        sess = agg.get(sid)
        assert sess is not None
        assert sess["last_used"] != sess["created_at"]

    def test_increment_prompt_count(self, tmp_path):
        agg = _make_agg(tmp_path)
        agg.register("onecode", "sess-1", "agent-a", "Sess")
        assert agg.increment_prompt_count("onecode", "sess-1") is True
        sess = agg.get_by_engine_id("onecode", "sess-1")
        assert sess is not None
        assert sess["prompt_count"] == 1

    def test_get_recent_returns_ordered(self, tmp_path):
        agg = _make_agg(tmp_path)
        agg.register("onecode", "s1", "a", "Old")
        agg.register("onecode", "s2", "a", "New")
        recent = agg.get_recent()
        assert len(recent) == 2
        # Most recent first
        assert recent[0]["title"] == "New"

    def test_get_recent_respects_limit(self, tmp_path):
        agg = _make_agg(tmp_path)
        for i in range(5):
            agg.register("onecode", f"s{i}", "a", f"S{i}")
        recent = agg.get_recent(max_results=3)
        assert len(recent) == 3

    def test_get_by_engine_filters(self, tmp_path):
        agg = _make_agg(tmp_path)
        agg.register("onecode", "s1", "a", "Onecode Sess")
        agg.register("opencode", "s2", "b", "Opencode Sess")
        onecode_sessions = agg.get_by_engine("onecode")
        assert len(onecode_sessions) == 1
        assert onecode_sessions[0]["engine"] == "onecode"

    def test_get_by_project(self, tmp_path):
        agg = _make_agg(tmp_path)
        agg.register("onecode", "s1", "a", "Proj Sess", project_name="my-project")
        agg.register("onecode", "s2", "a", "Other", project_name="other")
        proj_sessions = agg.get_by_project("my-project")
        assert len(proj_sessions) == 1
        assert proj_sessions[0]["title"] == "Proj Sess"

    def test_delete_removes_session(self, tmp_path):
        agg = _make_agg(tmp_path)
        sid = agg.register("onecode", "s1", "a", "To Delete")
        assert agg.delete(sid) is True
        assert agg.get(sid) is None

    def test_delete_nonexistent(self, tmp_path):
        agg = _make_agg(tmp_path)
        assert agg.delete(999) is True  # sqlite returns rows_affected=0, not error

    def test_count(self, tmp_path):
        agg = _make_agg(tmp_path)
        assert agg.count() == 0
        agg.register("onecode", "s1", "a", "S1")
        agg.register("opencode", "s2", "b", "S2")
        assert agg.count() == 2

    def test_list_engines(self, tmp_path):
        agg = _make_agg(tmp_path)
        agg.register("onecode", "s1", "a", "S1")
        agg.register("opencode", "s2", "b", "S2")
        engines = agg.list_engines()
        assert sorted(engines) == ["onecode", "opencode"]

    def test_list_engines_empty(self, tmp_path):
        agg = _make_agg(tmp_path)
        assert agg.list_engines() == []

    def test_persistence(self, tmp_path):
        agg_dir = tmp_path / "sessions"
        agg1 = _make_agg(tmp_path, agg_dir)
        agg1.register("onecode", "s1", "a", "Persistent")

        agg2 = _make_agg(tmp_path, agg_dir)
        assert agg2.count() == 1
        assert agg2.get_by_engine_id("onecode", "s1") is not None


class TestCdhSessionAggregatorImport:
    def test_import_from_missing_db(self, tmp_path):
        agg = _make_agg(tmp_path)
        count = agg.import_from_tui_db(tmp_path / "nonexistent.db")
        assert count == 0

    def test_import_from_tui_db(self, tmp_path):
        tui_db = tmp_path / "tui.db"
        _create_tui_db(tui_db, [
            ("onecode", "onecode", "sess-uuid-1", "Chat Session"),
            ("opencode", "opencode", "sess-uuid-2", "Code Review"),
        ])

        agg = _make_agg(tmp_path)
        count = agg.import_from_tui_db(tui_db)
        assert count == 2
        assert agg.count() == 2

    def test_import_skips_duplicates(self, tmp_path):
        tui_db = tmp_path / "tui.db"
        _create_tui_db(tui_db, [
            ("onecode", "onecode", "sess-uuid-1", "Original"),
        ])

        agg = _make_agg(tmp_path)
        agg.import_from_tui_db(tui_db)
        assert agg.count() == 1

        # Import again — should skip the already-registered session
        count = agg.import_from_tui_db(tui_db)
        assert count == 0
        assert agg.count() == 1


# ---------------------------------------------------------------------------
# Path separation
# ---------------------------------------------------------------------------


def test_session_dir_is_dot_cdh():
    from cdh.cdh_session_aggregator import CDH_SESSIONS_DIR
    assert CDH_SESSIONS_DIR == Path.home() / ".cdh" / "sessions"


def test_session_dir_not_onecode():
    from cdh.cdh_session_aggregator import CDH_SESSIONS_DIR
    from onecode.config import ONECODE_DIR
    assert CDH_SESSIONS_DIR != ONECODE_DIR / "sessions"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agg(tmp_path, sessions_dir=None):
    from cdh.cdh_session_aggregator import CdhSessionAggregator
    return CdhSessionAggregator(
        sessions_dir=sessions_dir or (tmp_path / "sessions")
    )


def _create_tui_db(path: Path, sessions: list[tuple[str, str, str, str]]):
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            agent_identity TEXT NOT NULL,
            agent_session_id TEXT NOT NULL,
            title TEXT NOT NULL,
            protocol TEXT NOT NULL,
            prompt_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            meta_json TEXT DEFAULT '{}'
        )
        """
    )
    for agent, agent_identity, agent_session_id, title in sessions:
        conn.execute(
            "INSERT INTO sessions (agent, agent_identity, agent_session_id, title, protocol) VALUES (?, ?, ?, ?, 'acp')",
            (agent, agent_identity, agent_session_id, title),
        )
    conn.commit()
    conn.close()
