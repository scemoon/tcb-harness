from __future__ import annotations

import re
import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class OffloadConfig:
    enabled: bool = True
    mild_ratio: float = 0.5
    aggressive_ratio: float = 0.85
    mmd_max_token_ratio: float = 0.2


class ContextOffloader:
    def __init__(
        self,
        refs_dir: Optional[Path] = None,
        config: Optional[OffloadConfig] = None,
    ):
        from onecode.config import CLOUD_DEV_HARNESS_DIR
        self.refs_dir = refs_dir or (CLOUD_DEV_HARNESS_DIR / "memory" / "refs")
        self.refs_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or OffloadConfig()
        self._offloaded_refs: dict[str, Path] = {}

    def should_offload(self, context_length: int, max_tokens: int) -> tuple[bool, str]:
        if not self.config.enabled:
            return False, "disabled"

        ratio = context_length / max_tokens if max_tokens > 0 else 0

        if ratio >= self.config.aggressive_ratio:
            return True, "aggressive"
        elif ratio >= self.config.mild_ratio:
            return True, "mild"
        return False, "none"

    def offload_content(
        self,
        content: str,
        node_id: str,
        file_pattern: str = "*.md",
    ) -> str:
        ext = file_pattern.replace("*", "md")
        ref_file = self.refs_dir / f"{node_id}.{ext}"
        ref_file.write_text(content, encoding="utf-8")
        self._offloaded_refs[node_id] = ref_file
        return f"See refs/{node_id}.{ext}"

    def recall_ref(self, node_id: str) -> Optional[str]:
        ref_file = self._offloaded_refs.get(node_id)
        if ref_file and ref_file.exists():
            return ref_file.read_text(encoding="utf-8")
        for ext in ["md", "txt", "log"]:
            alt_path = self.refs_dir / f"{node_id}.{ext}"
            if alt_path.exists():
                return alt_path.read_text(encoding="utf-8")
        return None

    def list_offloaded(self) -> list[str]:
        return list(self._offloaded_refs.keys())

    def cleanup_old_refs(self, max_age_hours: int = 24) -> int:
        import time
        from datetime import datetime, timezone
        removed = 0
        for ref_file in self.refs_dir.iterdir():
            if ref_file.is_file():
                age_hours = (time.time() - ref_file.stat().st_mtime) / 3600
                if age_hours > max_age_hours:
                    ref_file.unlink()
                    node_id = ref_file.stem
                    if node_id in self._offloaded_refs:
                        del self._offloaded_refs[node_id]
                    removed += 1
        return removed


class ToolCallExtractor:
    PATTERNS = [
        re.compile(r'\[TOOL_CALL\]\s*(\w+)\s*:\s*(.+)', re.DOTALL),
        re.compile(r'"tool":\s*"(\w+)"[^}]*"args":\s*({.+?})', re.DOTALL),
        re.compile(r'(\w+)\((.*?)\)\s*=>\s*(.+)', re.DOTALL),
    ]

    @classmethod
    def extract_calls(cls, text: str) -> list[dict]:
        calls = []
        for pattern in cls.PATTERNS:
            matches = pattern.finditer(text)
            for match in matches:
                if pattern == cls.PATTERNS[0]:
                    calls.append({"tool": match.group(1), "args": match.group(2)})
                elif pattern == cls.PATTERNS[1]:
                    calls.append({"tool": match.group(1), "args": match.group(2)})
                else:
                    calls.append({"tool": match.group(1), "args": match.group(2), "result": match.group(3)})
        return calls

    @classmethod
    def format_as_mermaid(cls, calls: list[dict]) -> str:
        lines = ["graph LR"]
        for i, call in enumerate(calls):
            node_id = f"C{i:03d}"
            tool_name = call.get("tool", "unknown")
            lines.append(f"    {node_id}[{tool_name}]")
            if i > 0:
                prev_id = f"C{i-1:03d}"
                lines.append(f"    {prev_id} --> {node_id}")
        return "\n".join(lines)