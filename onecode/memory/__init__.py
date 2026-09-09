"""
CDH Memory - Long-term Conversation Memory for AI Agents

L0: Raw conversation storage with BM25 keyword recall.
"""
import json
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

    def __init__(self, storage_path=None, max_docs: int = 5000):
        from onecode.config import ONECODE_DIR
        self.storage_path = storage_path or (ONECODE_DIR / "memory")
        self.max_docs = max_docs
        self.backend = MemoryBackend(self.storage_path / "memory.db")
        self.pyramid = MemoryPyramid(self.storage_path)
        self.recall = HybridRecall()
        self._warm_recall()

    def _index_file(self):
        return self.storage_path / "recall_index.json"

    def _warm_recall(self) -> None:
        idx_file = self._index_file()
        if idx_file.exists():
            try:
                data = json.loads(idx_file.read_text(encoding="utf-8"))
                self.recall = HybridRecall.deserialize(data)
                return
            except Exception:
                pass
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

    def _save_recall_index(self) -> None:
        try:
            idx_file = self._index_file()
            idx_file.write_text(json.dumps(self.recall.serialize(), indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def remember(self, layer: MemoryLayer, content: str, metadata: dict = None, parent_id: str = None, result_ref: str = None) -> MemoryEntry:
        entry = self.pyramid.add(layer, content, metadata, parent_id, result_ref)
        self.backend.add_entry(
            entry.id,
            layer.value,
            content,
            metadata,
            parent_id,
            result_ref,
        )
        self.recall.add_documents([content], [entry.id], {entry.id: metadata or {}})
        self._save_recall_index()
        self._evict_if_needed(layer)
        return entry

    def forget(self, layer: MemoryLayer, entry_id: str) -> bool:
        self.pyramid.remove(layer, entry_id)
        self.backend.delete_entry(entry_id)
        self.recall.remove_documents([entry_id])
        self._save_recall_index()
        return True

    def clear_old_memories(self, layer: MemoryLayer, keep_last: int = 100) -> int:
        removed_count, removed_ids = self.backend.clear_old_entries(layer.value, keep_last)
        if removed_ids:
            for eid in removed_ids:
                self.pyramid.remove(layer, eid)
            self.recall.remove_documents(removed_ids)
            self._save_recall_index()
        return removed_count

    def search_memories(self, query: str, top_k: int = 5) -> list[RecallResult]:
        return self.recall.hybrid_recall(query, top_k)

    def _evict_if_needed(self, layer: MemoryLayer) -> None:
        count = self.backend.count_by_layer().get(layer.value, 0)
        if count > self.max_docs:
            self.clear_old_memories(layer, keep_last=self.max_docs)
