from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


_LANG_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".jsx": "javascriptreact",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sql": "sql",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown",
    ".css": "css",
    ".scss": "scss",
    ".html": "html",
    ".svelte": "svelte",
    ".vue": "vue",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".fish": "shell",
    ".tf": "terraform",
    ".tfvars": "terraform",
}


@dataclass
class CodeChunk:
    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str = ""

    @property
    def identifier(self) -> str:
        return f"{self.file_path}:{self.start_line}-{self.end_line}"


def detect_language(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    return _LANG_MAP.get(ext, "")


def chunk_file(file_path: Path, strategy: str = "line",
               chunk_lines: int = 50, overlap: int = 10) -> list[CodeChunk]:
    if strategy == "line":
        return _chunk_by_lines(file_path, chunk_lines, overlap)
    if strategy == "ast":
        return _chunk_by_lines(file_path, chunk_lines, overlap)
    return _chunk_by_lines(file_path, chunk_lines, overlap)


def _chunk_by_lines(file_path: Path, chunk_lines: int, overlap: int) -> list[CodeChunk]:
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        return []

    lines = text.splitlines(keepends=True)
    if not lines:
        return []

    language = detect_language(str(file_path))
    step = max(chunk_lines - overlap, 1)
    chunks: list[CodeChunk] = []

    for start in range(0, len(lines), step):
        end = min(start + chunk_lines, len(lines))
        content = "".join(lines[start:end]).rstrip()
        if not content.strip():
            continue
        chunks.append(CodeChunk(
            file_path=str(file_path),
            start_line=start + 1,
            end_line=end,
            content=content,
            language=language,
        ))
        if end == len(lines):
            break

    return chunks


def chunk_text(text: str, file_path: str, chunk_lines: int = 50, overlap: int = 10) -> list[CodeChunk]:
    lines = text.splitlines(keepends=True)
    if not lines:
        return []

    language = detect_language(file_path)
    step = max(chunk_lines - overlap, 1)
    chunks: list[CodeChunk] = []

    for start in range(0, len(lines), step):
        end = min(start + chunk_lines, len(lines))
        content = "".join(lines[start:end]).rstrip()
        if not content.strip():
            continue
        chunks.append(CodeChunk(
            file_path=file_path,
            start_line=start + 1,
            end_line=end,
            content=content,
            language=language,
        ))
        if end == len(lines):
            break

    return chunks
