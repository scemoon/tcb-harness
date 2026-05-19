#!/usr/bin/env python3
"""
Project Initializer — Scaffold or import a cloud-harness project

Usage:
    # 从零创建新项目
    init_project.py --name <project-name> \\
        --platform <mp|web|hybrid> \\
        [--appid <appid>] \\
        [--envId <envId>]

    # 从 GitHub 导入已有项目
    init_project.py --name <project-name> \\
        --from-github <owner/repo> \\
        [--branch <branch>] \\
        [--token <github-token>]

Creates the standard directory structure under projects/<project-name>/.

Platform types:
    mp       — WeChat Mini Program only
    web      — Web app only
    oa       — WeChat Official Account H5 (JSSDK + OAuth)
    hybrid   — Multiple platforms sharing one backend
"""

import argparse
import json
import os
import shutil
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent  # cloud-harness root
WORKSPACE = Path(os.environ.get("OPENCLAW_WORKSPACE", SKILL_DIR.parent.parent))
PROJECTS_DIR = WORKSPACE / "projects"
HARNESS_DIR = WORKSPACE / ".harness"
CURRENT_FILE = HARNESS_DIR / "current"  # stores current project name
GITHUB_API = "https://api.github.com"
TOKEN_FILE = WORKSPACE / ".cloud-harness-tokens.json"


def load_stored_token() -> str:
    """Load stored GitHub token from local file."""
    if not TOKEN_FILE.exists():
        return ""
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        return data.get("github", "")
    except (json.JSONDecodeError, KeyError):
        return ""


def save_token(token: str) -> bool:
    """Save GitHub token to local file. Returns True on success."""
    try:
        data = {}
        if TOKEN_FILE.exists():
            try:
                data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        data["github"] = token
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        # Restrict permissions to owner only
        TOKEN_FILE.chmod(0o600)
        return True
    except Exception:
        return False


def clear_token() -> None:
    """Remove stored GitHub token."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()



def get_token(token_arg: str) -> str:
    """Resolve GitHub token: arg > env > stored file."""
    if token_arg:
        return token_arg
    env_token = os.environ.get("GITHUB_TOKEN", "")
    if env_token:
        return env_token
    return load_stored_token()

def get_current_project() -> str:
    """Return the name of the currently active project, or empty string if none."""
    if not CURRENT_FILE.exists():
        return ""
    try:
        return CURRENT_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def set_current_project(name: str) -> bool:
    """Set the currently active project. Returns True on success."""
    if not name:
        return False
    project_dir = PROJECTS_DIR / name
    if not project_dir.exists() or not (project_dir / ".harness").exists():
        print(f"[ERROR] Not a harness project: {name}")
        return False
    try:
        HARNESS_DIR.mkdir(parents=True, exist_ok=True)
        CURRENT_FILE.write_text(name, encoding="utf-8")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to write current project: {e}")
        return False


def clear_current_project() -> None:
    """Clear the currently active project."""
    if CURRENT_FILE.exists():
        CURRENT_FILE.unlink()


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


SUPPORTED_PLATFORMS = ["mp", "web", "oa", "hybrid"]


# ─── GitHub Import ────────────────────────────────────────────────────────────

def parse_github_repo(value: str) -> tuple[str, str]:
    """Parse 'owner/repo' or 'https://github.com/owner/repo' into (owner, repo)."""
    value = value.rstrip("/")
    if value.startswith("https://github.com/"):
        parts = value[len("https://github.com/"):].split("/")
        return parts[0], parts[1]
    if "/" in value:
        parts = value.split("/", 1)
        return parts[0], parts[1]
    raise ValueError(f"Invalid GitHub repo format: {value}")


def github_api(path: str, token: str = "") -> dict:
    """Make an authenticated GitHub API request."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{GITHUB_API}{path}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        error_body = json.loads(e.read())
        raise RuntimeError(f"GitHub API error {e.code}: {error_body.get('message', e.reason)}")


