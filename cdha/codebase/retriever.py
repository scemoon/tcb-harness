from __future__ import annotations

import json
import logging
import math
from typing import Optional

import httpx

from cdha.codebase.chunker import CodeChunk
from cdha.config import CodebaseConfig
from cdha.codebase.storage import CodebaseStorage
from cdha.memory.recall import BM25

logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class CodebaseRetriever:
    def __init__(self, project_dir, config: CodebaseConfig):
        self.storage = CodebaseStorage(project_dir)
        self.config = config
        self._bm25: Optional[BM25] = None
        self._chunks: list[CodeChunk] = []
        self._dirty = True

    def _ensure_indexed(self) -> None:
        if not self._dirty:
            return
        self._chunks = self.storage.get_all_chunks()
        if self._chunks:
            texts = [c.content for c in self._chunks]
            self._bm25 = BM25()
            self._bm25.index(texts)
        else:
            self._bm25 = None
        self._dirty = False
        logger.debug("BM25 index rebuilt with %d chunks", len(self._chunks))

    def mark_dirty(self) -> None:
        self._dirty = True

    async def retrieve(self, query: str, top_k: Optional[int] = None) -> list[CodeChunk]:
        k = top_k or self.config.top_k
        if not query.strip():
            return []
        retriever_type = self.config.retriever
        if retriever_type == "bm25":
            return self._retrieve_bm25(query, k)
        elif retriever_type == "embedding":
            return await self._retrieve_embedding(query, k) or self._retrieve_bm25(query, k)
        elif retriever_type == "hybrid":
            return await self._retrieve_hybrid(query, k)
        return self._retrieve_bm25(query, k)

    def _retrieve_bm25(self, query: str, top_k: int) -> list[CodeChunk]:
        self._ensure_indexed()
        if not self._bm25 or not self._chunks:
            return []
        results = self._bm25.search(query, top_k=top_k)
        scored: list[tuple[CodeChunk, float]] = []
        for idx, score in results:
            if 0 <= idx < len(self._chunks):
                scored.append((self._chunks[idx], score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scored[:top_k]]

    async def _retrieve_embedding(self, query: str, top_k: int) -> Optional[list[CodeChunk]]:
        self._ensure_indexed()
        if not self._chunks:
            return None

        query_emb = await _get_embedding(query, self.config)
        if query_emb is None:
            return None

        embs = await _get_batch_embeddings([c.content[:1000] for c in self._chunks], self.config)
        if not embs or len(embs) != len(self._chunks):
            return None

        scored = []
        for i, emb in enumerate(embs):
            if emb is not None:
                score = _cosine_similarity(query_emb, emb)
                scored.append((self._chunks[i], score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scored[:top_k]]

    async def _retrieve_hybrid(self, query: str, top_k: int) -> list[CodeChunk]:
        bm25_chunks = self._retrieve_bm25(query, top_k * 2)
        emb_chunks = await self._retrieve_embedding(query, top_k * 2) or []
        seen: set[str] = set()
        merged: list[CodeChunk] = []
        for chunk in bm25_chunks + emb_chunks:
            key = chunk.identifier
            if key not in seen:
                seen.add(key)
                merged.append(chunk)
        return merged[:top_k]


EMBEDDING_CACHE: dict[str, list[float]] = {}
BATCH_CACHE: dict[int, Optional[list[float]]] = {}


async def _get_embedding(text: str, config: CodebaseConfig) -> Optional[list[float]]:
    if text in EMBEDDING_CACHE:
        return EMBEDDING_CACHE[text]
    try:
        from cdha.config import load_config
        cfg = load_config()
        provider_name = config.embedding_provider or cfg.default_provider
        pcfg = cfg.providers.get(provider_name)
        if not pcfg:
            return None
        if provider_name == "openai":
            emb = await _openai_embed(text, pcfg.api_key or "", pcfg.endpoint or "")
        elif provider_name == "ollama":
            emb = await _ollama_embed(text, pcfg.endpoint or "http://localhost:11434")
        else:
            emb = await _openai_embed(text, pcfg.api_key or "", pcfg.endpoint or "")
        if emb is not None:
            EMBEDDING_CACHE[text] = emb
        return emb
    except Exception as e:
        logger.warning("Embedding failed: %s", e)
        return None


async def _get_batch_embeddings(texts: list[str], config: CodebaseConfig) -> list[Optional[list[float]]]:
    global BATCH_CACHE
    key = hash(tuple(texts))
    if key in BATCH_CACHE:
        return BATCH_CACHE[key]

    from cdha.config import load_config
    cfg = load_config()
    provider_name = config.embedding_provider or cfg.default_provider
    pcfg = cfg.providers.get(provider_name)

    if provider_name == "ollama" and pcfg:
        embs = await _ollama_batch_embed(texts, pcfg.endpoint or "http://localhost:11434")
    else:
        embs = []
        for t in texts:
            emb = await _get_embedding(t, config)
            embs.append(emb)

    BATCH_CACHE[key] = embs
    return embs


async def _openai_embed(text: str, api_key: str, endpoint: str) -> Optional[list[float]]:
    url = f"{endpoint.rstrip('/')}/embeddings"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"input": text, "model": "text-embedding-3-small"},
        )
        data = resp.json()
        emb = data.get("data", [{}])[0].get("embedding")
        return emb if emb else None


async def _ollama_embed(text: str, endpoint: str) -> Optional[list[float]]:
    url = f"{endpoint.rstrip('/')}/api/embeddings"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            url,
            json={"model": "nomic-embed-text", "prompt": text},
        )
        data = resp.json()
        emb = data.get("embedding")
        return emb if emb else None


async def _ollama_batch_embed(texts: list[str], endpoint: str) -> list[Optional[list[float]]]:
    embs = []
    for t in texts:
        emb = await _ollama_embed(t, endpoint)
        embs.append(emb)
    return embs
