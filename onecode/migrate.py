"""onecode legacy migration — move onecode's private state from ~/.cdh/ to ~/.onecode/.

This is a ONE-TIME migration triggered at first startup after upgrade.
It only moves directories owned by onecode (logs, traces, memory,
snapshots, mcps, models, onecode.config.yaml). cdh platform directories
(projects, state, sessions) are left untouched.  Session JSON is owned
by the cdh platform layer (B mapping mode), not by individual engines.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

logger = logging.getLogger("onecode.migrate")

# Directories/state that belong to onecode and should be migrated
# NOTE: sessions is deliberately excluded — it belongs to the cdh
# platform layer (B mapping mode), not to any individual engine.
_ONECODE_PRIVATE_DIRS = {
    "logs",
    "traces",
    "memory",
    "snapshots",
    "mcps",
    "models",
}

# cdh platform directories — NEVER touch
_CDH_PLATFORM_DIRS = {"projects", "state"}

# Dotfiles that belong to onecode (at the ~/.cdh/ root level)
_ONECODE_DOTFILES = {"onecode.config.yaml"}


def migrate_legacy_cdh_to_onecode(
    legacy_dir: Path | None = None,
    target_dir: Path | None = None,
) -> str | None:
    """Migrate onecode's private state from ~/.cdh/ to ~/.onecode/.

    Args:
        legacy_dir: Source directory (default ~/.cdh/).
        target_dir: Target directory (default ~/.onecode/).

    Returns:
        Info/warning message string, or None if no migration needed.
    """
    legacy = (legacy_dir or Path.home() / ".cdh").resolve()
    target = (target_dir or Path.home() / ".onecode").resolve()

    # Nothing to migrate
    if not legacy.exists():
        return None

    # Already migrated (marker exists)
    migrated_marker = target / ".migrated_from"
    if migrated_marker.exists():
        return None

    # Both exist but no marker → user may have manually set up ~/.onecode/
    if target.exists():
        # Check if target has any onecode dirs already
        has_content = any(
            (target / d).exists() for d in _ONECODE_PRIVATE_DIRS
        ) or target / "onecode.config.yaml" in target.iterdir()
        if has_content:
            return None  # 各自独立运行，无需迁移
        # Target exists but empty — safe to proceed

    # Perform migration
    target.mkdir(parents=True, exist_ok=True)
    migrated_items = []

    # Migrate private subdirectories
    for dir_name in _ONECODE_PRIVATE_DIRS:
        src = legacy / dir_name
        if src.exists() and src.is_dir():
            dst = target / dir_name
            if dst.exists():
                # Merge contents (don't overwrite existing)
                for item in src.iterdir():
                    dst_item = dst / item.name
                    if not dst_item.exists():
                        shutil.move(str(item), str(dst_item))
            else:
                shutil.move(str(src), str(dst))
            migrated_items.append(dir_name)

    # Migrate onecode dotfiles
    for fname in _ONECODE_DOTFILES:
        src = legacy / fname
        if src.exists() and src.is_file():
            dst = target / fname
            if not dst.exists():
                shutil.move(str(src), str(dst))
                migrated_items.append(fname)

    # Write migration marker
    marker_data = {
        "migrated_from": str(legacy),
        "migrated_to": str(target),
        "items": sorted(migrated_items),
        "preserved_on_legacy": sorted(_CDH_PLATFORM_DIRS),
    }
    migrated_marker.write_text(
        json.dumps(marker_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if migrated_items:
        msg = (
            f"⚠ Migrated onecode state from {legacy} → {target}: "
            f"{', '.join(migrated_items)}. "
            f"cdh platform dirs ({', '.join(_CDH_PLATFORM_DIRS)}) preserved at {legacy}."
        )
        logger.warning(msg)
        return msg

    return None
