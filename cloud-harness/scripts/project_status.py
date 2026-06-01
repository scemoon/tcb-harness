#!/usr/bin/env python3
"""
Project Status — Query and display project status/progress

Usage:
    project_status.py --project-dir <dir> [--json]

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


def get_project_status(project_dir: Path) -> dict:
    if not project_dir.exists():
        print(f"[ERROR] Project not found: {project_dir}")
        return None

    config_file = project_dir / ".harness" / "config.json"
    state_file = project_dir / ".harness" / "state.json"

    config = {}
    state = {}

    if config_file.exists():
        config = json.loads(config_file.read_text(encoding="utf-8"))
    else:
        print(f"[WARN] No config.json found at {config_file}")

    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
    else:
        print(f"[WARN] No state.json found at {state_file}")

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


def display_status(project_dir: Path, as_json: bool = False):
    data = get_project_status(project_dir)
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
    platform_label = {"mp": "小程序", "web": "Web", "hybrid": "混合项目"}.get(platform, platform)
    platform_icon = {"mp": "\U0001f4f1", "web": "\U0001f310", "hybrid": "\U0001f517"}.get(platform, "?")

    print(f"\n\u001b[4m项目\u001b[0m: {config.get('name', project_dir.name)}")
    print(f"\u001b[4m目录\u001b[0m: {project_dir}")
    print(f"\u001b[4m平台\u001b[0m: {platform_icon} {platform_label} ({platform})")
    print(f"\u001b[4m阶段\u001b[0m: {icon} {phase} ({status})")

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
        print(f"\u001b[4m任务进度\u001b[0m: {completed}/{total} ({progress_pct:.0f}%) [{bar}]")

        in_progress = tasks.get("inProgress", 0)
        if in_progress:
            print(f"\u001b[4m进行中\u001b[0m: {in_progress} 个任务")

    if state.get("currentSpec"):
        print(f"\u001b[4m当前 Spec\u001b[0m: {state['currentSpec']}")

    blockers = state.get("blockers", [])
    if blockers:
        print(f"\u26a0\ufe0f  阻塞项: {len(blockers)}")
        for b in blockers:
            print(f"   - {b}")
    else:
        print(f"\u26a0\ufe0f  阻塞: 无")

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

    print(f"\n\u001b[4m产出统计\u001b[0m:")
    print(f"   需求文档: {artifacts['specs']} 个")
    print(f"   设计文档: {artifacts['design']} 个")
    print(f"   源码文件: {artifacts['src_files']} 个")
    print(f"   云函数: {artifacts['cloud_functions']} 个")
    print(f"   测试文件: {artifacts['tests']} 个")
    print(f"   测试用例: {artifacts['test_cases']} 个")
    print(f"   测试报告: {artifacts['test_reports']} 个")

    last = state.get("lastActivity", {})
    if last:
        print(f"\n\U0001f550 最近活动: {last.get('action', '')} \u2014 {last.get('task', '')}")
        if last.get("timestamp"):
            print(f"   时间: {format_timestamp(last['timestamp'])}")


def main():
    parser = argparse.ArgumentParser(description="Query project status")
    parser.add_argument("--project-dir", default="",
                        help="Project directory (default: current working directory)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).expanduser().resolve() if args.project_dir else Path.cwd()
    display_status(project_dir, as_json=args.json)


if __name__ == "__main__":
    main()
