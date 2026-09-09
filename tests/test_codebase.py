"""Tests for onecode codebase subsystem."""

from __future__ import annotations

from pathlib import Path

import pytest

from onecode.codebase.chunker import CodeChunk, chunk_file, chunk_text, detect_language
from onecode.codebase.storage import CodebaseStorage
from onecode.codebase.retriever import CodebaseRetriever
from onecode.config import CodebaseConfig


# ---------------------------------------------------------------------------
# chunker
# ---------------------------------------------------------------------------


def test_detect_language():
    assert detect_language("foo.py") == "python"
    assert detect_language("bar.js") == "javascript"
    assert detect_language("baz.tsx") == "typescriptreact"
    assert detect_language("unknown.xyz") == ""


def test_chunk_text_basic():
    text = "line1\nline2\nline3\nline4\nline5\n"
    chunks = chunk_text(text, "test.py", chunk_lines=3, overlap=1)
    assert len(chunks) >= 2
    assert chunks[0].file_path == "test.py"
    assert chunks[0].language == "python"
    assert "line1" in chunks[0].content
    # overlap means line3 should appear in both first and second chunk
    contents = "|".join(c.content for c in chunks)
    assert "line3" in contents


def test_chunk_text_empty():
    assert chunk_text("", "empty.py") == []


def test_chunk_text_single_line():
    chunks = chunk_text("hello", "a.py", chunk_lines=50, overlap=10)
    assert len(chunks) == 1
    assert chunks[0].content.strip() == "hello"


def test_chunk_file(tmp_path: Path):
    f = tmp_path / "test.py"
    f.write_text("a\nb\nc\nd\ne\nf\ng\nh\ni\nj\n")
    chunks = chunk_file(f, chunk_lines=4, overlap=1)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.file_path == str(f)
        assert c.language == "python"


def test_chunk_file_nonexistent(tmp_path: Path):
    f = tmp_path / "missing.py"
    assert chunk_file(f) == []


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------


def test_storage_save_and_retrieve(tmp_path: Path):
    storage = CodebaseStorage(tmp_path)
    chunks = [
        CodeChunk(file_path="a.py", start_line=1, end_line=5, content="line1\nline2", language="python"),
    ]
    storage.save_chunks(chunks, mtime=100.0)
    assert storage.chunk_count() == 1
    assert storage.file_count() == 1
    loaded = storage.get_all_chunks()
    assert len(loaded) == 1
    assert loaded[0].file_path == "a.py"


def test_storage_update_chunks(tmp_path: Path):
    storage = CodebaseStorage(tmp_path)
    c1 = [CodeChunk("a.py", 1, 5, "old", "python")]
    storage.save_chunks(c1, mtime=1.0)
    c2 = [CodeChunk("a.py", 1, 5, "new", "python")]
    storage.save_chunks(c2, mtime=2.0)
    assert storage.chunk_count() == 1
    assert storage.get_all_chunks()[0].content == "new"


def test_storage_remove_file(tmp_path: Path):
    storage = CodebaseStorage(tmp_path)
    storage.save_chunks([CodeChunk("a.py", 1, 5, "x", "python")], mtime=1.0)
    storage.remove_file("a.py")
    assert storage.chunk_count() == 0


def test_storage_get_file_mtime(tmp_path: Path):
    storage = CodebaseStorage(tmp_path)
    assert storage.get_file_mtime("nope.py") == 0.0
    storage.save_chunks([CodeChunk("a.py", 1, 5, "x", "python")], mtime=42.0)
    assert storage.get_file_mtime("a.py") == 42.0


def test_storage_clear_all(tmp_path: Path):
    storage = CodebaseStorage(tmp_path)
    storage.save_chunks([CodeChunk("a.py", 1, 5, "x", "python")], mtime=1.0)
    storage.clear_all()
    assert storage.chunk_count() == 0


def test_storage_indexed_files(tmp_path: Path):
    storage = CodebaseStorage(tmp_path)
    storage.save_chunks([CodeChunk("a.py", 1, 5, "x", "python")], mtime=1.0)
    storage.save_chunks([CodeChunk("b.py", 1, 3, "y", "python")], mtime=2.0)
    assert storage.get_indexed_files() == {"a.py", "b.py"}


def test_storage_get_chunks_for_file(tmp_path: Path):
    storage = CodebaseStorage(tmp_path)
    storage.save_chunks([
        CodeChunk("a.py", 1, 5, "part1", "python"),
        CodeChunk("a.py", 6, 10, "part2", "python"),
        CodeChunk("b.py", 1, 3, "other", "python"),
    ], mtime=1.0)
    result = storage.get_chunks_for_file("a.py")
    assert len(result) == 2
    assert all(c.file_path == "a.py" for c in result)


# ---------------------------------------------------------------------------
# retriever (BM25)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retriever_empty(tmp_path: Path):
    cfg = CodebaseConfig(enabled=True, retriever="bm25", top_k=5)
    retriever = CodebaseRetriever(tmp_path, cfg)
    results = await retriever.retrieve("hello")
    assert results == []


@pytest.mark.asyncio
async def test_retriever_basic(tmp_path: Path):
    storage = CodebaseStorage(tmp_path)
    storage.save_chunks([
        CodeChunk("a.py", 1, 3, "def hello(): pass", "python"),
        CodeChunk("b.py", 1, 3, "def goodbye(): pass", "python"),
    ], mtime=1.0)
    cfg = CodebaseConfig(enabled=True, retriever="bm25", top_k=5)
    retriever = CodebaseRetriever(tmp_path, cfg)
    results = await retriever.retrieve("hello")
    assert len(results) >= 1
    assert "hello" in results[0].content


# ---------------------------------------------------------------------------
# CodebaseConfig defaults
# ---------------------------------------------------------------------------


def test_codebase_config_defaults():
    cfg = CodebaseConfig()
    assert cfg.enabled is True
    assert cfg.auto_retrieve is True
    assert cfg.chunk_strategy == "line"
    assert cfg.retriever == "bm25"
    assert cfg.top_k == 5
    assert ".git/**" in cfg.exclude_patterns
    assert ".py" in cfg.include_extensions
