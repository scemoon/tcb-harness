"""onecode bootstrap — ensures ai-dlc-skill is installed in the cdh platform pool.

Called at onecode startup (or cdh launch) to sync the ai-dlc-skill version
from the repository source (ai-dlc-skill/) to ~/.cdh/skills/ai-dlc-skill/.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

from cdh.cdh_skill_manager import CdhSkillManager

logger = logging.getLogger("onecode.skills.bootstrap")

SKILL_SOURCE_NAME = "ai-dlc-skill"
DEFAULT_VERSION = "4.0.0"


def get_source_skill_dir(workspace_root: Path) -> Optional[Path]:
    """Walk up from workspace_root to find ai-dlc-skill/ directory."""
    current = workspace_root.resolve()
    # Check current directory
    candidate = current / SKILL_SOURCE_NAME
    if candidate.is_dir() and (candidate / "skill.yaml").exists():
        return candidate
    # Check parent (if in a subdirectory)
    candidate = current.parent / SKILL_SOURCE_NAME
    if candidate.is_dir() and (candidate / "skill.yaml").exists():
        return candidate
    # Check git root
    try:
        git_root = next(
            p for p in current.parents if (p / ".git").exists()
        )
        candidate = git_root / SKILL_SOURCE_NAME
        if candidate.is_dir() and (candidate / "skill.yaml").exists():
            return candidate
    except StopIteration:
        pass
    return None


def get_source_version(source_dir: Path) -> str:
    """Read metadata.version from source skill.yaml."""
    try:
        skill_yaml = source_dir / "skill.yaml"
        data = yaml.safe_load(skill_yaml.read_text(encoding="utf-8")) or {}
        return data.get("metadata", {}).get("version", DEFAULT_VERSION)
    except Exception:
        return DEFAULT_VERSION


def ensure_ai_dlc_skill(workspace_root: Path | None = None) -> None:
    """Bootstrap ai-dlc-skill into cdh platform pool.

    Compares source version with installed version. If missing or outdated,
    installs via CdhSkillManager. Return value: None (logs warnings on failure).
    """
    root = workspace_root or Path.cwd()
    mgr = CdhSkillManager()

    # Check if already installed and up-to-date
    installed_version = mgr.get_installed_version(SKILL_SOURCE_NAME)

    # Find source directory
    source_dir = get_source_skill_dir(root)
    if source_dir is None:
        if installed_version is None:
            logger.warning(
                "ai-dlc-skill source not found at %s/ai-dlc-skill/ and not installed; "
                "install from repository root to enable AI-DLC methodology.",
                root,
            )
        return

    source_version = get_source_version(source_dir)

    if installed_version == source_version:
        logger.debug("ai-dlc-skill v%s is current, skipping install.", source_version)
        return

    # Install or update
    err = mgr.install(source_dir)
    if err:
        logger.warning("ai-dlc-skill install failed: %s", err)
    else:
        logger.info(
            "ai-dlc-skill installed v%s → %s/%s",
            source_version,
            mgr.skills_dir,
            SKILL_SOURCE_NAME,
        )
