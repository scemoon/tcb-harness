from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class RecallResult:
    entry_id: str
    content: str
    score: float
    source: str
    metadata: dict


class BM25:
    # Hard cap above which ``index()`` refuses to build the inverted index.
    # The original O(V × N) construction of ``doc_freqs`` (set membership
    # over Python lists) becomes effectively uncallable above a few
    # thousand docs — a 79k-chunk corpus (observed in production where
    # sessions kept re-indexing without cleaning the SQLite store) took
    # ~1 hour, blocking the event loop and freezing streaming + cancel.
    # Above this cap we degrade to a no-op index so callers fall back to
    # other retrievers / explicit search instead of hanging the process.
    _MAX_DOCS = 5000

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_lengths: list[int] = []
        self.avgdl: float = 0
        self.doc_freqs: dict[str, int] = {}
        self.num_docs: int = 0
        self.doc_tokens: list[list[str]] = []
        # Tokenize once per doc as ``set`` (not list) so the
        # ``token in doc`` membership check inside the doc_freqs
        # comprehension is O(1) instead of O(doc_len).  This alone takes
        # the 79k-doc construction from ~hours to ~seconds; the hard cap
        # above is a safety net for pathological corpora.
        self._doc_token_sets: list[set[str]] = []

    def index(self, documents: list[str]) -> None:
        if len(documents) > self._MAX_DOCS:
            import logging
            logging.getLogger(__name__).warning(
                "BM25.index refused: %d docs exceeds cap=%d (would block "
                "the event loop for minutes); BM25 search will return no "
                "results. Clean the codebase index or use a smaller "
                "project scope.", len(documents), self._MAX_DOCS,
            )
            self.doc_tokens = []
            self._doc_token_sets = []
            self.doc_lengths = []
            self.avgdl = 0
            self.num_docs = 0
            self.doc_freqs = {}
            return

        self.doc_tokens = [self._tokenize(doc) for doc in documents]
        self._doc_token_sets = [set(t) for t in self.doc_tokens]
        self.doc_lengths = [len(tokens) for tokens in self.doc_tokens]
        self.avgdl = sum(self.doc_lengths) / len(self.doc_lengths) if self.doc_lengths else 0
        self.num_docs = len(documents)

        all_tokens = set()
        for tokens in self._doc_token_sets:
            all_tokens.update(tokens)
        self.doc_freqs = {
            token: sum(1 for ts in self._doc_token_sets if token in ts)
            for token in all_tokens
        }

    def _tokenize(self, text: str) -> list[str]:
        text = text.lower()
        tokens = re.findall(r"\b\w+\b", text)
        return tokens

    def score(self, query: str, doc_index: int) -> float:
        query_tokens = self._tokenize(query)
        doc_tokens = self.doc_tokens[doc_index]
        doc_len = self.doc_lengths[doc_index]
        score = 0.0

        for qt in query_tokens:
            if qt not in self.doc_freqs:
                continue
            df = self.doc_freqs[qt]
            idf = math.log((self.num_docs - df + 0.5) / (df + 0.5) + 1)
            tf = doc_tokens.count(qt)
            tf_score = (tf * (self.k1 + 1)) / (tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl))
            score += idf * tf_score
        return score

    def search(self, query: str, top_k: int = 5) -> list[tuple[int, float]]:
        scores = [(i, self.score(query, i)) for i in range(self.num_docs)]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


class HybridRecall:
    def __init__(
        self,
        bm25: Optional[BM25] = None,
        embedding_fn: Optional[callable] = None,
    ):
        self.bm25 = bm25 or BM25()
        self.embedding_fn = embedding_fn
        self._documents: list[str] = []
        self._embeddings: list[list[float]] = []
        self._entry_ids: list[str] = []
        self._metadata: dict[str, dict] = {}

    def add_documents(self, documents: list[str], entry_ids: Optional[list[str]] = None, metadata: Optional[dict] = None) -> None:
        start_idx = len(self._documents)
        self._documents.extend(documents)
        for i, doc in enumerate(documents):
            eid = entry_ids[i] if entry_ids and i < len(entry_ids) else f"doc_{start_idx + i}"
            self._entry_ids.append(eid)
            if metadata and eid in metadata:
                self._metadata[eid] = metadata[eid]

        self.bm25.index(self._documents)

        if self.embedding_fn:
            for doc in documents:
                emb = self.embedding_fn(doc)
                self._embeddings.append(emb)

    def keyword_recall(self, query: str, top_k: int = 5) -> list[RecallResult]:
        bm25_results = self.bm25.search(query, top_k * 2)
        results = []
        for doc_idx, bm25_score in bm25_results:
            if doc_idx < len(self._entry_ids):
                eid = self._entry_ids[doc_idx]
                results.append(RecallResult(
                    entry_id=eid,
                    content=self._documents[doc_idx],
                    score=bm25_score,
                    source="bm25",
                    metadata=self._metadata.get(eid, {}),
                ))
        return results[:top_k]

    def semantic_recall(self, query: str, top_k: int = 5) -> list[RecallResult]:
        if not self.embedding_fn:
            return []

        query_emb = self.embedding_fn(query)
        similarities = []

        for i, emb in enumerate(self._embeddings):
            sim = self._cosine_similarity(query_emb, emb)
            similarities.append((i, sim))

        similarities.sort(key=lambda x: x[1], reverse=True)
        results = []
        for doc_idx, sim_score in similarities[:top_k]:
            eid = self._entry_ids[doc_idx]
            results.append(RecallResult(
                entry_id=eid,
                content=self._documents[doc_idx],
                score=sim_score,
                source="embedding",
                metadata=self._metadata.get(eid, {}),
            ))
        return results

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0
        return dot / (norm_a * norm_b)

    def hybrid_recall(self, query: str, top_k: int = 5, rrf_k: int = 60) -> list[RecallResult]:
        bm25_results = self.keyword_recall(query, top_k * 2)
        semantic_results = self.semantic_recall(query, top_k * 2)

        rrf_scores: dict[str, float] = {}
        rrf_results: dict[str, RecallResult] = {}

        for rank, result in enumerate(bm25_results):
            score = 1.0 / (rrf_k + rank + 1)
            rrf_scores[result.entry_id] = rrf_scores.get(result.entry_id, 0) + score
            rrf_results[result.entry_id] = result

        for rank, result in enumerate(semantic_results):
            score = 1.0 / (rrf_k + rank + 1)
            rrf_scores[result.entry_id] = rrf_scores.get(result.entry_id, 0) + score
            rrf_results[result.entry_id] = result

        sorted_ids = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return [rrf_results[eid] for eid, _ in sorted_ids[:top_k]]

    def clear(self) -> None:
        self._documents = []
        self._embeddings = []
        self._entry_ids = []
        self._metadata = {}
        self.bm25 = BM25()