def detect_platform_from_repo(contents_url: str, token: str) -> str:
    """Detect platform by scanning key files in the repo."""
    # Common indicator files
    indicators = {
        "mp": [
            "project.config.json",
            "miniprogram/project.config.json",
            "src/miniprogram/app.json",
            "cloud/create-order/index.js",
        ],
        "web": [
            "vite.config.ts",
            "vite.config.js",
            "src/web/index.html",
            "package.json",  # check for tdesign-react
        ],
        "oa": [
            "src/official-account/index.html",
            "src/official-account/src/utils/wxJSSDK.js",
        ],
    }

    for platform, filenames in indicators.items():
        for filename in filenames:
            try:
                github_api(f"/repos/contents/{filename}", token)
                return platform
            except (RuntimeError, urllib.error.HTTPError):
                pass

    # Default to hybrid if uncertain
    return "hybrid"


def import_from_github(name: str, repo_value: str, branch: str = "main",
                     token: str = "", save_token_flag: bool = False) -> Path:
    """Clone and import a project from GitHub."""
    owner, repo_name = parse_github_repo(repo_value)
    repo_path = f"/repos/{owner}/{repo_name}"

    # Resolve token: arg > env > stored file
    token = get_token(token)

    # Verify token works by making a simple API call
    if token:
        try:
            github_api(f"/repos/{owner}/{repo_name}", token)
        except RuntimeError:
            # Token might be invalid/expired — try without it
            token = ""
    project_dir = PROJECTS_DIR / name

    if project_dir.exists():
        print(f"[ERROR] Project directory already exists: {project_dir}")
        raise SystemExit(1)

    print(f"\nImporting project from GitHub: {owner}/{repo_name} (branch: {branch})")

    # Verify repo exists and is accessible
    try:
        repo_info = github_api(repo_path, token)
        print(f"  Repo: {repo_info['full_name']}")
        print(f"  Description: {repo_info['description'] or '(none)'}")
    except RuntimeError as e:
        print(f"[ERROR] Cannot access repo: {e}")
        raise SystemExit(1)

    # Clone the repo using git
    if token:
        clone_url = f"https://{token}@github.com/{owner}/{repo_name}.git"
    else:
        clone_url = f"https://github.com/{owner}/{repo_name}.git"

    print(f"  Cloning...")
    try:
        subprocess.run(
            ["git", "clone", "--branch", branch, "--depth", "1", clone_url, str(project_dir)],
            check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Git clone failed: {e.stderr}")
        raise SystemExit(1)

    # Remove .git directory (don't keep VCS history)
    git_dir = project_dir / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)

    # Detect platform from existing structure
    platform = detect_platform_from_repo(repo_path, token)

    # Check for existing .harness/config.json
    harness_config = project_dir / ".harness" / "config.json"
    if harness_config.exists():
        try:
            config = json.loads(harness_config.read_text(encoding="utf-8"))
            saved_platform = config.get("platform", platform)
            if saved_platform in SUPPORTED_PLATFORMS:
                platform = saved_platform
            print(f"  Detected platform: {platform} (from existing config)")
        except (json.JSONDecodeError, KeyError):
            pass

    # Ensure .harness directory exists
    harness_dir = project_dir / ".harness"
    harness_dir.mkdir(exist_ok=True)

    # Write / update .harness/config.json
    config_path = harness_dir / "config.json"
    existing_config = {}
    if config_path.exists():
        try:
            existing_config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    config = {
        **existing_config,
        "name": name,
        "platform": platform,
        "imported": {
            "from": f"{owner}/{repo_name}",
            "branch": branch,
            "importedAt": datetime.now(timezone.utc).isoformat(),
        },
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"[OK] Updated .harness/config.json")

    # Write / update .harness/state.json
    state_path = harness_dir / "state.json"
    existing_state = {}
    if state_path.exists():
        try:
            existing_state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    state = {
        **existing_state,
        "phase": existing_state.get("phase", "init"),
        "status": "ready",
        "lastActivity": {
            "action": "import",
            "task": f"imported from {owner}/{repo_name}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "importedFrom": f"{owner}/{repo_name}",
    }
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"[OK] Updated .harness/state.json")

    # Write / update deploy-config.json if not present
    deploy_path = harness_dir / "deploy-config.json"
    if not deploy_path.exists():
        deploy_config = {
            "version": "0.1.0",
            "lastDeployed": None,
            "envId": config.get("cloudbase", {}).get("envId", ""),
            "platform": platform,
            "frontend": {},
            "backend": {"cloudFunctions": [], "cloudRun": [], "database": {"noSql": {"collections": []}, "mysql": {"enabled": False}},"securityRules": {}},
            "deployOrder": [],
        }
        with open(deploy_path, "w", encoding="utf-8") as f:
            json.dump(deploy_config, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"[OK] Created .harness/deploy-config.json")

    print(f"\n[OK] Project '{name}' imported successfully from GitHub")
    print(f"  Location: {project_dir}")
    print(f"  Platform: {platform}")

    # Save token if requested
    if save_token_flag and token:
        if save_token(token):
            print(f"  Token saved to: {TOKEN_FILE}")
        else:
            print(f"  [WARN] Failed to save token.")

    print(f"\nNext steps:")
    print("1. Review and update .harness/config.json")
    print("2. Run `python3 scripts/validate_spec.py` to check existing specs")
    print("3. Continue from the current phase using '继续' command")

    return project_dir


