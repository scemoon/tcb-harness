from __future__ import annotations

from pathlib import Path


def load_project_doc(workspace_root: Path) -> str:
    """Read ``AGENTS.md`` at the project root if present.

    Convention mirrors ``AGENTS.md`` / ``CLAUDE.md``: exactly one file at
    the workspace root that all AI agents must read.  Unlike skills,
    this is not registered — it's injected directly as project context.
    """
    path = workspace_root.resolve() / "AGENTS.md"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""
