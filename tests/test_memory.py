"""Tests for onecode memory subsystem."""

from __future__ import annotations

from pathlib import Path

import pytest

from onecode.memory.recall import BM25, HybridRecall
from onecode.memory.backend import MemoryBackend
from onecode.memory.pyramid import MemoryLayer, MemoryEntry, MemoryPyramid
from onecode.memory import AgentMemory


# ---------------------------------------------------------------------------
# BM25 (also used by codebase retriever)
# ---------------------------------------------------------------------------


def test_bm25_basic():
    bm25 = BM25()
    bm25.index(["hello world", "goodbye world", "hello there"])
    results = bm25.search("hello", top_k=2)
    assert len(results) == 2
    assert results[0][0] in (0, 2)


def test_bm25_empty():
    bm25 = BM25()
    bm25.index([])
    assert bm25.search("hello") == []


def test_bm25_cap():
    bm25 = BM25()
    docs = [f"doc {i}" for i in range(6000)]
    bm25.index(docs)
    assert bm25.num_docs == 0


def test_bm25_score_order():
    bm25 = BM25()
    docs = ["python is great for data science", "i like cats and dogs", "python code is fun"]
    bm25.index(docs)
    results = bm25.search("python", top_k=3)
    scores = [s for _, s in results]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# HybridRecall (used by AgentMemory)
# ---------------------------------------------------------------------------


def test_hybrid_recall_add_and_search():
    hr = HybridRecall()
    hr.add_documents(["hello world", "goodbye world", "python code"])
    results = hr.keyword_recall("hello", top_k=2)
    assert len(results) >= 1
    assert any("hello" in r.content for r in results)


def test_hybrid_recall_empty():
    hr = HybridRecall()
    assert hr.keyword_recall("hello") == []


def test_hybrid_recall_clear():
    hr = HybridRecall()
    hr.add_documents(["hello world"])
    hr.clear()
    assert hr.keyword_recall("hello") == []


# ---------------------------------------------------------------------------
# MemoryLayer, MemoryEntry
# ---------------------------------------------------------------------------


def test_memory_layer_values():
    assert MemoryLayer.L0_CONVERSATION.value == "l0_conversation"


def test_memory_entry_create():
    entry = MemoryEntry.create(MemoryLayer.L0_CONVERSATION, "test content")
    assert entry.layer == MemoryLayer.L0_CONVERSATION
    assert entry.content == "test content"
    assert entry.id is not None
    assert len(entry.id) == 16


def test_memory_entry_roundtrip():
    entry = MemoryEntry.create(MemoryLayer.L0_CONVERSATION, "hello", {"key": "val"})
    d = entry.to_dict()
    restored = MemoryEntry.from_dict(d)
    assert restored.id == entry.id
    assert restored.content == entry.content
    assert restored.metadata == entry.metadata


# ---------------------------------------------------------------------------
# MemoryPyramid (simplified — L0 only)
# ---------------------------------------------------------------------------


def test_pyramid_add_and_get(tmp_path: Path):
    pyramid = MemoryPyramid(tmp_path / "mem")
    entry = pyramid.add(MemoryLayer.L0_CONVERSATION, "hello world")
    assert entry.id is not None
    got = pyramid.get(MemoryLayer.L0_CONVERSATION, entry.id)
    assert got is not None
    assert got.content == "hello world"


def test_pyramid_list_by_layer(tmp_path: Path):
    pyramid = MemoryPyramid(tmp_path / "mem")
    pyramid.add(MemoryLayer.L0_CONVERSATION, "first")
    pyramid.add(MemoryLayer.L0_CONVERSATION, "second")
    entries = pyramid.list_by_layer(MemoryLayer.L0_CONVERSATION)
    assert len(entries) == 2


def test_pyramid_list_recent(tmp_path: Path):
    pyramid = MemoryPyramid(tmp_path / "mem")
    for i in range(5):
        pyramid.add(MemoryLayer.L0_CONVERSATION, f"msg {i}")
    recent = pyramid.list_recent(MemoryLayer.L0_CONVERSATION, limit=3)
    assert len(recent) == 3


def test_pyramid_get_content(tmp_path: Path):
    pyramid = MemoryPyramid(tmp_path / "mem")
    entry = pyramid.add(MemoryLayer.L0_CONVERSATION, "content here")
    content = pyramid.get_content(entry)
    assert "content" in content


# ---------------------------------------------------------------------------
# MemoryBackend
# ---------------------------------------------------------------------------


def test_backend_add_and_get(tmp_path: Path):
    backend = MemoryBackend(tmp_path / "test.db")
    backend.add_entry("id1", "l0_conversation", "hello", {"k": "v"})
    entry = backend.get_entry("id1")
    assert entry is not None
    assert entry["content"] == "hello"
    assert entry["metadata_json"] == {"k": "v"}


def test_backend_count_by_layer(tmp_path: Path):
    backend = MemoryBackend(tmp_path / "test.db")
    backend.add_entry("id1", "l0_conversation", "a")
    backend.add_entry("id2", "l0_conversation", "b")
    counts = backend.count_by_layer()
    assert counts.get("l0_conversation") == 2


def test_backend_get_recent_entries(tmp_path: Path):
    backend = MemoryBackend(tmp_path / "test.db")
    for i in range(5):
        backend.add_entry(f"id{i}", "l0_conversation", f"msg {i}")
    recent = backend.get_recent_entries(limit=3)
    assert len(recent) == 3


def test_backend_delete_entry(tmp_path: Path):
    backend = MemoryBackend(tmp_path / "test.db")
    backend.add_entry("id1", "l0_conversation", "hello")
    assert backend.delete_entry("id1") is True
    assert backend.delete_entry("nonexistent") is False


def test_backend_clear_old_entries(tmp_path: Path):
    backend = MemoryBackend(tmp_path / "test.db")
    for i in range(10):
        backend.add_entry(f"id{i}", "l0_conversation", f"msg {i}")
    removed = backend.clear_old_entries("l0_conversation", keep_last=3)
    assert removed == 7
    counts = backend.count_by_layer()
    assert counts.get("l0_conversation") == 3


# ---------------------------------------------------------------------------
# AgentMemory (integration)
# ---------------------------------------------------------------------------


def test_agent_memory_remember_and_search(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("onecode.config.ONECODE_DIR", tmp_path)
    am = AgentMemory()
    entry = am.remember(MemoryLayer.L0_CONVERSATION, "remember this information", {"source": "test"})
    assert entry.id is not None
    results = am.search_memories("remember", top_k=5)
    assert len(results) >= 1
    assert results[0].entry_id == entry.id


def test_agent_memory_search_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("onecode.config.ONECODE_DIR", tmp_path)
    am = AgentMemory()
    results = am.search_memories("nothing relevant here")
    assert results == []


def test_agent_memory_multi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("onecode.config.ONECODE_DIR", tmp_path)
    am = AgentMemory()
    am.remember(MemoryLayer.L0_CONVERSATION, "python is a programming language")
    am.remember(MemoryLayer.L0_CONVERSATION, "cats are cute animals")
    results = am.search_memories("python", top_k=5)
    assert len(results) >= 1
    assert "python" in results[0].content