# ─── Scaffold from scratch ───────────────────────────────────────────────────

def create_base_dirs(project_dir: Path, platform: str):
    dirs = [
        ".harness", "specs", "design/ui/wireframes", "design/shared",
        "tests/unit/services", "tests/unit/models", "tests/unit/utils",
        "tests/integration/services", "tests/e2e/flows",
        "tests/test-data", "tests/results", "tests/reports", "tests/test-cases",
        "docs/reviews",
    ]
    if platform in ("mp", "hybrid"):
        dirs += [
            "design/frontend/miniprogram",
            "src/miniprogram/pages", "src/miniprogram/components/common",
            "src/miniprogram/components/business", "src/miniprogram/services",
            "src/miniprogram/models", "src/miniprogram/utils", "cloud",
        ]
    if platform in ("web", "hybrid"):
        dirs += [
            "design/frontend/web",
            "src/web/src/pages", "src/web/src/components/common",
            "src/web/src/components/business", "src/web/src/services",
            "src/web/src/store", "src/web/src/router", "src/web/src/styles",
            "src/web/public",
        ]
    if platform in ("oa", "hybrid"):
        dirs += [
            "design/frontend/official-account",
            "src/official-account/src/pages", "src/official-account/src/components/common",
            "src/official-account/src/components/business", "src/official-account/src/services",
            "src/official-account/src/hooks", "src/official-account/src/utils",
            "src/official-account/src/styles", "src/official-account/public",
            "cloud",
        ]
    if platform == "hybrid":
        dirs += [
            "design/backend/api-contract", "design/backend/data-model",
            "design/backend/cloud-functions", "design/backend/security-rules",
        ]
    if platform == "web":
        dirs += ["cloud"]

    for d in dirs:
        (project_dir / d).mkdir(parents=True, exist_ok=True)


def write_harness_config(project_dir: Path, name: str, platform: str, appid: str, envId: str):
    config = {
        "name": name, "platform": platform, "description": "",
        "cloudbase": {"envId": envId or "", "devEnvId": ""},
        "wechat": {"appid": appid or ""},
        "created": datetime.now(timezone.utc).isoformat(),
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
    }
    path = project_dir / ".harness" / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("[OK] Created .harness/config.json")


def write_harness_state(project_dir: Path):
    state = {
        "phase": "init", "status": "ready", "currentSpec": "",
        "tasks": {"total": 0, "completed": 0, "inProgress": 0, "blocked": 0},
        "lastActivity": {"action": "init", "task": "", "timestamp": datetime.now(timezone.utc).isoformat()},
        "phaseHistory": [], "blockers": [],
    }
    path = project_dir / ".harness" / "state.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("[OK] Created .harness/state.json")


