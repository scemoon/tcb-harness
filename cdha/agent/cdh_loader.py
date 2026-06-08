from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import yaml


def _walk_up_parents(workspace_root: Path):
    """Yield workspace root, then git root.

    Unlike :class:`~cdha.skills.loader.SkillLoader` we deliberately do
    **not** yield ``Path.home()`` — the global ``~/.cdh/`` is the CDH
    user-config directory, not a project-level ``.cdh/``, so including it
    would cause false-positive matches.
    """
    current = workspace_root.resolve()
    yield current
    try:
        git_root = next(
            (
                p
                for p in current.parents
                if (p / ".git").exists() or (p / ".hg").exists()
            ),
            None,
        )
        if git_root:
            yield git_root
    except StopIteration:
        pass


class CdhProjectLoader:
    """Load project-level ``.cdh/`` state and inject it into agent context.

    Looks for ``.cdh/`` by walking up from the workspace root to the git
    root, then the home directory — the same pattern used by
    :class:`~cdha.skills.loader.SkillLoader` for skill discovery.
    """

    CDH_DIRNAME = ".cdh"
    LAST_SESSION_FILENAME = "last_session.json"

    # ── discovery ──────────────────────────────────────────────

    @staticmethod
    def find_cdh_dir(workspace_root: Path) -> Optional[Path]:
        """Walk up parent directories looking for a ``.cdh/`` folder.

        Returns the first match (nearest ancestor wins), or ``None`` if
        none of the ancestor trees contain a ``.cdh/`` directory.
        """
        for parent in _walk_up_parents(workspace_root):
            candidate = parent / CdhProjectLoader.CDH_DIRNAME
            if candidate.is_dir():
                return candidate
        return None

    # ── file readers ───────────────────────────────────────────

    @staticmethod
    def load_project_config(cdh_dir: Path) -> dict:
        """Read ``.cdh/config.yaml`` (preferred) or ``.cdh/config.json``."""
        yaml_path = cdh_dir / "config.yaml"
        if yaml_path.exists():
            try:
                return yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            except Exception:
                pass
        json_path = cdh_dir / "config.json"
        if json_path.exists():
            try:
                return json.loads(json_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    @staticmethod
    def load_project_state(cdh_dir: Path) -> dict:
        """Read ``.cdh/state.json``."""
        state_path = cdh_dir / "state.json"
        if state_path.exists():
            try:
                return json.loads(state_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    @staticmethod
    def get_skill_content(cdh_dir: Path) -> str:
        """Read ``.cdh/SKILL.md`` if it exists."""
        skill_path = cdh_dir / "SKILL.md"
        if skill_path.exists():
            try:
                return skill_path.read_text(encoding="utf-8")
            except Exception:
                pass
        return ""

    # ── last-session persistence ───────────────────────────────

    @staticmethod
    def save_last_session(cdh_dir: Path, session_data: dict) -> None:
        """Save last session info to ``.cdh/last_session.json``."""
        path = cdh_dir / CdhProjectLoader.LAST_SESSION_FILENAME
        path.write_text(
            json.dumps(session_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def load_last_session(cdh_dir: Path) -> dict:
        """Load last session info from ``.cdh/last_session.json``."""
        path = cdh_dir / CdhProjectLoader.LAST_SESSION_FILENAME
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    # ── public API ─────────────────────────────────────────────

    @staticmethod
    def load_for_workspace(workspace_root: Path) -> str:
        """Find ``.cdh/`` and return formatted context text, or ``""``."""
        cdh_dir = CdhProjectLoader.find_cdh_dir(workspace_root)
        if cdh_dir is None:
            return ""

        config = CdhProjectLoader.load_project_config(cdh_dir)
        state = CdhProjectLoader.load_project_state(cdh_dir)
        skill = CdhProjectLoader.get_skill_content(cdh_dir)

        parts = ["## Project State (.cdh)"]
        name = config.get("name", cdh_dir.parent.name)
        parts.append(f"- Name: {name}")
        parts.append(f"- Path: {cdh_dir.parent}")
        phase = state.get("current_phase", config.get("phase", ""))
        if phase:
            parts.append(f"- Phase: {phase}")
        platform = config.get("platform", "")
        if platform:
            parts.append(f"- Platform: {platform}")
        if config:
            parts.append(f"- Config: {json.dumps(config, ensure_ascii=False)}")
        if state:
            parts.append(f"- State: {json.dumps(state, ensure_ascii=False)}")
        if skill:
            parts.append(f"\n--- .cdh/SKILL.md ---\n{skill}")

        return "\n".join(parts)

    # ── scaffolding ────────────────────────────────────────────

    @staticmethod
    def init_project(
        workspace_root: Path,
        name: str,
        platform: str = "",
        phase: str = "init",
    ) -> Path:
        """Scaffold a ``.cdh/`` directory inside *workspace_root*.

        Creates ``.cdh/config.yaml``, ``.cdh/state.json``, and a
        stub ``.cdh/SKILL.md``.
        """
        cdh_dir = workspace_root / CdhProjectLoader.CDH_DIRNAME
        cdh_dir.mkdir(parents=True, exist_ok=True)

        config = {"name": name}
        if platform:
            config["platform"] = platform
        if phase:
            config["phase"] = phase
        config_path = cdh_dir / "config.yaml"
        config_path.write_text(yaml.dump(config, default_flow_style=False), encoding="utf-8")

        state = {"current_phase": phase}
        state_path = cdh_dir / "state.json"
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        skill_path = cdh_dir / "SKILL.md"
        if not skill_path.exists():
            skill_path.write_text(
                f"# {name} — Project Instructions\n\n"
                "Add project-specific agent instructions here.\n",
                encoding="utf-8",
            )

        return cdh_dir
