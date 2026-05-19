from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from cdh.models.provider import Message


HARNESS_SKILL_DIR = Path(__file__).parent.parent.parent.parent / "cloud-harness"
WORKSPACE = HARNESS_SKILL_DIR.parent
PROJECTS_DIR = WORKSPACE / "projects"


class HarnessSkill:
    @staticmethod
    def get_skill_content() -> str:
        skill_md = HARNESS_SKILL_DIR / "SKILL.md"
        if skill_md.exists():
            return skill_md.read_text(encoding="utf-8")
        return ""

    @staticmethod
    def load_skill_into_context(context: list[Message], skill_content: str) -> None:
        system_msg = Message(role="system", content=skill_content)
        context.insert(0, system_msg)

    @staticmethod
    def is_harness_project(project_name: str) -> bool:
        if not project_name:
            return False
        project_dir = PROJECTS_DIR / project_name
        harness_dir = project_dir / ".harness"
        return harness_dir.exists()

    @staticmethod
    def get_project_info(project_name: str) -> dict:
        if not HarnessSkill.is_harness_project(project_name):
            return {}
        
        project_dir = PROJECTS_DIR / project_name
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
        ref_file = HARNESS_SKILL_DIR / "references" / ref_name
        if ref_file.exists():
            return ref_file
        spec_file = HARNESS_SKILL_DIR / "spec-workflow" / ref_name
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
    def run_harness_script(script_name: str, project_name: str, extra_args: list[str] = None) -> dict:
        script_path = HARNESS_SKILL_DIR / "scripts" / script_name
        if not script_path.exists():
            return {"success": False, "error": f"Script not found: {script_name}"}
        
        cmd = ["python3", str(script_path), "--project", project_name]
        if extra_args:
            cmd.extend(extra_args)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(WORKSPACE),
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


def load_skill_for_project(context: list[Message], project_name: str) -> bool:
    if not HarnessSkill.is_harness_project(project_name):
        return False
    
    info = HarnessSkill.get_project_info(project_name)
    if not info:
        return False
    
    skill_content = HarnessSkill.get_skill_content()
    if not skill_content:
        return False
    
    HarnessSkill.load_skill_into_context(context, skill_content)
    return True