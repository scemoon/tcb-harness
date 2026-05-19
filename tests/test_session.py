import pytest
from pathlib import Path
from cdh.storage.session import SessionStore


def test_create_session(tmp_path):
    store = SessionStore(tmp_path / "test.db")
    record = store.create("test-session", mode="plan")
    assert record.name == "test-session"
    assert record.mode == "plan"
    assert record.id is not None


def test_list_sessions(tmp_path):
    store = SessionStore(tmp_path / "test.db")
    store.create("session-a")
    store.create("session-b")
    sessions = store.list_all()
    assert len(sessions) == 2


def test_load_session(tmp_path):
    store = SessionStore(tmp_path / "test.db")
    created = store.create("load-me")
    loaded = store.load(created.id)
    assert loaded is not None
    assert loaded.name == "load-me"


def test_delete_session(tmp_path):
    store = SessionStore(tmp_path / "test.db")
    created = store.create("delete-me")
    store.delete(created.id)
    assert store.load(created.id) is None


def test_rename_session(tmp_path):
    store = SessionStore(tmp_path / "test.db")
    created = store.create("old-name")
    store.rename(created.id, "new-name")
    renamed = store.load(created.id)
    assert renamed.name == "new-name"
