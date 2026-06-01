import pytest
import tempfile
from pathlib import Path

from cdha.memory.pyramid import MemoryPyramid, MemoryLayer, MemoryEntry
from cdha.memory.symbolic import SymbolicMemory, MermaidCanvas, NodeType
from cdha.memory.offload import ContextOffloader, OffloadConfig
from cdha.memory.recall import HybridRecall, BM25, RecallResult
from cdha.memory.backend import MemoryBackend, MemoryRecord
from cdha.memory import AgentMemory


class TestMemoryPyramid:
    def test_create_and_add(self, tmp_path):
        pyramid = MemoryPyramid(tmp_path)
        entry = pyramid.add(MemoryLayer.L0_CONVERSATION, "Test conversation content")
        assert entry.id is not None
        assert entry.layer == MemoryLayer.L0_CONVERSATION
        assert "Test conversation" in entry.content

    def test_list_by_layer(self, tmp_path):
        pyramid = MemoryPyramid(tmp_path)
        pyramid.add(MemoryLayer.L0_CONVERSATION, "Content 1")
        pyramid.add(MemoryLayer.L0_CONVERSATION, "Content 2")
        pyramid.add(MemoryLayer.L1_ATOM, "Atom content")
        l0_entries = pyramid.list_by_layer(MemoryLayer.L0_CONVERSATION)
        assert len(l0_entries) == 2
        l1_entries = pyramid.list_by_layer(MemoryLayer.L1_ATOM)
        assert len(l1_entries) == 1

    def test_drill_down(self, tmp_path):
        pyramid = MemoryPyramid(tmp_path)
        l0 = pyramid.add(MemoryLayer.L0_CONVERSATION, "Original conversation")
        l1 = pyramid.add(MemoryLayer.L1_ATOM, "Extracted atom", parent_id=l0.id)
        chain = pyramid.drill_down(l1.id)
        assert len(chain) == 2
        assert chain[0].id == l0.id
        assert chain[1].id == l1.id


class TestSymbolicMemory:
    def test_create_canvas(self):
        canvas = MermaidCanvas("test-task")
        assert canvas.task_id == "test-task"

    def test_add_nodes_and_edges(self):
        canvas = MermaidCanvas()
        task_id = canvas.add_node(NodeType.TASK, "Implement login")
        action_id = canvas.add_node(NodeType.ACTION, "Write code")
        result_id = canvas.add_node(NodeType.RESULT, "Login works")
        canvas.add_edge(task_id, action_id)
        canvas.add_edge(action_id, result_id)
        assert len(canvas.nodes) == 3
        assert len(canvas.edges) == 2

    def test_mermaid_output(self):
        canvas = MermaidCanvas()
        task_id = canvas.add_node(NodeType.TASK, "Test task")
        result_id = canvas.add_node(NodeType.RESULT, "Done")
        canvas.add_edge(task_id, result_id, "complete")
        mermaid = canvas.to_mermaid()
        assert "graph LR" in mermaid
        assert "Test task" in mermaid
        assert "Done" in mermaid

    def test_offload_and_recall(self):
        symbolic = SymbolicMemory()
        node_id = symbolic.create_result_node("Task result", "Verbose output here...")
        assert symbolic.get_ref_content(node_id) == "Verbose output here..."

    def test_error_node(self):
        symbolic = SymbolicMemory()
        node_id = symbolic.create_error_node("Failed step", "Error: something went wrong")
        assert symbolic.get_ref_content(node_id) == "Error: something went wrong"


class TestContextOffloader:
    def test_should_offload_disabled(self):
        config = OffloadConfig(enabled=False)
        offloader = ContextOffloader(config=config)
        should, reason = offloader.should_offload(1000, 4000)
        assert not should

    def test_should_offload_aggressive(self):
        config = OffloadConfig(enabled=True, aggressive_ratio=0.85)
        offloader = ContextOffloader(config=config)
        should, reason = offloader.should_offload(3500, 4000)
        assert should
        assert reason == "aggressive"

    def test_offload_and_recall(self, tmp_path):
        offloader = ContextOffloader(tmp_path / "refs")
        offloader.config.enabled = True
        ref = offloader.offload_content("Verbose log content", "N001")
        recalled = offloader.recall_ref("N001")
        assert recalled == "Verbose log content"


