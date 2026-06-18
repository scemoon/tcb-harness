"""
CDH Memory - Layered Long-term Memory for AI Agents

Based on TencentDB-Agent-Memory architecture:
- L0: Raw conversation
- L1: Atomic facts
- L2: Scenarios
- L3: Personas

With symbolic short-term memory (Mermaid canvas + context offloading)
"""

from onecode.memory.pyramid import MemoryPyramid, MemoryLayer, MemoryEntry
from onecode.memory.symbolic import SymbolicMemory, MermaidCanvas, NodeType
from onecode.memory.offload import ContextOffloader, OffloadConfig, ToolCallExtractor
from onecode.memory.recall import HybridRecall, BM25, RecallResult
from onecode.memory.backend import MemoryBackend

__all__ = [
    "MemoryPyramid",
    "MemoryLayer",
    "MemoryEntry",
    "SymbolicMemory",
    "MermaidCanvas",
    "NodeType",
    "ContextOffloader",
    "OffloadConfig",
    "ToolCallExtractor",
    "HybridRecall",
    "BM25",
    "RecallResult",
    "MemoryBackend",
]


class AgentMemory:
    """
    Unified memory interface combining layered long-term memory
    with symbolic short-term memory and hybrid recall.
    """

    def __init__(self, storage_path=None):
        from onecode.config import CLOUD_DEV_HARNESS_DIR
        self.storage_path = storage_path or (CLOUD_DEV_HARNESS_DIR / "memory")
        self.backend = MemoryBackend(self.storage_path / "memory.db")
        self.pyramid = MemoryPyramid(self.storage_path)
        self.symbolic = SymbolicMemory()
        self.offloader = ContextOffloader(self.storage_path / "refs")
        self.recall = HybridRecall()

    def remember(self, layer: MemoryLayer, content: str, metadata: dict = None, parent_id: str = None) -> MemoryEntry:
        entry = self.pyramid.add(layer, content, metadata, parent_id)
        self.backend.add_entry(
            entry.id,
            layer.value,
            content,
            metadata,
            parent_id,
            entry.result_ref,
        )
        self.recall.add_documents([content], [entry.id], {entry.id: metadata or {}})
        return entry

    def search_memories(self, query: str, top_k: int = 5) -> list[RecallResult]:
        return self.recall.hybrid_recall(query, top_k)

    def remember_conversation(self, conversation_id: str, messages: list[dict]) -> MemoryEntry:
        content = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages)
        entry = self.remember(MemoryLayer.L0_CONVERSATION, content, {"conversation_id": conversation_id})
        return entry

    def extract_atoms(self, conversation_id: str, max_atoms: int = 20) -> list[MemoryEntry]:
        return self.pyramid.extract_atoms_from_conversation(conversation_id, max_atoms)

    def build_scenario(self, name: str, atom_ids: list[str]) -> MemoryEntry:
        scenario = self.pyramid.build_scenario_from_atoms(atom_ids, name)
        self.backend.add_entry(scenario.id, MemoryLayer.L2_SCENARIO.value, scenario.content, scenario.metadata)
        return scenario

    def build_persona(self, name: str, scenario_ids: list[str]) -> MemoryEntry:
        persona = self.pyramid.build_persona_from_scenarios(scenario_ids, name)
        self.backend.add_entry(persona.id, MemoryLayer.L3_PERSONA.value, persona.content, persona.metadata)
        return persona

    def offload_and_symbolize(self, node_id: str, verbose_content: str, task_label: str) -> str:
        ref_path = self.symbolic.offload_log(node_id, verbose_content)
        self.backend.save_ref(node_id, verbose_content)
        self.symbolic.create_result_node(task_label, verbose_content)
        return ref_path

    def get_canvas(self) -> str:
        return self.symbolic.get_canvas_markdown()

    def drill_down(self, entry_id: str) -> list[MemoryEntry]:
        return self.pyramid.drill_down(entry_id)