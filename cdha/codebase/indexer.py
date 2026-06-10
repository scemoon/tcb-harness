from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pathspec import PathSpec
from pathspec.patterns import GitWildMatchPattern

from cdha.codebase.chunker import chunk_file
from cdha.config import CodebaseConfig
from cdha.codebase.storage import CodebaseStorage

logger = logging.getLogger(__name__)


@dataclass
class IndexResult:
    total_files: int = 0
    indexed_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    total_chunks: int = 0
    duration_ms: float = 0.0
    errors: list[str] = field(default_factory=list)


class CodebaseIndexer:
    def __init__(self, project_dir: Path, config: CodebaseConfig):
        self.project_dir = project_dir.resolve()
        self.config = config
        self.storage = CodebaseStorage(project_dir)
        self._spec = self._build_spec()

    def _build_spec(self) -> Optional[PathSpec]:
        patterns = self.config.exclude_patterns
        if not patterns:
            return None
        return PathSpec.from_lines(GitWildMatchPattern, patterns)

    def walk_files(self) -> list[Path]:
        include_exts = {ext.lower() for ext in self.config.include_extensions}
        files: list[Path] = []
        for root, dirs, filenames in os.walk(self.project_dir):
            root_path = Path(root)
            rel_root = root_path.relative_to(self.project_dir)
            dirs[:] = [
                d for d in dirs
                if not self._is_excluded(str(rel_root / d))
            ]
            for fname in filenames:
                fpath = root_path / fname
                rel = fpath.relative_to(self.project_dir)
                if self._is_excluded(str(rel)):
                    continue
                if fpath.suffix.lower() in include_exts:
                    files.append(fpath)
        return files

    def _is_excluded(self, rel_path: str) -> bool:
        if self._spec is None:
            return False
        return self._spec.match_file(rel_path)

    def needs_reindex(self, file_path: Path) -> bool:
        if not file_path.exists():
            return True
        stored_mtime = self.storage.get_file_mtime(str(file_path))
        actual_mtime = file_path.stat().st_mtime
        return actual_mtime > stored_mtime

    async def index(self, force: bool = False) -> IndexResult:
        result = IndexResult()
        start = time.monotonic()

        if force:
            self.storage.clear_all()

        files = self.walk_files()
        result.total_files = len(files)

        for fpath in files:
            if not force and not self.needs_reindex(fpath):
                result.skipped_files += 1
                continue

            try:
                mtime = fpath.stat().st_mtime
                chunks = chunk_file(
                    fpath,
                    strategy=self.config.chunk_strategy,
                    chunk_lines=self.config.chunk_lines,
                    overlap=self.config.chunk_overlap,
                )
                if chunks:
                    self.storage.save_chunks(chunks, mtime=mtime)
                result.indexed_files += 1
                result.total_chunks += len(chunks)
            except Exception as e:
                logger.warning("Failed to index %s: %s", fpath, e)
                result.failed_files += 1
                result.errors.append(f"{fpath}: {e}")

        result.duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            "Indexed %d files (%d skipped, %d failed) → %d chunks in %.0fms",
            result.indexed_files, result.skipped_files, result.failed_files,
            result.total_chunks, result.duration_ms,
        )
        return result

    async def index_file(self, file_path: Path) -> None:
        if not file_path.exists():
            self.storage.remove_file(str(file_path))
            return
        include_exts = {ext.lower() for ext in self.config.include_extensions}
        if file_path.suffix.lower() not in include_exts:
            self.storage.remove_file(str(file_path))
            return
        try:
            mtime = file_path.stat().st_mtime
            chunks = chunk_file(
                file_path,
                strategy=self.config.chunk_strategy,
                chunk_lines=self.config.chunk_lines,
                overlap=self.config.chunk_overlap,
            )
            if chunks:
                self.storage.save_chunks(chunks, mtime=mtime)
            else:
                self.storage.remove_file(str(file_path))
        except Exception as e:
            logger.warning("Failed to index %s: %s", file_path, e)