class TestBM25:
    def test_index_and_search(self):
        bm25 = BM25()
        docs = [
            "Python programming language",
            "Java programming language",
            "Machine learning with Python",
            "Deep learning neural networks",
        ]
        bm25.index(docs)
        results = bm25.search("Python programming", top_k=2)
        assert len(results) <= 2
        assert results[0][0] == 0  # First doc should be top

    def test_empty_query(self):
        bm25 = BM25()
        bm25.index(["Some document about Python", "Another doc"])
        results = bm25.search("xyznonexistent123", top_k=5)
        scores = [s for _, s in results if s > 0]
        assert len(scores) == 0


class TestHybridRecall:
    def test_keyword_recall(self):
        recall = HybridRecall()
        recall.add_documents(
            ["Implement login feature", "Fix bug in auth", "Add tests"],
            ["doc1", "doc2", "doc3"],
        )
        results = recall.keyword_recall("login", top_k=1)
        assert len(results) == 1
        assert results[0].entry_id == "doc1"

    def test_hybrid_recall(self):
        recall = HybridRecall()
        recall.add_documents(
            ["Login page UI", "Authentication flow", "Database schema"],
            ["doc1", "doc2", "doc3"],
        )
        results = recall.hybrid_recall("auth login", top_k=2)
        assert len(results) == 2
        assert results[0].source in ("bm25", "embedding")


class TestMemoryBackend:
    def test_add_and_get_entry(self, tmp_path):
        backend = MemoryBackend(tmp_path / "test.db")
        backend.add_entry("test001", "l0_conversation", "Test content", {"key": "value"})
        with backend.session() as s:
            record = s.query(MemoryRecord).filter_by(id="test001").first()
            assert record is not None
            assert record.content == "Test content"
            assert record.layer == "l0_conversation"

    def test_search_content(self, tmp_path):
        backend = MemoryBackend(tmp_path / "test.db")
        backend.add_entry("s1", "l1_atom", "Python is a programming language")
        backend.add_entry("s2", "l1_atom", "Java is also a programming language")
        with backend.session() as s:
            results = s.query(MemoryRecord).filter(MemoryRecord.content.like("%Python%")).all()
            assert len(results) >= 1

    def test_count_by_layer(self, tmp_path):
        backend = MemoryBackend(tmp_path / "test.db")
        backend.add_entry("c1", "l0_conversation", "Content 1")
        backend.add_entry("c2", "l0_conversation", "Content 2")
        backend.add_entry("a1", "l1_atom", "Atom 1")
        counts = backend.count_by_layer()
        assert counts.get("l0_conversation", 0) == 2
        assert counts.get("l1_atom", 0) == 1


class TestAgentMemory:
    def test_remember_and_recall(self, tmp_path):
        memory = AgentMemory(tmp_path)
        entry = memory.remember(MemoryLayer.L0_CONVERSATION, "User asked about Python")
        assert entry is not None
        results = memory.search_memories("Python")
        assert len(results) >= 1

    def test_remember_conversation(self, tmp_path):
        memory = AgentMemory(tmp_path)
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        entry = memory.remember_conversation("conv123", messages)
        assert entry is not None
        assert "user: Hello" in entry.content

    def test_build_scenario(self, tmp_path):
        memory = AgentMemory(tmp_path)
        atom1 = memory.remember(MemoryLayer.L1_ATOM, "Atom 1 content")
        atom2 = memory.remember(MemoryLayer.L1_ATOM, "Atom 2 content")
        scenario = memory.build_scenario("Test Scenario", [atom1.id, atom2.id])
        assert scenario is not None
        assert "Test Scenario" in scenario.content

    def test_offload_and_symbolize(self, tmp_path):
        memory = AgentMemory(tmp_path)
        ref = memory.offload_and_symbolize("N001", "Long verbose output...", "Task label")
        assert ref is not None
        canvas = memory.get_canvas()
        assert "Task label" in canvas