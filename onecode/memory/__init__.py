"""
CDH Memory - Long-term Conversation Memory for AI Agents

L0: Raw conversation storage with BM25 keyword recall.
"""
from onecode.memory.pyramid import MemoryPyramid, MemoryLayer, MemoryEntry
from onecode.memory.recall import HybridRecall, BM25, RecallResult
from onecode.memory.backend import MemoryBackend

__all__ = [
    "MemoryPyramid",
    "MemoryLayer",
    "MemoryEntry",
    "HybridRecall",
    "BM25",
    "RecallResult",
    "MemoryBackend",
    "AgentMemory",
]


class AgentMemory:
    """
    Unified memory interface combining persistent L0 conversation storage
    with BM25 keyword recall for long-term context.
    """

    def __init__(self, storage_path=None):
        from onecode.config import ONECODE_DIR
        self.storage_path = storage_path or (ONECODE_DIR / "memory")
        self.backend = MemoryBackend(self.storage_path / "memory.db")
        self.pyramid = MemoryPyramid(self.storage_path)
        self.recall = HybridRecall()
        self._warm_recall()

    def _warm_recall(self) -> None:
        records = self.backend.get_all_entries()
        if not records:
            return
        docs: list[str] = []
        ids: list[str] = []
        meta: dict[str, dict] = {}
        for r in records:
            docs.append(r["content"])
            ids.append(r["id"])
            meta[r["id"]] = r.get("metadata_json") or {}
        self.recall.add_documents(docs, ids, meta)

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