def write_deploy_config(project_dir: Path, platform: str):
    config = {
        "version": "0.1.0", "lastDeployed": None, "envId": "", "platform": platform,
        "frontend": {}, "backend": {
            "cloudFunctions": [], "cloudRun": [],
            "database": {"noSql": {"collections": []}, "mysql": {"enabled": False, "tables": []}},
            "securityRules": {},
        },
        "tracing": {"enabled": False, "collector": {"type": "mongodb", "collection": "traces"}},
        "deployOrder": [], "dependencies": {},
    }
    if platform in ("mp", "hybrid"):
        config["frontend"]["miniprogram"] = {
            "appid": "", "srcPath": "./src/miniprogram",
            "build": {"npmInstall": True, "npmBuild": True, "verified": False},
            "preview": {"qrcodeOutput": "./preview-qrcode.png", "verified": False},
            "upload": {"version": "0.1.0", "desc": "", "committed": False},
            "config": {"mainPackageSize": None, "totalSize": None},
        }
    if platform in ("web", "hybrid"):
        config["frontend"]["web"] = {
            "srcPath": "./src/web", "buildCommand": "npm run build", "outputPath": "./dist",
            "buildVerified": False, "deployedAt": None,
            "staticHosting": {"enabled": True, "envId": "", "domain": None, "customDomain": None, "cdn": True},
        }
    if platform in ("oa", "hybrid"):
        config["frontend"]["officialAccount"] = {
            "appid": appid or "", "srcPath": "./src/official-account",
            "buildCommand": "npm run build", "outputPath": "./dist",
            "buildVerified": False, "deployedAt": None,
            "staticHosting": {"enabled": True, "envId": "", "domain": None, "customDomain": None, "cdn": True},
            "oauth": {"type": "snsapi_userinfo", "redirectUri": "", "whitelisted": False},
            "jssdk": {"enabled": True, "jsApiList": [], "debug": False},
        }
    if platform == "hybrid":
        config["frontend"]["shared"] = {"note": "多端共用同一套后台 (cloud/)"}
    if platform == "hybrid":
        config["deployOrder"] = ["backend", "frontend.miniprogram", "frontend.web"]
    elif platform == "mp":
        config["deployOrder"] = ["backend", "frontend.miniprogram"]
    elif platform == "oa":
        config["deployOrder"] = ["backend", "frontend.officialAccount"]
    else:
        config["deployOrder"] = ["backend", "frontend.web"]

    path = project_dir / ".harness" / "deploy-config.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("[OK] Created .harness/deploy-config.json")


def copy_templates(project_dir: Path, platform: str):
    tpl = SKILL_DIR / "assets" / "templates"

    def copy_dir(src_dir: Path, dst_base: Path):
        if not src_dir.exists():
            return
        for f in src_dir.rglob("*"):
            if f.is_file() and f.suffix != ".tpl":
                rel = f.relative_to(src_dir)
                dst = dst_base / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)

    # Mini program
    mp_tpl = tpl / "project" / "miniprogram"
    if platform in ("mp", "hybrid") and mp_tpl.exists():
        copy_dir(mp_tpl, project_dir / "src" / "miniprogram")
        print("[OK] Copied miniprogram templates")

    # Web
    web_tpl = tpl / "project" / "web"
    if platform in ("web", "hybrid") and web_tpl.exists():
        copy_dir(web_tpl, project_dir / "src" / "web")
        print("[OK] Copied web templates")

    # Official Account
    oa_tpl = tpl / "project" / "official-account"
    if platform in ("oa", "hybrid") and oa_tpl.exists():
        copy_dir(oa_tpl, project_dir / "src" / "official-account")
        print("[OK] Copied official-account templates")

    # Backend
    backend_tpl = tpl / "project" / "backend"
    if platform in ("web", "oa", "hybrid") and backend_tpl.exists():
        copy_dir(backend_tpl, project_dir / "cloud")
        print("[OK] Copied backend templates")

    # Spec templates
    for f in (tpl / "spec").glob("*.tpl"):
        shutil.copy2(f, project_dir / "specs" / f.stem)
    print("[OK] Copied spec templates")

    # Test templates
    for f in (tpl / "testing").glob("*.tpl"):
        shutil.copy2(f, project_dir / "tests" / f.stem)
    print("[OK] Copied test templates")

    # Deploy template
    deploy_tpl = tpl / "deploy" / "deploy-config.json.tpl"
    if deploy_tpl.exists():
        shutil.copy2(deploy_tpl, project_dir / ".harness" / "deploy-config.json.tpl")


