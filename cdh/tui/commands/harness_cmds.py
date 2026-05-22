from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from cdh.config import HARNESS_DIR
from cdh.tui.commands.registry import command


def _projects_dir(app) -> Path:
    return Path(app.workspace).expanduser().resolve() / "projects"


def _current_file(app) -> Path:
    return Path(app.workspace).expanduser().resolve() / ".current_project"


def get_current_project(workspace: Path) -> str:
    current_file = workspace / ".current_project"
    if current_file.exists():
        try:
            return current_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return ""


def write_current_project(workspace: Path, name: str) -> None:
    current_file = workspace / ".current_project"
    current_file.parent.mkdir(parents=True, exist_ok=True)
    current_file.write_text(name, encoding="utf-8")


def get_project_state(project_name: str, projects_dir: Path) -> dict:
    state_file = projects_dir / project_name / ".harness" / "state.json"
    if state_file.exists():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def get_project_config(project_name: str, projects_dir: Path) -> dict:
    config_file = projects_dir / project_name / ".harness" / "config.json"
    if config_file.exists():
        try:
            return json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


@command("harness init", "Initialize a new project with cloud-harness")
def cmd_harness_init(app, *args):
    if not args:
        return "Usage: /harness init <project-name> --platform <mp|web|oa|hybrid> [--appid <appid>] [--envId <envId>]"

    name = args[0] if args else ""
    if not name:
        return "Project name required."

    platform = "mp"
    appid = ""
    envId = ""

    remaining = list(args[1:])
    i = 0
    while i < len(remaining):
        if remaining[i] == "--platform" and i + 1 < len(remaining):
            platform = remaining[i + 1]
            i += 2
        elif remaining[i] == "--appid" and i + 1 < len(remaining):
            appid = remaining[i + 1]
            i += 2
        elif remaining[i] == "--envId" and i + 1 < len(remaining):
            envId = remaining[i + 1]
            i += 2
        else:
            i += 1

    try:
        init_script = HARNESS_DIR / "scripts" / "init_project.py"
        cmd = [
            "python3", str(init_script), "init",
            "--name", name, "--platform", platform,
            "--workspace", str(app.workspace),
        ]
        if appid:
            cmd.extend(["--appid", appid])
        if envId:
            cmd.extend(["--envId", envId])
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return f"Init failed: {result.stderr.strip() or result.stdout.strip()}"
        write_current_project(app.workspace, name)
        app.current_project = name
        app.agent._project_context_loaded = False
        app.agent._inject_project_context(name)
        app.activity_recorder.record(
            event_type="harness_init",
            project=name,
            details={"platform": platform, "appid": appid, "envId": envId},
        )
        project_dir = app.projects_dir / name
        return f"Project '{name}' initialized.\nLocation: {project_dir}"
    except Exception as e:
        return f"Error: {e}"


@command("harness import", "Import project from GitHub via cloud-harness")
def cmd_harness_import(app, *args):
    if not args:
        return "Usage: /harness import <project-name> --from-github <owner/repo> [--branch <branch>] [--token <token>]"

    name = args[0] if args else ""
    if not name:
        return "Project name required."

    from_github = ""
    branch = "main"
    token = ""

    remaining = list(args[1:])
    i = 0
    while i < len(remaining):
        if remaining[i] == "--from-github" and i + 1 < len(remaining):
            from_github = remaining[i + 1]
            i += 2
        elif remaining[i] == "--branch" and i + 1 < len(remaining):
            branch = remaining[i + 1]
            i += 2
        elif remaining[i] == "--token" and i + 1 < len(remaining):
            token = remaining[i + 1]
            i += 2
        else:
            i += 1

    if not from_github:
        return "--from-github required (format: owner/repo)"

    init_script = HARNESS_DIR / "scripts" / "init_project.py"
    if not init_script.exists():
        return f"cloud-harness not found at {HARNESS_DIR}"

    cmd = [
        "python3", str(init_script), "import",
        "--name", name, "--from-github", from_github, "--branch", branch,
        "--workspace", str(app.workspace),
    ]
    if token:
        cmd.extend(["--token", token])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            write_current_project(app.workspace, name)
            app.current_project = name
            app.agent._project_context_loaded = False
            app.agent._inject_project_context(name)
            return f"Project '{name}' imported from GitHub.\n{result.stdout}"
        else:
            return f"Import failed: {result.stderr}"
    except Exception as e:
        return f"Error: {e}"


