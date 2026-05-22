from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from cdh.agent.tools.errors import ToolPermissionError


class PermissionResult(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


def _resolve_path(p: str | Path) -> Path:
    return Path(p).expanduser().resolve()


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


@dataclass
class ToolPermissionContext:
    deny_names: frozenset[str] = field(default_factory=frozenset)
    deny_prefixes: tuple[str, ...] = ()
    workspace_root: Optional[Path] = None
    additional_working_directories: tuple[Path, ...] = ()

    @classmethod
    def from_iterables(
        cls,
        deny_names: list[str] | None = None,
        deny_prefixes: list[str] | None = None,
        *,
        workspace_root: str | Path | None = None,
        additional_working_directories: list[str | Path] | None = None,
    ) -> ToolPermissionContext:
        return cls(
            deny_names=frozenset(name.lower() for name in (deny_names or [])),
            deny_prefixes=tuple(prefix.lower() for prefix in (deny_prefixes or [])),
            workspace_root=_resolve_path(workspace_root) if workspace_root else None,
            additional_working_directories=tuple(
                _resolve_path(p) for p in (additional_working_directories or [])
            ),
        )

    def blocks_tool(self, tool_name: str) -> bool:
        lowered = tool_name.lower()
        return lowered in self.deny_names or any(
            lowered.startswith(prefix) for prefix in self.deny_prefixes
        )

    def allowed_roots(self) -> tuple[Path, ...]:
        roots: list[Path] = []
        if self.workspace_root is not None:
            roots.append(self.workspace_root)
        roots.extend(self.additional_working_directories)
        return tuple(roots)

    def ensure_path_allowed(self, path: str | Path) -> Path:
        resolved = _resolve_path(path)
        roots = self.allowed_roots()
        if not roots:
            return resolved
        if any(_is_within(resolved, root) for root in roots):
            return resolved
        roots_str = ", ".join(str(r) for r in roots)
        raise ToolPermissionError(
            f"path is outside allowed working directories: {resolved} (allowed: {roots_str})"
        )
