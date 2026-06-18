from __future__ import annotations

import fnmatch
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


ALLOWED_EXTENSIONS = {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".sql", ".sh", ".bash", ".zsh", ".toml", ".ini", ".cfg", ".conf", ".log"}
DEFAULT_MAX_SIZE_MB = 10


@dataclass
class Attachment:
    path: str
    alias: Optional[str] = None
    content: Optional[str] = None
    size: int = 0
    mime_type: Optional[str] = None
    error: Optional[str] = None

    @property
    def name(self) -> str:
        return self.alias or Path(self.path).name

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.path})"


@dataclass
class AttachmentSet:
    _items: list = field(default_factory=list)
    max_size_mb: int = DEFAULT_MAX_SIZE_MB
    allowed_extensions: set = field(default_factory=lambda: ALLOWED_EXTENSIONS.copy())

    def attach(self, path: str, alias: Optional[str] = None) -> Attachment:
        p = Path(path)
        if not p.exists():
            att = Attachment(path=path, alias=alias, error="File not found")
            self._items.append(att)
            return att

        if not p.is_file():
            att = Attachment(path=path, alias=alias, error="Not a file")
            self._items.append(att)
            return att

        size = p.stat().st_size
        if size > self.max_size_mb * 1024 * 1024:
            att = Attachment(path=path, alias=alias, size=size, error=f"File too large (max {self.max_size_mb}MB)")
            self._items.append(att)
            return att

        ext = p.suffix.lower()
        if ext not in self.allowed_extensions and not self._is_text_file(p):
            att = Attachment(path=path, alias=alias, size=size, error="File type not allowed")
            self._items.append(att)
            return att

        try:
            content = p.read_text(encoding="utf-8")
            mime = mimetypes.guess_type(str(p))[0]
            att = Attachment(path=path, alias=alias, content=content, size=size, mime_type=mime)
            self._items.append(att)
            return att
        except Exception as e:
            att = Attachment(path=path, alias=alias, size=size, error=str(e))
            self._items.append(att)
            return att

    def attach_glob(self, pattern: str, base: Optional[str] = None) -> list[Attachment]:
        base_path = Path(base) if base else Path.cwd()
        results = []
        for p in base_path.glob(pattern):
            if p.is_file():
                results.append(self.attach(str(p)))
        return results

    def get(self, index: int) -> Optional[Attachment]:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def list(self) -> list[Attachment]:
        return self._items

    def clear(self) -> None:
        self._items = []

    def remove(self, index: int) -> bool:
        if 0 <= index < len(self._items):
            self._items.pop(index)
            return True
        return False

    def get_context_text(self) -> str:
        parts = []
        for i, att in enumerate(self._items):
            if att.error:
                parts.append(f"[Attachment {i+1}] {att.display_name}: ERROR - {att.error}")
            else:
                parts.append(f"[Attachment {i+1}] {att.display_name}:\n```\n{att.content[:2000]}{'...' if len(att.content) > 2000 else ''}\n```")
        return "\n\n".join(parts) if parts else ""

    def _is_text_file(self, p: Path) -> bool:
        try:
            with open(str(p), "r", encoding="utf-8") as f:
                f.read(1024)
            return True
        except Exception:
            return False