@command("harness switch", "Switch active harness project")
def cmd_harness_switch(app, *args):
    if not args:
        current = get_current_project(app.workspace)
        if current:
            return f"Current harness project: {current}"
        return "No active harness project. Usage: /harness switch <project-name>"

    name = args[0]
    pdir = _projects_dir(app)
    project_dir = pdir / name
    if not project_dir.exists():
        return f"Project not found: {name}"
    if not (project_dir / ".harness").exists():
        return f"Not a harness project: {name}"

    try:
        prev = get_current_project(app.workspace)
        write_current_project(app.workspace, name)
        app.current_project = name
        app.agent._project_context_loaded = False
        app.agent._inject_project_context(name)
        app._load_session_for_project(name)
        app.activity_recorder.record(
            event_type="harness_switch",
            project=name,
            session=app._session.id if app._session else "",
            details={"previous_project": prev},
        )
        return f"Switched to project: {name}"
    except Exception as e:
        return f"Failed to switch: {e}"


@command("harness status", "Show harness project status")
def cmd_harness_status(app, *args):
    name = args[0] if args else get_current_project(app.workspace)
    if not name:
        return "No active project. Usage: /harness status [project-name]"

    pdir = _projects_dir(app)
    config = get_project_config(name, pdir)
    state = get_project_state(name, pdir)

    if not config and not state:
        return f"Project not found or not a harness project: {name}"

    platform = config.get("platform", "unknown")
    phase = state.get("phase", "unknown")
    status = state.get("status", "unknown")

    last_activity = state.get("lastActivity", {})
    activity_desc = f"{last_activity.get('action', 'N/A')}: {last_activity.get('task', 'N/A')}"

    tasks = state.get("tasks", {})
    task_info = f"Tasks: {tasks.get('completed', 0)}/{tasks.get('total', 0)} completed"

    return (
        f"Project: {name}\n"
        f"Platform: {platform}\n"
        f"Phase: {phase} | Status: {status}\n"
        f"Last activity: {activity_desc}\n"
        f"{task_info}"
    )


@command("harness list", "List all harness projects")
def cmd_harness_list(app, *args):
    pdir = _projects_dir(app)
    if not pdir.exists():
        return "No projects directory."

    current = get_current_project(app.workspace)
    projects = []

    for d in sorted(pdir.iterdir()):
        if d.is_dir() and (d / ".harness").exists():
            marker = " [current]" if d.name == current else ""
            projects.append(f"  {d.name}{marker}")

    if not projects:
        return "No harness projects found."

    return "Harness projects:\n" + "\n".join(projects)


@command("harness run", "Run harness script (validate_spec, gen_test_cases, etc.)")
def cmd_harness_run(app, *args):
    if not args:
        scripts = [
            "init_project.py", "validate_spec.py", "gen_test_cases.py",
            "gen_test_data.py", "diagnose.py", "preview.py"
        ]
        return "Usage: /harness run <script-name> [args]\nAvailable scripts: " + ", ".join(scripts)

    script_name = args[0]
    script_path = HARNESS_DIR / "scripts" / script_name
    if not script_path.exists():
        return f"Script not found: {script_name}"

    project_name = get_current_project(app.workspace)
    if not project_name:
        return "No active project. Run /harness switch <project> first."

    cmd = ["python3", str(script_path), "--project", project_name, "--workspace", str(app.workspace)] + list(args[1:])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout if result.stdout else "Done."
        else:
            return f"Error: {result.stderr}"
    except Exception as e:
        return f"Error: {e}"


@command("harness clone", "Clone project code from GitHub to local")
def cmd_harness_clone(app, *args):
    if len(args) < 2:
        return "Usage: /harness clone <local-name> <github-repo> [--branch <branch>] [--token <token>]"

    local_name = args[0]
    repo = args[1]
    branch = "main"
    token = os.environ.get("GITHUB_TOKEN", "")

    remaining = list(args[2:])
    i = 0
    while i < len(remaining):
        if remaining[i] == "--branch" and i + 1 < len(remaining):
            branch = remaining[i + 1]
            i += 2
        elif remaining[i] == "--token" and i + 1 < len(remaining):
            token = remaining[i + 1]
            i += 2
        else:
            i += 1

    owner_repo = repo.replace("https://github.com/", "").replace("http://github.com/", "")
    if "/" not in owner_repo:
        return f"Invalid repo format: {repo} (use owner/repo)"

    if token:
        clone_url = f"https://{token}@github.com/{owner_repo}.git"
    else:
        clone_url = f"https://github.com/{owner_repo}.git"

    pdir = _projects_dir(app)
    target_dir = pdir / local_name
    if target_dir.exists():
        return f"Directory already exists: {local_name}"

    try:
        subprocess.run(
            ["git", "clone", "--branch", branch, "--depth", "1", clone_url, str(target_dir)],
            check=True, capture_output=True, text=True
        )

        git_dir = target_dir / ".git"
        if git_dir.exists():
            import shutil
            shutil.rmtree(git_dir)

        return f"Cloned {repo} \u2192 {local_name}\nLocation: {target_dir}"
    except subprocess.CalledProcessError as e:
        return f"Clone failed: {e.stderr}"
