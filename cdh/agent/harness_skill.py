from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from cdh.config import HARNESS_DIR
from cdh.models.provider import Message


class HarnessSkill:
    @staticmethod
    def get_skill_content() -> str:
        skill_md = HARNESS_DIR / "SKILL.md"
        if skill_md.exists():
            return skill_md.read_text(encoding="utf-8")
        return ""

    @staticmethod
    def load_skill_into_context(context: list[Message], skill_content: str) -> None:
        system_msg = Message(role="system", content=skill_content)
        context.insert(0, system_msg)

    @staticmethod
    def is_harness_project(project_name: str, workspace: Path) -> bool:
        if not project_name:
            return False
        return (workspace / "projects" / project_name / ".harness").exists()

    @staticmethod
    def get_project_info(project_name: str, workspace: Path) -> dict:
        if not HarnessSkill.is_harness_project(project_name, workspace):
            return {}

        project_dir = workspace / "projects" / project_name
        config_file = project_dir / ".harness" / "config.json"
        state_file = project_dir / ".harness" / "state.json"

        info = {"name": project_name}

        if config_file.exists():
            try:
                info["config"] = json.loads(config_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        if state_file.exists():
            try:
                info["state"] = json.loads(state_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        return info

    @staticmethod
    def get_reference_path(ref_name: str) -> Optional[Path]:
        ref_file = HARNESS_DIR / "references" / ref_name
        if ref_file.exists():
            return ref_file
        spec_file = HARNESS_DIR / "spec-workflow" / ref_name
        if spec_file.exists():
            return spec_file
        return None

    @staticmethod
    def read_reference(ref_name: str) -> str:
        ref_path = HarnessSkill.get_reference_path(ref_name)
        if ref_path:
            return ref_path.read_text(encoding="utf-8")
        return f"Reference not found: {ref_name}"

    @staticmethod
    def load_skill_for_project(workspace: Path, project_name: str) -> str:
        """Check if project is a harness project and return its skill content, or ''."""
        if not HarnessSkill.is_harness_project(project_name, workspace):
            return ""
        info = HarnessSkill.get_project_info(project_name, workspace)
        if not info:
            return ""
        return HarnessSkill.get_skill_content()

    @staticmethod
    def run_harness_script(script_name: str, project_name: str, workspace: Path, extra_args: list[str] = None) -> dict:
        script_path = HARNESS_DIR / "scripts" / script_name
        if not script_path.exists():
            return {"success": False, "error": f"Script not found: {script_name}"}

        cmd = ["python3", str(script_path), "--project", project_name, "--workspace", str(workspace)]
        if extra_args:
            cmd.extend(extra_args)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(workspace),
                timeout=120
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Script timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}
