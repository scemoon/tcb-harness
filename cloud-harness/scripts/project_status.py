#!/usr/bin/env python3
"""
Project Status — Query and display project status/progress

Usage:
    project_status.py --name <project-name> [--json] [--workspace <dir>]

Reads .harness/state.json and provides a summary of project phase,
task progress, and blockers.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import sys
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

CDH_DIR = Path.home() / ".cloud-dev-harness"
DEFAULT_WORKSPACE = CDH_DIR / "workspace"


def _workspace_dir(ws_arg: str = "") -> Path:
    if ws_arg:
        return Path(ws_arg).expanduser().resolve()
    env_ws = os.environ.get("CDH_WORKSPACE", "")
    if env_ws:
        return Path(env_ws).expanduser().resolve()
    return DEFAULT_WORKSPACE


def get_current_project(workspace: Path) -> str:
    cf = workspace / ".current_project"
    if not cf.exists():
        return ""
    try:
        return cf.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def resolve_project(name: str, workspace: Path) -> str:
    if name:
        return name
    current = get_current_project(workspace)
    if current:
        return current
    print("[ERROR] No project specified and no current project is set.")
    print("   Run: python3 scripts/init_project.py switch <project-name>")
    raise SystemExit(1)


PHASE_ORDER = ["init", "spec", "design", "coding", "testing", "deploy", "deployed"]
PHASE_ICONS = {
    "init": "\U0001f527",
    "spec": "\U0001f4dd",
    "design": "\U0001f3a8",
    "coding": "\U0001f4bb",
    "testing": "\U0001f9ea",
    "deploy": "\U0001f680",
    "deployed": "\u2705",
}


def format_timestamp(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return ts


def get_project_status(name: str, workspace: Path) -> dict:
    project_dir = workspace / "projects" / name
    if not project_dir.exists():
        print(f"[ERROR] Project not found: {name}")
        print(f"   Expected: {project_dir}")
        return None

    config_file = project_dir / ".harness" / "config.json"
    state_file = project_dir / ".harness" / "state.json"

    config = {}
    state = {}

    if config_file.exists():
        config = json.loads(config_file.read_text(encoding="utf-8"))
    else:
        print(f"[WARN] No config.json found for project '{name}'")

    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
    else:
        print(f"[WARN] No state.json found for project '{name}'")

    artifacts = {
        "specs": len(list((project_dir / "specs").glob("**/*.md"))) if (project_dir / "specs").exists() else 0,
        "design": len(list((project_dir / "design").glob("**/*.md"))) if (project_dir / "design").exists() else 0,
        "src_files": len(list((project_dir / "src").glob("**/*.*"))) if (project_dir / "src").exists() else 0,
        "cloud_functions": len(list((project_dir / "cloud").glob("*"))) if (project_dir / "cloud").exists() else 0,
        "tests": len(list((project_dir / "tests").glob("**/*.test.*"))) + len(list((project_dir / "tests").glob("**/*.spec.*"))) if (project_dir / "tests").exists() else 0,
        "test_cases": len(list((project_dir / "tests" / "test-cases").glob("*.md"))) if (project_dir / "tests" / "test-cases").exists() else 0,
        "test_reports": len(list((project_dir / "tests" / "reports").glob("*.md"))) if (project_dir / "tests" / "reports").exists() else 0,
    }

    return {
        "config": config,
        "state": state,
        "artifacts": artifacts,
    }


def display_status(name: str, as_json: bool = False, workspace: Path = DEFAULT_WORKSPACE):
    data = get_project_status(name, workspace)
    if not data:
        return

    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    config = data["config"]
    state = data["state"]
    artifacts = data["artifacts"]

    phase = state.get("phase", "unknown")
    status = state.get("status", "unknown")
    icon = PHASE_ICONS.get(phase, "\u2753")

    platform = config.get("platform", "unknown")
    platform_label = {"mp": "\u5c0f\u7a0b\u5e8f", "web": "Web", "hybrid": "\u6df7\u5408\u9879\u76ee"}.get(platform, platform)
    platform_icon = {"mp": "\U0001f4f1", "web": "\U0001f310", "hybrid": "\U0001f517"}.get(platform, "?")

    print(f"\n\u001b[4m\u9879\u76ee\u001b[0m: {config.get('name', name)}")
    print(f"\u001b[4m\u5e73\u53f0\u001b[0m: {platform_icon} {platform_label} ({platform})")
    print(f"\u001b[4m\u9636\u6bb5\u001b[0m: {icon} {phase} ({status})")

    if config.get("cloudbase", {}).get("envId"):
        print(f"\u001b[4mCloudBase\u001b[0m: {config['cloudbase']['envId']}")
    if config.get("wechat", {}).get("appid"):
        print(f"\u001b[4mAppID\u001b[0m: {config['wechat']['appid']}")

    tasks = state.get("tasks", {})
    if tasks.get("total", 0) > 0:
        total = tasks["total"]
        completed = tasks.get("completed", 0)
        progress_pct = (completed / total) * 100
        bar_len = 20
        filled = int(bar_len * completed / total)
        bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
        print(f"\u001b[4m\u4efb\u52a1\u8fdb\u5ea6\u001b[0m: {completed}/{total} ({progress_pct:.0f}%) [{bar}]")

        in_progress = tasks.get("inProgress", 0)
        if in_progress:
            print(f"\u001b[4m\u8fdb\u884c\u4e2d\u001b[0m: {in_progress} \u4e2a\u4efb\u52a1")

    if state.get("currentSpec"):
        print(f"\u001b[4m\u5f53\u524d Spec\u001b[0m: {state['currentSpec']}")

    blockers = state.get("blockers", [])
    if blockers:
        print(f"\u26a0\ufe0f  \u963b\u585e\u9879: {len(blockers)}")
        for b in blockers:
            print(f"   - {b}")
    else:
        print(f"\u26a0\ufe0f  \u963b\u585e: \u65e0")

    phase_history = state.get("phaseHistory", [])
    if phase_history:
        completed_phases = {h["phase"] for h in phase_history}
        timeline = []
        for p in PHASE_ORDER:
            if p in completed_phases:
                timeline.append(f"{p} \u2713")
            elif p == phase:
                timeline.append(f"{p} \u25c9")
            else:
                timeline.append(f"{p} \u25cb")
        print(" \u2192 ".join(timeline))

    print(f"\n\u001b[4m\u4ea7\u51fa\u7edf\u8ba1\u001b[0m:")
    print(f"   \u9700\u6c42\u6587\u6863: {artifacts['specs']} \u4e2a")
    print(f"   \u8bbe\u8ba1\u6587\u6863: {artifacts['design']} \u4e2a")
    print(f"   \u6e90\u7801\u6587\u4ef6: {artifacts['src_files']} \u4e2a")
    print(f"   \u4e91\u51fd\u6570: {artifacts['cloud_functions']} \u4e2a")
    print(f"   \u6d4b\u8bd5\u6587\u4ef6: {artifacts['tests']} \u4e2a")
    print(f"   \u6d4b\u8bd5\u7528\u4f8b: {artifacts['test_cases']} \u4e2a")
    print(f"   \u6d4b\u8bd5\u62a5\u544a: {artifacts['test_reports']} \u4e2a")

    last = state.get("lastActivity", {})
    if last:
        print(f"\n\U0001f550 \u6700\u8fd1\u6d3b\u52a8: {last.get('action', '')} \u2014 {last.get('task', '')}")
        if last.get("timestamp"):
            print(f"   \u65f6\u95f4: {format_timestamp(last['timestamp'])}")


def list_projects(workspace: Path):
    projects_dir = workspace / "projects"
    if not projects_dir.exists():
        print("No projects directory found")
        return

    projects = sorted([d.name for d in projects_dir.iterdir() if d.is_dir() and (d / ".harness").exists()])

    if not projects:
        print("No harness projects found")
        return

    print(f"\n\u001b[4m\u9879\u76ee\u5217\u8868\u001b[0m ({len(projects)} \u4e2a):")
    for name in projects:
        state_file = projects_dir / name / ".harness" / "state.json"
        if state_file.exists():
            state = json.loads(state_file.read_text(encoding="utf-8"))
            phase = state.get("phase", "?")
            icon = PHASE_ICONS.get(phase, "?")
            tasks = state.get("tasks", {})
            total = tasks.get("total", 0)
            completed = tasks.get("completed", 0)
            task_str = f" ({completed}/{total})" if total > 0 else ""
            print(f"   {icon} {name} \u2014 {phase}{task_str}")
        else:
            print(f"   ? {name} \u2014 unknown state")


def main():
    import os
    parser = argparse.ArgumentParser(description="Query project status")
    parser.add_argument("--name", help="Project name")
    parser.add_argument("--list", action="store_true", help="List all projects")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--workspace", default="",
                        help=f"Workspace directory (default: {DEFAULT_WORKSPACE})")
    args = parser.parse_args()

    ws = _workspace_dir(args.workspace)

    if args.list:
        list_projects(ws)
    else:
        name = resolve_project(args.name, ws)
        display_status(name, as_json=args.json, workspace=ws)


if __name__ == "__main__":
    main()
