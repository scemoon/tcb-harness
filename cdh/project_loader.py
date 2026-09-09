from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Optional

import yaml


AIDLC_VERSION = "4.0.0"


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
    _PHASE_SEQUENCE = ["init", "understand", "plan", "verify", "deliver"]

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
    def save_state_atomic(cdh_dir: Path, state_data: dict, timeout: float = 5.0) -> bool:
        """Atomically update state with file locking.

        Returns True if successful, False if lock could not be acquired.
        """
        import time
        path = cdh_dir / CdhProjectLoader.STATE_FILENAME
        lock_path = path.with_suffix(".lock")
        start = time.time()
        while lock_path.exists():
            if time.time() - start > timeout:
                return False
            time.sleep(0.05)
        try:
            lock_path.touch()
            migrated = CdhProjectLoader._migrate_state(state_data)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(migrated, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(path)
            return True
        finally:
            if lock_path.exists():
                lock_path.unlink()

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

    @staticmethod
    def is_aidlc_project(workspace_root: Path) -> bool:
        """Check if workspace is an AI-DLC project."""
        cdh_dir = CdhProjectLoader.find_cdh_dir(workspace_root)
        if cdh_dir is None:
            return False
        aidlc_yaml = cdh_dir.parent / "aidlc" / "project.yaml"
        return aidlc_yaml.exists()

    @staticmethod
    def _get_agents_version(workspace_root: Path) -> str:
        """Extract AI-DLC version from AGENTS.md header comment."""
        agents_md = workspace_root / "AGENTS.md"
        if not agents_md.exists():
            return ""
        try:
            content = agents_md.read_text(encoding="utf-8")
            import re
            m = re.search(r"version\s+([\d.]+)", content)
            return m.group(1) if m else ""
        except Exception:
            return ""

    @staticmethod
    def _get_skill_version(workspace_root: Path) -> str:
        """Get current AI-DLC skill version from skill.yaml."""
        skill_yaml_paths = [
            workspace_root / "ai-dlc-skill" / "skill.yaml",
            Path(__file__).resolve().parents[1] / "ai-dlc-skill" / "skill.yaml",
        ]
        for skill_yaml in skill_yaml_paths:
            if skill_yaml.exists():
                try:
                    import yaml as _yaml
                    data = _yaml.safe_load(skill_yaml.read_text(encoding="utf-8"))
                    return str(data.get("version", "") if data else "")
                except Exception:
                    pass
        return ""

    @staticmethod
    def _detect_phase_from_files(project_root: Path) -> dict | None:
        """Detect suggested phase based on recent file changes.

        Returns dict with 'phase', 'label', 'reason' if detection matches,
        otherwise None.
        """
        import time

        def _match_recent(base: Path, pattern: str) -> bool:
            """Check if any file matching pattern was modified in last 24h."""
            if "/*/" in pattern:
                prefix, suffix = pattern.split("/*/", 1)
                suffix = suffix.rstrip("/") if suffix else ""
                base_path = project_root / prefix
                if not base_path.is_dir():
                    return False
                for parent in base_path.iterdir():
                    if parent.is_dir():
                        if suffix:
                            for f in parent.glob(suffix + "/*"):
                                if f.is_file() and f.stat().st_mtime > cutoff:
                                    return True
                        else:
                            if parent.stat().st_mtime > cutoff:
                                return True
            elif pattern.endswith("/"):
                path = project_root / pattern.rstrip("/")
                if path.is_dir():
                    for f in path.rglob("*"):
                        if f.is_file() and f.stat().st_mtime > cutoff:
                            return True
            else:
                path = project_root / pattern
                if path.is_file() and path.stat().st_mtime > cutoff:
                    return True
            return False

        # File patterns that indicate each phase (first match wins)
        phase_indicators = [
            ("understand", "Understand", [
                ("aidlc/requirements.md", "New requirements document"),
            ]),
            ("plan", "Plan", [
                ("aidlc/openspec/changes/", "Spec delta ready for planning"),
                ("aidlc/design/", "Design documents"),
            ]),
            ("verify", "Verify", [
                ("apps/*/features/", "New BDD feature files"),
                ("aidlc/contracts/", "Contract changes need verification"),
            ]),
        ]

        cutoff = time.time() - 86400  # files modified in last 24h

        for phase, label, patterns in phase_indicators:
            for pattern, reason in patterns:
                if _match_recent(project_root, pattern):
                    return {
                        "phase": phase,
                        "label": label,
                        "reason": f"Detected recent changes in {pattern}",
                    }

        return None

    @staticmethod
    def analyze_user_intent(user_input: str, workspace_root: Path) -> dict | None:
        """Analyze user input and suggest AI-DLC complexity level and phases.

        Returns dict with:
        - level: L1-L5 complexity level
        - phases: list of recommended phases
        - reason: explanation of why these phases are recommended
        - confidence: 0.0-1.0 confidence score
        """
        import re

        user_lower = user_input.lower()
        # Use substring matching for keyword detection
        user_input_lower = user_input.lower()

        level = None
        phases = []
        reasons = []
        confidence = 0.5

        # Component detection from FR prefixes
        fr_prefixes = re.findall(r'\b(NATIVE|DESKTOP|WEB|BE|WXA|MYA|TTA|INT)-FR-\d+', user_input, re.IGNORECASE)
        if fr_prefixes:
            components_affected = len(set(fr_prefixes))
            if components_affected >= 3:
                level = "L4"
                phases = ["understand", "plan", "verify", "deliver"]
                reasons.append(f"涉及 {components_affected} 个组件的跨栈变更")
                confidence = 0.9
            elif components_affected == 2:
                level = "L3"
                phases = ["understand", "plan", "verify"]
                reasons.append(f"涉及 {components_affected} 个组件的集成变更")
                confidence = 0.85
            else:
                level = "L2"
                phases = ["understand", "verify"]
                reasons.append("单组件功能变更")
                confidence = 0.8

        # Keyword-based complexity detection
        bug_keywords = ["bug", "fix", "修复", "错误", "defect", "patch", "修"]
        feature_keywords = ["feature", "新功能", "新增", "add", "implement", "功能", "实现"]
        deploy_keywords = ["deploy", "部署", "release", "发布", "上线", "production"]
        refactor_keywords = ["refactor", "重构", "migration", "迁移", "架构"]

        if level is None:
            if any(k in user_input_lower for k in bug_keywords):
                level = "L1"
                phases = ["verify"]
                reasons.append("Bug fix")
                confidence = 0.7
            elif any(k in user_input_lower for k in deploy_keywords):
                level = "L4"
                phases = ["understand", "plan", "verify", "deliver"]
                reasons.append("包含部署的生产变更")
                confidence = 0.85
            elif any(k in user_input_lower for k in refactor_keywords):
                level = "L5"
                phases = ["plan", "verify"]
                reasons.append("架构重构")
                confidence = 0.75
            elif any(k in user_input_lower for k in feature_keywords):
                # Check if multi-component
                component_dirs = ["native", "desktop", "web", "backend", "wxa", "mya", "tta"]
                mentioned_components = [c for c in component_dirs if c in user_input_lower]
                if len(mentioned_components) >= 2:
                    level = "L3"
                    phases = ["understand", "plan", "verify"]
                    reasons.append(f"多组件功能: {', '.join(mentioned_components)}")
                else:
                    level = "L2"
                    phases = ["understand", "verify"]
                    reasons.append("单组件功能")
                confidence = 0.7
            else:
                level = "L2"
                phases = ["understand", "verify"]
                reasons.append("一般开发任务")
                confidence = 0.6

        # Contract detection
        if "contract" in user_lower or "api" in user_lower or "接口" in user_input:
            if level in ("L2", "L3"):
                level = "L3"
                if "understand" not in phases:
                    phases.insert(0, "understand")
                if "plan" not in phases:
                    phases.insert(1, "plan")
            reasons.append("涉及接口合约变更")

        return {
            "level": level,
            "phases": phases,
            "reasons": reasons,
            "confidence": confidence,
            "suggestion": f"[{level}] {' → '.join(phases)}",
        }

    @staticmethod
    def load_aidlc_nudge(workspace_root: Path, user_intent: str = "") -> str:
        """Generate AI-DLC contextual nudge based on project state.

        Returns an empty string if not an AI-DLC project or no nudge needed.
        """
        cdh_dir = CdhProjectLoader.find_cdh_dir(workspace_root)
        if cdh_dir is None:
            return ""

        project_root = cdh_dir.parent
        aidlc_yaml = project_root / "aidlc" / "project.yaml"
        if not aidlc_yaml.exists():
            return ""

        state = CdhProjectLoader.load_project_state(cdh_dir)
        current_phase = state.get("current_phase", "")
        completed_phases = state.get("completed_phases", [])
        task_registry = state.get("task_registry", [])

        pending_tasks = [
            t for t in task_registry
            if isinstance(t, dict) and t.get("status") not in ("completed", "skipped")
        ]

        parts = ["<!-- AIDLC_NUDGE -->"]

        # Version sync check
        agents_ver = CdhProjectLoader._get_agents_version(project_root)
        skill_ver = CdhProjectLoader._get_skill_version(project_root)
        if agents_ver and skill_ver and agents_ver != skill_ver:
            parts.append(f"\n## AI-DLC: Version Mismatch ⚠️\n")
            parts.append(f"- Project AGENTS.md: **{agents_ver}**\n")
            parts.append(f"- Latest skill: **{skill_ver}**\n")
            parts.append(f"\nRun `cdh aidlc sync` to update AGENTS.md.\n")

        # File-based phase suggestion
        phase_suggestion = CdhProjectLoader._detect_phase_from_files(project_root)

        if not current_phase and not task_registry:
            if phase_suggestion:
                parts.append(f"\n## AI-DLC: Detected Work → {phase_suggestion['label']}\n")
                parts.append(f"{phase_suggestion['reason']}\n")
                parts.append(f"\nSay 'start {phase_suggestion['phase']}' to begin.\n")
            else:
                parts.append("\n## AI-DLC: Ready to Start\n")
                parts.append("This is an AI-DLC project. To begin a new development cycle:\n")
                parts.append("- Describe your **intent** and I'll assess complexity (L1-L5)\n")
                parts.append("- Or use `/aidlc phase understand` to start with the Understand phase\n")
                parts.append("\n**Triggers**: mention `ai-dlc`, `lifecycle`, `BDD`, or `INT-FR` to activate\n")
            return "".join(parts)

        phase_labels = {
            "init": "Initialized",
            "understand": "Understand",
            "plan": "Plan",
            "verify": "Verify",
            "deliver": "Deliver",
        }

        if pending_tasks:
            task_intents = [t.get("intent", "Unknown")[:50] for t in pending_tasks[:3]]
            parts.append(f"\n## AI-DLC: {len(pending_tasks)} Pending Task(s)\n")
            for intent in task_intents:
                parts.append(f"- {intent}...\n")
            if current_phase:
                label = phase_labels.get(current_phase, current_phase)
                parts.append(f"\n**Current phase**: {label}\n")
            parts.append("\nTo continue, describe what you want to work on.\n")
            return "".join(parts)

        if current_phase and current_phase not in completed_phases:
            label = phase_labels.get(current_phase, current_phase)
            parts.append(f"\n## AI-DLC: In Progress\n")
            parts.append(f"**Current phase**: {label}\n")
            if completed_phases:
                completed_labels = [phase_labels.get(p, p) for p in completed_phases]
                parts.append(f"**Completed**: {', '.join(completed_labels)}\n")
            parts.append("\nTo advance, describe what you want to work on or say 'continue'.\n")
            return "".join(parts)

        # File-based phase suggestion (Level 2)
        phase_suggestion = CdhProjectLoader._detect_phase_from_files(project_root)
        if phase_suggestion:
            parts.append(f"\n## AI-DLC: Detected Work → {phase_suggestion['label']}\n")
            parts.append(f"{phase_suggestion['reason']}\n")
            parts.append(f"\nSay 'start {phase_suggestion['phase']}' to begin.\n")

        # Proactive intent analysis (Level 1) - only if user provided intent
        if user_intent and len(user_intent) > 10:
            intent_analysis = CdhProjectLoader.analyze_user_intent(user_intent, project_root)
            if intent_analysis and intent_analysis.get("confidence", 0) >= 0.6:
                parts.append(f"\n## AI-DLC: Intent Analysis\n")
                parts.append(f"**Suggested**: `{intent_analysis['suggestion']}`\n")
                for reason in intent_analysis.get("reasons", []):
                    parts.append(f"- {reason}\n")
                parts.append(f"\nConfidence: {intent_analysis['confidence']:.0%}\n")
                parts.append(f"\nSay 'start {intent_analysis['phases'][0]}' to begin.\n")

        return ""

    # ── intent matching & task registry ────────────────────────

    @staticmethod
    def _compute_intent_hash(intent: str) -> str:
        """Compute a deterministic hash for intent matching."""
        import hashlib
        normalized = " ".join(intent.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    @staticmethod
    def match_intent(task_registry: list, new_intent: str) -> dict | None:
        """Match new intent against existing tasks.

        Returns dict with 'task', 'match_type' (exact/fuzzy/partial), 'pending_phases'
        or None if no match.
        """
        if not task_registry:
            return None

        new_hash = CdhProjectLoader._compute_intent_hash(new_intent)

        for task in task_registry:
            if not isinstance(task, dict):
                continue

            existing_intent = task.get("intent", "")
            existing_hash = CdhProjectLoader._compute_intent_hash(existing_intent)

            if existing_hash == new_hash:
                pending = [
                    p["name"] for p in task.get("phases", [])
                    if p.get("status") not in ("completed", "skipped")
                ]
                return {
                    "task": task,
                    "match_type": "exact",
                    "pending_phases": pending,
                    "task_id": task.get("id", ""),
                }

        new_words = set(new_intent.lower().split())
        for task in task_registry:
            if not isinstance(task, dict):
                continue
            existing_words = set(task.get("intent", "").lower().split())
            overlap = new_words & existing_words
            if len(overlap) >= 3 and len(overlap) / max(len(new_words), len(existing_words)) > 0.5:
                pending = [
                    p["name"] for p in task.get("phases", [])
                    if p.get("status") not in ("completed", "skipped")
                ]
                return {
                    "task": task,
                    "match_type": "fuzzy",
                    "pending_phases": pending,
                    "task_id": task.get("id", ""),
                }

        return None

    @staticmethod
    def create_task(workspace_root: Path, intent: str, level: str, phases: list) -> dict | None:
        """Create a new task in the registry."""
        cdh_dir = CdhProjectLoader.find_cdh_dir(workspace_root)
        if cdh_dir is None:
            return None

        state = CdhProjectLoader.load_project_state(cdh_dir)
        task_id = f"task-{CdhProjectLoader._compute_intent_hash(intent)}"

        existing = CdhProjectLoader.match_intent(state.get("task_registry", []), intent)
        if existing and existing.get("pending_phases") == []:
            return None

        new_task = {
            "id": task_id,
            "intent": intent[:200],
            "level": level,
            "status": "running",
            "phases": [{"name": p, "status": "pending"} for p in phases],
        }

        state.setdefault("task_registry", []).append(new_task)
        state["current_phase"] = phases[0] if phases else ""
        CdhProjectLoader.save_state(cdh_dir, state)

        return new_task

    @staticmethod
    def get_task_fingerprint(workspace_root: Path) -> str:
        """Get fingerprint for current task state."""
        cdh_dir = CdhProjectLoader.find_cdh_dir(workspace_root)
        if cdh_dir is None:
            return ""
        state = CdhProjectLoader.load_project_state(cdh_dir)
        active_tasks = [
            t for t in state.get("task_registry", [])
            if isinstance(t, dict) and t.get("status") == "running"
        ]
        if not active_tasks:
            return ""
        return active_tasks[0].get("id", "")

    # ── phase state management ─────────────────────────────────

    @staticmethod
    def get_phase_prerequisites(phase: str) -> list:
        """Get prerequisite phases that must be completed before entering this phase."""
        prereqs = {
            "understand": [],
            "plan": ["understand"],
            "verify": ["understand"],
            "deliver": ["plan", "verify"],
        }
        return prereqs.get(phase, [])

    @staticmethod
    def can_enter_phase(workspace_root: Path, phase: str) -> tuple[bool, str]:
        """Check if it's valid to enter a phase (prerequisites met).

        Returns (can_enter, reason).
        """
        cdh_dir = CdhProjectLoader.find_cdh_dir(workspace_root)
        if cdh_dir is None:
            return False, "No .cdh directory found"

        state = CdhProjectLoader.load_project_state(cdh_dir)
        completed = set(state.get("completed_phases", []))
        prereqs = CdhProjectLoader.get_phase_prerequisites(phase)

        missing = [p for p in prereqs if p not in completed]
        if missing:
            return False, f"Prerequisites not met: {', '.join(missing)} must be completed first"

        return True, ""

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