from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import yaml


def _walk_up_parents(workspace_root: Path):
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
    CDH_DIRNAME = ".cdh"
    STATE_FILENAME = "state.json"
    LAST_SESSION_FILENAME = "last_session.json"
    TODOS_FILENAME = "todos.json"
    PERMISSIONS_FILENAME = "permissions.json"

    # ── discovery ──────────────────────────────────────────────

    @staticmethod
    def find_cdh_dir(workspace_root: Path) -> Optional[Path]:
        for parent in _walk_up_parents(workspace_root):
            candidate = parent / CdhProjectLoader.CDH_DIRNAME
            if candidate.is_dir():
                return candidate
        return None

    @staticmethod
    def find_cdh_dir_for_todos(workspace_root: Path) -> Optional[Path]:
        candidate = workspace_root.resolve() / CdhProjectLoader.CDH_DIRNAME
        return candidate if candidate.is_dir() else None

    # ── file readers ───────────────────────────────────────────

    @staticmethod
    def load_project_config(cdh_dir: Path) -> dict:
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
        state_path = cdh_dir / CdhProjectLoader.STATE_FILENAME
        if state_path.exists():
            try:
                return json.loads(state_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    @staticmethod
    def save_state(cdh_dir: Path, state_data: dict) -> None:
        path = cdh_dir / CdhProjectLoader.STATE_FILENAME
        path.write_text(
            json.dumps(state_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── last-session persistence ───────────────────────────────

    @staticmethod
    def save_last_session(cdh_dir: Path, session_data: dict) -> None:
        path = cdh_dir / CdhProjectLoader.LAST_SESSION_FILENAME
        path.write_text(
            json.dumps(session_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def load_last_session(cdh_dir: Path) -> dict:
        path = cdh_dir / CdhProjectLoader.LAST_SESSION_FILENAME
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    # ── todo persistence ───────────────────────────────────────

    @staticmethod
    def save_todos(cdh_dir: Path, todos_data: dict) -> None:
        path = cdh_dir / CdhProjectLoader.TODOS_FILENAME
        path.write_text(
            json.dumps(todos_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def load_todos(cdh_dir: Path) -> dict:
        path = cdh_dir / CdhProjectLoader.TODOS_FILENAME
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    # ── permission persistence ─────────────────────────────────

    @staticmethod
    def save_permissions(cdh_dir: Path, perm_data: dict) -> None:
        path = cdh_dir / CdhProjectLoader.PERMISSIONS_FILENAME
        path.write_text(
            json.dumps(perm_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def load_permissions(cdh_dir: Path) -> dict:
        path = cdh_dir / CdhProjectLoader.PERMISSIONS_FILENAME
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    # ── public API ─────────────────────────────────────────────

    @staticmethod
    def load_for_workspace(workspace_root: Path) -> str:
        cdh_dir = CdhProjectLoader.find_cdh_dir(workspace_root)
        if cdh_dir is None:
            return ""

        config = CdhProjectLoader.load_project_config(cdh_dir)
        state = CdhProjectLoader.load_project_state(cdh_dir)

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

        parts.append(
            "\n**Important**: Work directly in the project root directory shown above. "
            "Do NOT create a subdirectory named after the project — all files go "
            "directly under the project root."
        )

        return "\n".join(parts)

    # ── phase state management ─────────────────────────────────

    _PHASE_SEQUENCE = ["init", "understand", "plan", "verify", "deliver"]

    @staticmethod
    def advance_phase(workspace_root: Path, phase: str) -> bool:
        """Advance to the next AI-DLC phase. Only single-step forward allowed.

        To reset: call with phase="init".
        """
        cdh_dir = CdhProjectLoader.find_cdh_dir(workspace_root)
        if cdh_dir is None:
            return False
        state = CdhProjectLoader.load_project_state(cdh_dir)
        prev = state.get("current_phase", "")

        if phase == prev:
            return True

        if phase == "init":
            state["current_phase"] = "init"
            state["completed_phases"] = []
            state["gate_results"] = {}
            CdhProjectLoader.save_state(cdh_dir, state)
            return True

        seq = CdhProjectLoader._PHASE_SEQUENCE
        try:
            prev_idx = seq.index(prev)
            target_idx = seq.index(phase)
        except ValueError:
            return False

        if target_idx != prev_idx + 1:
            return False

        if prev and prev != "init":
            completed = state.get("completed_phases", [])
            if prev not in completed:
                completed.append(prev)
                state["completed_phases"] = completed

        state["current_phase"] = phase
        CdhProjectLoader.save_state(cdh_dir, state)
        return True

    @staticmethod
    def record_gate_result(
        workspace_root: Path, gate_name: str, status: str, summary: str = ""
    ) -> bool:
        """Record a quality gate result."""
        cdh_dir = CdhProjectLoader.find_cdh_dir(workspace_root)
        if cdh_dir is None:
            return False
        state = CdhProjectLoader.load_project_state(cdh_dir)
        state.setdefault("gate_results", {})[gate_name] = {
            "status": status,
            "summary": summary,
        }
        CdhProjectLoader.save_state(cdh_dir, state)
        return True

    # ── scaffolding ────────────────────────────────────────────

    @staticmethod
    def init_project(
        workspace_root: Path,
        name: str,
        platform: str = "",
        phase: str = "init",
    ) -> Path:
        workspace_root = workspace_root.resolve()
        existing = CdhProjectLoader.find_cdh_dir(workspace_root)
        if existing is not None:
            if existing.parent != workspace_root:
                import sys as _sys
                print(
                    f"⚠ {workspace_root} is inside an existing project at "
                    f"{existing.parent}. Auto-correcting to use that project.",
                    file=_sys.stderr,
                )
                return existing
            cdh_dir = existing
        else:
            cdh_dir = workspace_root / CdhProjectLoader.CDH_DIRNAME
            cdh_dir.mkdir(parents=True, exist_ok=True)

        config = {"name": name}
        if platform:
            config["platform"] = platform
        if phase:
            config["phase"] = phase
        config_path = cdh_dir / "config.yaml"
        config_path.write_text(yaml.dump(config, default_flow_style=False), encoding="utf-8")

        state = {"current_phase": phase, "completed_phases": [], "gate_results": {}}
        state_path = cdh_dir / CdhProjectLoader.STATE_FILENAME
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        return cdh_dir
