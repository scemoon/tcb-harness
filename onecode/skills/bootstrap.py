"""onecode bootstrap — installs default built-in skills.

Called at onecode startup (or cdh launch) to install built-in skills
(git, shell) into ~/.onecode/skills/ on first run.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger("onecode.skills.bootstrap")


def ensure_onecode_default_skills() -> None:
    """Install built-in skills (git, shell) to ~/.onecode/skills/ on first run."""
    from onecode.config import ONECODE_DIR

    target_dir = ONECODE_DIR / "skills"
    target_dir.mkdir(parents=True, exist_ok=True)

    builtin_root = Path(__file__).resolve().parent.parent / "builtin_skills"
    if not builtin_root.exists():
        return

    for d in sorted(builtin_root.iterdir()):
        if not d.is_dir():
            continue
        if not (d / "skill.yaml").exists():
            continue
        name = d.name
        target = target_dir / name
        if target.exists():
            continue
        shutil.copytree(d, target)
        logger.info("default skill %s installed \u2192 %s/%s", name, target_dir, name)