def create_project(name: str, platform: str, appid: str = "", envId: str = "") -> Path:
    project_dir = PROJECTS_DIR / name
    if project_dir.exists():
        print(f"[ERROR] Project directory already exists: {project_dir}")
        raise SystemExit(1)
    if platform not in SUPPORTED_PLATFORMS:
        print(f"[ERROR] Unknown platform: {platform}")
        print(f"   Supported: {', '.join(SUPPORTED_PLATFORMS)}")
        raise SystemExit(1)

    print(f"\nCreating project: {name} (platform: {platform})")
    print(f"Location: {project_dir}")

    project_dir.mkdir(parents=True, exist_ok=True)
    create_base_dirs(project_dir, platform)
    write_harness_config(project_dir, name, platform, appid, envId)
    write_harness_state(project_dir)
    write_deploy_config(project_dir, platform)
    copy_templates(project_dir, platform)

    print(f"\n[OK] Project '{name}' initialized successfully")
    print("\nNext steps:")
    print("1. Update .harness/config.json with CloudBase envId and WeChat AppID")
    print("2. Update .harness/deploy-config.json with CloudBase envId")
    print("3. Start the Spec phase: describe your requirements")

    notes = {
        "mp": "Mini Program — design/frontend/miniprogram/ and cloud/ are active",
        "web": "Web — design/frontend/web/ and cloud/ are active",
        "hybrid": "Hybrid — both frontend platforms + shared backend",
    }
    print(f"\nPlatform: {notes[platform]}")
    return project_dir


# ─── CLI Entry ────────────────────────────────────────────────────────────────

