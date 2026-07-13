from __future__ import annotations

import re
from pathlib import Path


def load_project_doc(workspace_root: Path) -> str:
    """Read ``AGENTS.md`` at the project root if present.

    Convention mirrors ``AGENTS.md`` / ``CLAUDE.md``: exactly one file at
    the workspace root that all AI agents must read.  Unlike skills,
    this is not registered — it's injected directly as project context.

    If the document contains backtick-enclosed references to ``SKILL.md``
    files (e.g. `` `ai-dlc-skill/SKILL.md` ``), the loader attempts to
    resolve each reference relative to the workspace root or the loader's
    own package location and appends the referenced content.
    """
    path = workspace_root.resolve() / "AGENTS.md"
    if not path.exists():
        return ""
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return ""

    # Resolve any backtick-enclosed SKILL.md references
    script_dir = Path(__file__).resolve().parent
    for ref in _extract_skill_refs(content):
        skill_path = _resolve_skill_ref(ref, workspace_root, script_dir)
        if skill_path is not None:
            try:
                skill_content = skill_path.read_text(encoding="utf-8")
                content += f"\n\n<!-- PROJECT_SKILL:{skill_path.name} -->\n{skill_content}"
            except Exception:
                pass

    return content


def _extract_skill_refs(content: str) -> list[str]:
    """Extract backtick-enclosed paths ending with ``SKILL.md``."""
    return re.findall(r"`([^`]+SKILL\.md)`", content)


def _resolve_skill_ref(ref: str, workspace_root: Path, script_dir: Path) -> Path | None:
    """Resolve a SKILL.md reference.

    Tries in order:
    1. Relative to workspace root
    2. Walk up from the loader's script directory (supports -e installs)
    """
    candidate = workspace_root / ref
    if candidate.exists():
        return candidate

    current = script_dir
    for _ in range(10):
        candidate = current / ref
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None
