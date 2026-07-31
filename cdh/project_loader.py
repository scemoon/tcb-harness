from __future__ import annotations

import hashlib
import json
import os
import tempfile
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
    VALIDATE_HISTORY_FILENAME = "validate_history.json"
    METRICS_FILENAME = "metrics.json"

    STATE_VERSION = 2
    SCHEMA_VERSION = "1.0"

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
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except Exception:
                state = {}
        else:
            state = {}
        return CdhProjectLoader._migrate_state(state)

    @staticmethod
    def save_state(cdh_dir: Path, state_data: dict) -> None:
        path = cdh_dir / CdhProjectLoader.STATE_FILENAME
        migrated = CdhProjectLoader._migrate_state(state_data)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(migrated, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)

    @staticmethod
    def validate_state_schema(cdh_dir: Path) -> tuple[bool, list[str]]:
        from cdh.state_schema import validate_state

        state_path = cdh_dir / CdhProjectLoader.STATE_FILENAME
        if not state_path.exists():
            return False, [f"state file not found: {state_path}"]
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return False, [f"unable to read state.json: {exc}"]
        return validate_state(state)


    @staticmethod
    def _atomic_write(path: Path, data: str) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(data, encoding="utf-8")
        tmp.replace(path)

    # ── validate history / metrics persistence ────────────────

    @staticmethod
    def append_validate_history(cdh_dir: Path, entry: dict) -> None:
        path = cdh_dir / CdhProjectLoader.VALIDATE_HISTORY_FILENAME
        history = CdhProjectLoader.get_validate_history(cdh_dir)
        history.append(entry)
        CdhProjectLoader._atomic_write(
            path,
            json.dumps(history, ensure_ascii=False, indent=2),
        )

    @staticmethod
    def get_validate_history(cdh_dir: Path) -> list:
        path = cdh_dir / CdhProjectLoader.VALIDATE_HISTORY_FILENAME
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except Exception:
                return []
        return []

    @staticmethod
    def record_metrics(cdh_dir: Path, run_entry: dict) -> dict:
        """Record an aggregated metrics entry derived from a validate run.

        ``run_entry`` must contain: ``checks_run`` (list[str]), ``passed`` (bool),
        ``duration_ms`` (int), ``failed_checks`` (list[str]).
        Returns the updated metrics dict.
        """
        path = cdh_dir / CdhProjectLoader.METRICS_FILENAME
        metrics = CdhProjectLoader.get_metrics(cdh_dir)

        metrics["total_runs"] = metrics.get("total_runs", 0) + 1
        metrics["last_run_timestamp"] = run_entry.get("timestamp", "")

        per_check = metrics.setdefault("per_check", {})
        for check in run_entry.get("checks_run", []):
            slot = per_check.setdefault(
                check,
                {
                    "runs": 0,
                    "passes": 0,
                    "fails": 0,
                    "total_duration_ms": 0,
                    "first_failure_at": None,
                },
            )
            slot["runs"] += 1
            if run_entry.get("passed"):
                slot["passes"] += 1
            else:
                slot["fails"] += 1
                if slot["first_failure_at"] is None:
                    slot["first_failure_at"] = run_entry.get("timestamp", "")

        avg_duration = run_entry.get("duration_ms", 0)
        runs_so_far = metrics["total_runs"]
        if runs_so_far > 0:
            metrics["average_duration_ms"] = round(
                (metrics.get("average_duration_ms", 0) * (runs_so_far - 1) + avg_duration)
                / runs_so_far
            )

        mttd = metrics.setdefault("mttd_per_check", {})
        for failed in run_entry.get("failed_checks", []):
            slot = per_check.get(failed, {})
            if slot.get("first_failure_at") and slot.get("fails", 0) > 0:
                # MTTD proxy: average ms-to-first-failure across runs so far.
                # We accumulate total ms at first failure for this check.
                mttd.setdefault(failed, {"accumulated_ms": 0, "samples": 0})
                mttd[failed]["accumulated_ms"] += avg_duration
                mttd[failed]["samples"] += 1

        for check, slot_mttd in mttd.items():
            samples = slot_mttd.get("samples", 0)
            if samples > 0:
                slot_mttd["mttd_ms"] = round(
                    slot_mttd["accumulated_ms"] / samples
                )

        CdhProjectLoader._atomic_write(
            path,
            json.dumps(metrics, ensure_ascii=False, indent=2),
        )
        return metrics

    @staticmethod
    def get_metrics(cdh_dir: Path) -> dict:
        path = cdh_dir / CdhProjectLoader.METRICS_FILENAME
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
        return {}

    @staticmethod
    def save_last_session(cdh_dir: Path, session_data: dict) -> None:
        path = cdh_dir / CdhProjectLoader.LAST_SESSION_FILENAME
        CdhProjectLoader._atomic_write(
            path,
            json.dumps(session_data, ensure_ascii=False, indent=2),
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
        CdhProjectLoader._atomic_write(
            path,
            json.dumps(todos_data, ensure_ascii=False, indent=2),
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
        CdhProjectLoader._atomic_write(
            path,
            json.dumps(perm_data, ensure_ascii=False, indent=2),
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
            prev_idx = seq.index(prev) if prev else -1
            target_idx = seq.index(phase)
        except ValueError:
            return False

        # Allow any forward jump (AI-DLC adaptive flow may skip phases)
        if target_idx <= prev_idx:
            return False

        if prev and prev != "init" and prev in seq:
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

    # ── state migration & fingerprinting ───────────────────────

    @staticmethod
    def _migrate_state(state: dict) -> dict:
        """Migrate legacy state dicts to current schema (idempotent)."""
        if not isinstance(state, dict):
            state = {}
        if "state_version" not in state:
            state["state_version"] = CdhProjectLoader.STATE_VERSION
        if "fingerprint" not in state:
            state["fingerprint"] = ""
        if "task_registry" not in state:
            state["task_registry"] = []
        if "schema_version" not in state:
            state["schema_version"] = CdhProjectLoader.SCHEMA_VERSION
        return state

    @staticmethod
    def compute_task_fingerprint(intent: str, project_root: Path) -> str:
        """Return SHA256 hex of (intent, project.yaml contents)[:24]."""
        project_yaml = project_root / "project.yaml"
        yaml_contents = ""
        if project_yaml.exists():
            try:
                yaml_contents = project_yaml.read_text(encoding="utf-8")
            except Exception:
                yaml_contents = ""
        payload = f"{intent}\n{yaml_contents}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:24]

    @staticmethod
    def find_existing_task(cdh_dir: Path, fingerprint: str) -> Optional[dict]:
        """Search task_registry for entry matching fingerprint."""
        state = CdhProjectLoader.load_project_state(cdh_dir)
        for entry in state.get("task_registry", []):
            if isinstance(entry, dict) and entry.get("fingerprint") == fingerprint:
                return entry
        return None

    @staticmethod
    def register_task(cdh_dir: Path, intent: str, status: str) -> bool:
        """Register or update a task in task_registry. Returns False on no-op."""
        project_root = cdh_dir.parent
        fingerprint = CdhProjectLoader.compute_task_fingerprint(intent, project_root)
        state = CdhProjectLoader.load_project_state(cdh_dir)
        registry = state.setdefault("task_registry", [])

        for entry in registry:
            if isinstance(entry, dict) and entry.get("fingerprint") == fingerprint:
                if entry.get("status") == status:
                    return False
                entry["status"] = status
                state["fingerprint"] = fingerprint
                CdhProjectLoader.save_state(cdh_dir, state)
                return True

        registry.append(
            {
                "fingerprint": fingerprint,
                "intent": intent,
                "status": status,
            }
        )
        state["fingerprint"] = fingerprint
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
        CdhProjectLoader.save_state(cdh_dir, state)

        return cdh_dir

    # ── incremental validation cache ──────────────────────────────

    CACHE_FILENAME = "validate_cache.json"

    @staticmethod
    def load_validate_cache(cdh_dir: Path) -> dict:
        """Load incremental validation cache."""
        path = cdh_dir / CdhProjectLoader.CACHE_FILENAME
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"version": 1, "entries": {}}

    @staticmethod
    def save_validate_cache(cdh_dir: Path, cache_data: dict) -> None:
        """Save incremental validation cache atomically."""
        path = cdh_dir / CdhProjectLoader.CACHE_FILENAME
        CdhProjectLoader._atomic_write(
            path,
            json.dumps(cache_data, ensure_ascii=False, indent=2),
        )

    @staticmethod
    def get_file_hash(file_path: Path) -> str:
        """Get SHA256 hash of file content."""
        import hashlib
        try:
            return hashlib.sha256(file_path.read_bytes()).hexdigest()[:16]
        except Exception:
            return ""

    @staticmethod
    def should_skip_validation(cdh_dir: Path, file_path: Path, check_name: str) -> bool:
        """Check if validation can be skipped for a file based on cache."""
        cache = CdhProjectLoader.load_validate_cache(cdh_dir)
        entries = cache.get("entries", {})
        file_key = str(file_path.relative_to(cdh_dir.parent))
        file_hash = CdhProjectLoader.get_file_hash(file_path)
        if not file_hash:
            return False
        entry = entries.get(file_key)
        if not entry:
            return False
        return entry.get("hash") == file_hash and check_name in entry.get("passed_checks", [])

    @staticmethod
    def record_validation_pass(cdh_dir: Path, file_path: Path, check_name: str) -> None:
        """Record that a file passed a specific validation check."""
        cache = CdhProjectLoader.load_validate_cache(cdh_dir)
        entries = cache.setdefault("entries", {})
        file_key = str(file_path.relative_to(cdh_dir.parent))
        file_hash = CdhProjectLoader.get_file_hash(file_path)
        if not file_hash:
            return
        entry = entries.setdefault(file_key, {"hash": file_hash, "passed_checks": []})
        if entry["hash"] != file_hash:
            entry["hash"] = file_hash
            entry["passed_checks"] = []
        if check_name not in entry["passed_checks"]:
            entry["passed_checks"].append(check_name)
        CdhProjectLoader.save_validate_cache(cdh_dir, cache)

    @staticmethod
    def invalidate_validation_cache(cdh_dir: Path, file_path: Path | None = None) -> None:
        """Invalidate cache for a specific file or all files."""
        if file_path is None:
            cache = {"version": 1, "entries": {}}
        else:
            cache = CdhProjectLoader.load_validate_cache(cdh_dir)
            file_key = str(file_path.relative_to(cdh_dir.parent))
            cache.get("entries", {}).pop(file_key, None)
        CdhProjectLoader.save_validate_cache(cdh_dir, cache)