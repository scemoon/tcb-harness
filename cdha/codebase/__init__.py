from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from cdha.codebase.chunker import CodeChunk
from cdha.config import CodebaseConfig
from cdha.codebase.indexer import CodebaseIndexer
from cdha.codebase.retriever import CodebaseRetriever
from cdha.codebase.storage import CodebaseStorage
from cdha.codebase.tools import CodebaseSearchTool

logger = logging.getLogger(__name__)

_MAX_INJECT_TOKENS = 2000


class CodebaseEngine:
    def __init__(self, project_dir: Path, config: Optional[CodebaseConfig] = None):
        self.project_dir = project_dir.resolve()
        self.config = config or CodebaseConfig()
        self.storage = CodebaseStorage(project_dir)
        self.indexer = CodebaseIndexer(project_dir, self.config)
        self.retriever = CodebaseRetriever(project_dir, self.config)
        self._indexed = False

    async def ensure_indexed(self, force: bool = False) -> None:
        if self._indexed and not force:
            return
        result = await self.indexer.index(force=force)
        self._indexed = True
        self.retriever.mark_dirty()
        return result

    async def retrieve(self, query: str, top_k: Optional[int] = None) -> list[CodeChunk]:
        await self.ensure_indexed()
        return await self.retriever.retrieve(query, top_k=top_k)

    def format_context(self, chunks: list[CodeChunk], max_tokens: int = _MAX_INJECT_TOKENS) -> str:
        if not chunks:
            return ""
        parts: list[str] = []
        token_budget = max_tokens
        for c in chunks:
            header = f"<chunk file=\"{c.file_path}\" lines=\"{c.start_line}-{c.end_line}\">"
            footer = "</chunk>"
            chunk_text = f"{header}\n{c.content}\n{footer}"
            estimated_tokens = len(chunk_text) // 4 + 1
            if estimated_tokens > token_budget:
                if not parts:
                    trimmed = c.content[:token_budget * 4]
                    chunk_text = f"{header}\n{trimmed}\n{footer}"
                    parts.append(chunk_text)
                break
            parts.append(chunk_text)
            token_budget -= estimated_tokens
        return "<codebase_context>\n" + "\n".join(parts) + "\n</codebase_context>"


__all__ = [
    "CodebaseEngine",
    "CodebaseConfig",
    "CodeChunk",
    "CodebaseIndexer",
    "CodebaseRetriever",
    "CodebaseStorage",
    "CodebaseSearchTool",
]