def main():
    import sys
    # Backward-compat: --from-github as top-level flag (no subcommand needed)
    if "--from-github" in sys.argv or "--from" in sys.argv:
        argv = sys.argv[1:]
        kw = {}
        i = 0
        while i < len(argv):
            arg = argv[i]
            if arg in ("--from-github", "--from"):
                kw["from_github"] = argv[i + 1]
                i += 2
            elif arg in ("--name",):
                kw["name"] = argv[i + 1]
                i += 2
            elif arg in ("--branch",):
                kw["branch"] = argv[i + 1]
                i += 2
            elif arg in ("--token",):
                kw["token"] = argv[i + 1]
                i += 2
            elif arg in ("--save-token",):
                kw["save_token"] = True
                i += 1
            else:
                i += 1

        name = kw.get("name", "").strip().lower().replace(" ", "-") if kw.get("name") else ""
        if not name and kw.get("from_github"):
            try:
                name = parse_github_repo(kw["from_github"])[1].lower()
            except ValueError:
                name = "imported-project"

        import_from_github(
            name or "imported-project",
            kw["from_github"],
            branch=kw.get("branch", "main"),
            token=kw.get("token", ""),
            save_token_flag=kw.get("save_token", False)
        )
        return

    parser = argparse.ArgumentParser(description="Initialize or import a cloud-harness project")
    sub = parser.add_subparsers(dest="mode", help="init or import")

    # Scaffold mode
    p_scaffold = sub.add_parser("init", help="Scaffold a new project from templates")
    p_scaffold.add_argument("--name", required=True, help="Project name")
    p_scaffold.add_argument("--platform", required=True, choices=SUPPORTED_PLATFORMS,
                            help="Platform type: mp, web, hybrid")
    p_scaffold.add_argument("--appid", default="", help="WeChat Mini Program AppID")
    p_scaffold.add_argument("--envId", default="", help="CloudBase Environment ID")

    # Import mode
    p_import = sub.add_parser("import", help="Import an existing project from GitHub")
    p_import.add_argument("--name", required=True, help="Local project name")
    p_import.add_argument("--from-github", required=True,
                          help="GitHub repo in 'owner/repo' format or full HTTPS URL")
    p_import.add_argument("--branch", default="main", help="Branch to clone (default: main)")
    p_import.add_argument("--token", default="",
                          help="GitHub token (reads from env GITHUB_TOKEN or stored token if omitted)")
    p_import.add_argument("--save-token", action="store_true",
                          help="Save the GitHub token to local file after import")

    # Auth mode: save / show / clear GitHub token
    p_auth = sub.add_parser("auth", help="Manage stored credentials")
    p_auth.add_argument("--github-token", dest="github_token", default="",
                        help="GitHub token to save (reads from GITHUB_TOKEN env if omitted)")
    p_auth.add_argument("--clear", action="store_true", help="Clear stored GitHub token")
    p_auth.add_argument("--show", action="store_true", help="Show whether a token is stored (does not reveal the token)")

    # Switch active project
    p_switch = sub.add_parser("switch", help="Set or show the active project")
    p_switch.add_argument("project", nargs="?", help="Project name to activate (omit to show current)")
    p_switch.add_argument("--clear", action="store_true", help="Clear the active project")

    # Fallback: --from-github implies import mode
    import_init = sub.add_parser("github", help=argparse.SUPPRESS)  # hidden alias

    args = parser.parse_args()

    # Auth mode
    if args.mode == "auth":
        if args.clear:
            clear_token()
            print("[OK] GitHub token cleared.")
        elif args.show:
            stored = load_stored_token()
            if stored:
                print("[OK] GitHub token is stored.")
            else:
                print("[--] No GitHub token stored.")
                print("    Run: python3 scripts/init_project.py auth --github-token <token>")
        else:
            tok = args.github_token or os.environ.get("GITHUB_TOKEN", "")
            if not tok:
                print("[ERROR] No token provided.")
                print("    python3 scripts/init_project.py auth --github-token <token>")
                print("    python3 scripts/init_project.py auth  (reads GITHUB_TOKEN env)")
                raise SystemExit(1)
            if save_token(tok):
                print("[OK] GitHub token saved to:", TOKEN_FILE)
            else:
                print("[ERROR] Failed to save token.")
                raise SystemExit(1)
        return

    # Switch active project
    if args.mode == "switch":
        if args.clear:
            clear_current_project()
            print("[OK] Active project cleared.")
            return
        if not args.project:
            current = get_current_project()
            if current:
                print(f"📌 Current project: {current}")
            else:
                print("[--] No active project.")
                print("    Run: python3 scripts/init_project.py switch <project-name>")
            return
        if set_current_project(args.project):
            print(f"[OK] Switched to project: {args.project}")
        return

    # Determine mode
    if args.mode in ("import", "github"):
        save_flag = getattr(args, "save_token", False)
        name = args.name.strip().lower().replace(" ", "-")
        if not name:
            print("[ERROR] Project name cannot be empty")
            raise SystemExit(1)
        import_from_github(
            name, args.from_github,
            branch=args.branch, token=args.token or "",
            save_token_flag=save_flag
        )
    elif args.mode == "init":
        name = args.name.strip().lower().replace(" ", "-")
        if not name:
            print("[ERROR] Project name cannot be empty")
            raise SystemExit(1)
        create_project(name, platform=args.platform, appid=args.appid, envId=args.envId)
    else:
        # Backward compat: treat positional as init with --from-github
        if hasattr(args, "from_github") and args.from_github:
            save_flag = getattr(args, "save_token", False)
            name = args.name.strip().lower().replace(" ", "-") if args.name else ""
            if not name:
                name = parse_github_repo(args.from_github)[1].lower()
            import_from_github(
                name, args.from_github,
                branch=getattr(args, "branch", "main"),
                token=getattr(args, "token", ""),
                save_token_flag=save_flag
            )
        else:
            parser.print_help()
            raise SystemExit(1)


if __name__ == "__main__":
    main()
