#!/usr/bin/env python3
"""
Project Status — Query and display project status/progress

Usage:
    project_status.py --name <project-name> [--json]

Reads .harness/state.json and provides a summary of project phase,
task progress, and blockers.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent.parent  # workspace root
PROJECTS_DIR = WORKSPACE / "projects"
HARNESS_DIR = WORKSPACE / ".harness"
CURRENT_FILE = HARNESS_DIR / "current"  # stores current project name


def get_current_project() -> str:
    """Return the name of the currently active project, or empty string if none."""
    if not CURRENT_FILE.exists():
        return ""
    try:
        return CURRENT_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def resolve_project(name: str) -> str:
    """Resolve project name: use --name arg if given, otherwise read from CURRENT_FILE."""
    if name:
        return name
    current = get_current_project()
    if current:
        return current
    print("[ERROR] No project specified and no current project is set.")
    print("   Run: python3 scripts/init_project.py switch <project-name>")
    raise SystemExit(1)

PHASE_ORDER = ["init", "spec", "design", "coding", "testing", "deploy", "deployed"]
PHASE_ICONS = {
    "init": "🔧",
    "spec": "📝",
    "design": "🎨",
    "coding": "💻",
    "testing": "🧪",
    "deploy": "🚀",
    "deployed": "✅",
}


def format_timestamp(ts: str) -> str:
    """Format ISO timestamp for display."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return ts


def get_project_status(name: str) -> dict:
    """Read project status from .harness files."""
    project_dir = PROJECTS_DIR / name
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

    # Count artifacts
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


def display_status(name: str, as_json: bool = False):
    """Display project status."""
    data = get_project_status(name)
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
    icon = PHASE_ICONS.get(phase, "❓")

    platform = config.get("platform", "unknown")
    platform_label = {"mp": "小程序", "web": "Web", "hybrid": "混合项目"}.get(platform, platform)
    platform_icon = {"mp": "📱", "web": "🌐", "hybrid": "🔗"}.get(platform, "?")

    print(f"\n📋 项目: {config.get('name', name)}")
    print(f"🔧 平台: {platform_icon} {platform_label} ({platform})")
    print(f"📌 阶段: {icon} {phase} ({status})")

    if config.get("cloudbase", {}).get("envId"):
        print(f"☁️  CloudBase: {config['cloudbase']['envId']}")
    if config.get("wechat", {}).get("appid"):
        print(f"📱 AppID: {config['wechat']['appid']}")

    # Task progress
    tasks = state.get("tasks", {})
    if tasks.get("total", 0) > 0:
        total = tasks["total"]
        completed = tasks.get("completed", 0)
        progress_pct = (completed / total) * 100
        bar_len = 20
        filled = int(bar_len * completed / total)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"✅ 任务进度: {completed}/{total} ({progress_pct:.0f}%) [{bar}]")

        in_progress = tasks.get("inProgress", 0)
        if in_progress:
            print(f"🔄 进行中: {in_progress} 个任务")

    # Current spec
    if state.get("currentSpec"):
        print(f"📄 当前 Spec: {state['currentSpec']}")

    # Blockers
    blockers = state.get("blockers", [])
    if blockers:
        print(f"⚠️  阻塞项: {len(blockers)}")
        for b in blockers:
            print(f"   - {b}")
    else:
        print(f"⚠️  阻塞: 无")

    # Phase timeline
    phase_history = state.get("phaseHistory", [])
    if phase_history:
        print("📅 里程碑:", end=" ")
        completed_phases = {h["phase"] for h in phase_history}
        for p in PHASE_ORDER:
            if p in completed_phases:
                print(f"{p} ✓", end=" → ")
            elif p == phase:
                print(f"{p} ◉", end=" → ")
            else:
                print(f"{p} ○", end=" → ")
        print()

    # Artifacts
    print(f"\n📊 产出统计:")
    print(f"   需求文档: {artifacts['specs']} 个")
    print(f"   设计文档: {artifacts['design']} 个")
    print(f"   源码文件: {artifacts['src_files']} 个")
    print(f"   云函数: {artifacts['cloud_functions']} 个")
    print(f"   测试文件: {artifacts['tests']} 个")
    print(f"   测试用例: {artifacts['test_cases']} 个")
    print(f"   测试报告: {artifacts['test_reports']} 个")

    # Last activity
    last = state.get("lastActivity", {})
    if last:
        print(f"\n🕐 最近活动: {last.get('action', '')} — {last.get('task', '')}")
        if last.get("timestamp"):
            print(f"   时间: {format_timestamp(last['timestamp'])}")


def list_projects():
    """List all projects."""
    if not PROJECTS_DIR.exists():
        print("No projects directory found")
        return

    projects = sorted([d.name for d in PROJECTS_DIR.iterdir() if d.is_dir() and (d / ".harness").exists()])

    if not projects:
        print("No harness projects found")
        return

    print(f"\n📁 项目列表 ({len(projects)} 个):")
    for name in projects:
        state_file = PROJECTS_DIR / name / ".harness" / "state.json"
        if state_file.exists():
            state = json.loads(state_file.read_text(encoding="utf-8"))
            phase = state.get("phase", "?")
            icon = PHASE_ICONS.get(phase, "?")
            tasks = state.get("tasks", {})
            total = tasks.get("total", 0)
            completed = tasks.get("completed", 0)
            task_str = f" ({completed}/{total})" if total > 0 else ""
            print(f"   {icon} {name} — {phase}{task_str}")
        else:
            print(f"   ? {name} — unknown state")


def main():
    parser = argparse.ArgumentParser(description="Query project status")
    parser.add_argument("--name", help="Project name")
    parser.add_argument("--list", action="store_true", help="List all projects")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.list:
        list_projects()
    else:
        name = resolve_project(args.name)
        display_status(name, as_json=args.json)


if __name__ == "__main__":
    main()
