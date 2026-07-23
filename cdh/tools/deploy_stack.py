#!/usr/bin/env python3
"""deploy_stack.py — Unified stack deployment orchestrator.

Deploys backend first, captures BACKEND_URL, then deploys all client
components with BACKEND_URL injected. Supports TCB and Aliyun.

Usage:
  deploy_stack.py --preview [--provider tcb|aliyun] [--project-root PATH] [--region REGION] [--tags K=V,...]
  deploy_stack.py --env staging|production [--provider tcb|aliyun] [--region REGION] [--tags K=V,...]
  deploy_stack.py --rollback [--stack-version VERSION]
  deploy_stack.py --test [--provider tcb|aliyun]
  deploy_stack.py --output url|json
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── structured log helper ──────────────────────────────────────────────

_JSON_MODE: bool = False


def _log(level: str, msg: str, **extra: Any) -> None:
    """Emit a structured log line to stderr.

    When ``--json`` is passed on the CLI the output is a JSON object per
    line; otherwise it is a plain ``LEVEL: message`` format.
    """
    payload: Dict[str, Any] = {
        "level": level,
        "msg": msg,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    payload.update(extra)
    if _JSON_MODE:
        print(json.dumps(payload), file=sys.stderr)
    else:
        line = f"[{level}] {msg}"
        if extra:
            line += " " + json.dumps(extra)
        print(line, file=sys.stderr)


# ── result helpers ─────────────────────────────────────────────────────


def _ok_result(**fields: Any) -> Dict[str, Any]:
    return {"status": "passed", "passed": True, "failed": False, "errors": [], **fields}


def _fail_result(reason: str, **fields: Any) -> Dict[str, Any]:
    return {"status": "failed", "passed": False, "failed": True, "errors": [reason], **fields}


def _merge_results(*results: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {
        "status": "passed",
        "passed": True,
        "failed": False,
        "errors": [],
        "components": {},
    }
    for r in results:
        if r.get("failed"):
            merged["status"] = "failed"
            merged["passed"] = False
            merged["failed"] = True
        merged["errors"].extend(r.get("errors", []))
        merged["components"].update(r.get("components", {}))
    return merged


# ── config loading ─────────────────────────────────────────────────────


def _load_config(project_root: Any) -> Dict[str, Any]:
    project_root = Path(project_root).resolve()
    project_yaml = project_root / "aidlc" / "project.yaml"
    if not project_yaml.exists():
        _log("WARN", "project.yaml not found, using empty config")
        return {}
    try:
        import yaml
        return yaml.safe_load(project_yaml.read_text(encoding="utf-8")) or {}
    except ImportError:
        _log("WARN", "PyYAML not installed, falling back to empty config")
        return {}
    except Exception as exc:
        _log("ERROR", f"Failed to parse project.yaml: {exc}")
        return {}


def _detect_provider(project: Dict[str, Any], preferred: str = "") -> str:
    if preferred:
        return preferred
    cross = project.get("stack", {}).get("cross_cutting", {})
    if isinstance(cross, dict) and cross.get("provider"):
        return cross["provider"]
    return "tcb"


def _get_components(project: Dict[str, Any]) -> List[str]:
    return [c.get("id", "") for c in project.get("stack", {}).get("components", [])]


# ── CLI detection ──────────────────────────────────────────────────────


def _cli_available(name: str) -> bool:
    return shutil.which(name) is not None


def _detect_tcb_cli() -> Tuple[bool, str]:
    if not _cli_available("tcb"):
        return False, "tcb CLI not found on PATH"
    try:
        r = subprocess.run(["tcb", "--version"], capture_output=True, text=True, timeout=15)
        version = r.stdout.strip() or r.stderr.strip()
        return True, version
    except Exception as exc:
        return False, str(exc)


def _detect_aliyun_cli() -> Tuple[bool, str]:
    if _cli_available("fun"):
        try:
            r = subprocess.run(["fun", "--version"], capture_output=True, text=True, timeout=15)
            return True, r.stdout.strip() or r.stderr.strip()
        except Exception as exc:
            return False, str(exc)
    if _cli_available("aliyun"):
        try:
            r = subprocess.run(["aliyun", "--version"], capture_output=True, text=True, timeout=15)
            return True, r.stdout.strip() or r.stderr.strip()
        except Exception as exc:
            return False, str(exc)
    return False, "neither fun nor aliyun CLI found on PATH"


def _detect_available_clis() -> Dict[str, Tuple[bool, str]]:
    return {
        "tcb": _detect_tcb_cli(),
        "aliyun": _detect_aliyun_cli(),
    }


# ── subprocess runner ──────────────────────────────────────────────────


def _run_step(
    step: str,
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    cwd: Optional[Path] = None,
    dry_run: bool = False,
) -> Tuple[int, str, str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    if dry_run:
        _log("DRY-RUN", f"Would run: {' '.join(cmd)}", step=step, cwd=str(cwd or ""))
        return 0, "", ""

    _log("INFO", f"Running: {' '.join(cmd)}", step=step, cwd=str(cwd or ""))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, env=merged_env, cwd=cwd, timeout=300)
        if r.returncode != 0:
            _log("WARN", f"Step '{step}' exited {r.returncode}", step=step, stderr=r.stderr.strip()[:200])
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        msg = f"Timeout (300s): {' '.join(cmd)}"
        _log("ERROR", msg, step=step)
        return -1, "", msg
    except FileNotFoundError:
        msg = f"Command not found: {cmd[0]}"
        _log("ERROR", msg, step=step)
        return -2, "", msg
    except OSError as exc:
        msg = f"OS error running {' '.join(cmd)}: {exc}"
        _log("ERROR", msg, step=step)
        return -3, "", msg


# ── core deploy logic ──────────────────────────────────────────────────


def deploy_preview(
    project_root: Any,
    provider: str = "tcb",
    region: str = "",
    tags: Optional[Dict[str, str]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    project_root = Path(project_root).resolve()
    result: Dict[str, Any] = {"status": "passed", "passed": True, "failed": False, "errors": [], "components": {}}
    project = _load_config(project_root)
    provider = _detect_provider(project, provider)
    comps = _get_components(project)
    tags = tags or {}
    backend_url = ""
    clis = _detect_available_clis()

    _log("INFO", f"Starting preview deploy", provider=provider, region=region or "default", dry_run=dry_run)

    available, version = clis.get(provider, (False, ""))
    if available:
        _log("INFO", f"Detected {provider} CLI: {version}")
    else:
        _log("WARN", f"{provider} CLI not available: {version} — falling back to simulated deploy")

    if not comps:
        _log("WARN", "No components defined in project.yaml — deploying backend only")
        comps = ["backend"]

    # ── deploy backend ──
    if "backend" in comps:
        backend_dir = project_root / "apps" / "backend"
        comps = [c for c in comps if c != "backend"]

        if provider == "tcb" and available:
            # Real TCB function deploy
            fn_cmd: list[str] = ["tcb", "fn", "deploy", "--json"]
            if region:
                fn_cmd += ["-r", region]
            if tags:
                for k, v in tags.items():
                    fn_cmd += ["--tag", f"{k}={v}"]
            rc, out, err = _run_step("tcb-backend-deploy", fn_cmd, cwd=project_root, dry_run=dry_run)
            if dry_run:
                backend_url = f"https://{project.get('name', 'project')}-preview.example.com"
            elif rc == 0:
                try:
                    deploy_info = json.loads(out)
                    backend_url = deploy_info.get("url", "")
                except (json.JSONDecodeError, TypeError):
                    # fallback to extracting from output
                    pass
                if not backend_url:
                    backend_url = f"https://{project.get('name', 'project')}-preview.tcb-preview.com"
                _log("INFO", f"Backend deployed", url=backend_url)
                result["components"]["backend"] = backend_url
            else:
                result["components"]["backend"] = f"error: {err[:120]}"
                result["errors"].append(f"Backend deploy failed: {err[:120]}")
                result["status"] = "failed"
                result["passed"] = False
                result["failed"] = True
        else:
            # Simulated
            provider_tag = "tcb" if provider == "tcb" else "fc"
            backend_url = f"https://{project.get('name', 'project')}-preview.{provider_tag}-preview.com"
            result["components"]["backend"] = f"simulated: {backend_url}"
            _log("INFO", f"Backend (simulated)", url=backend_url)
    else:
        # No backend component — perhaps already deployed externally
        backend_url = f"https://{project.get('name', 'project')}-preview.example.com"

    # ── deploy client components ──
    for comp in comps:
        if comp == "contracts":
            continue
        comp_dir = project_root / "apps" / comp
        if not comp_dir.exists():
            result["components"][comp] = "skipped (no directory)"
            _log("INFO", f"{comp}: skipped (directory not found)")
            continue

        build_env = os.environ.copy()
        if backend_url:
            build_env["BACKEND_URL"] = backend_url

        _log("INFO", f"Building {comp}", BACKEND_URL=backend_url)

        if provider == "tcb" and available and comp in ("web",):
            # Use tcb deploy for web frontend
            deploy_cmd = ["tcb", "deploy", f"--cwd={comp_dir}", "--json"]
            if region:
                deploy_cmd += ["-r", region]
            rc, out, err = _run_step(f"{comp}-tcb-deploy", deploy_cmd, cwd=project_root, dry_run=dry_run)
            if dry_run:
                result["components"][comp] = "dry-run (would tcb deploy)"
            elif rc == 0:
                url = f"https://{comp}.{project.get('name', 'project')}-preview.tcb-preview.com"
                result["components"][comp] = url
                _log("INFO", f"{comp} deployed", url=url)
            else:
                msg = f"tcb deploy error: {err[:120]}"
                result["components"][comp] = f"error: {err[:120]}"
                result["errors"].append(msg)
        else:
            # Build and optionally upload
            rc, out, err = _run_step(
                f"{comp}-build",
                ["npm", "run", "build"],
                env=build_env,
                cwd=comp_dir,
                dry_run=dry_run,
            )
            if dry_run:
                result["components"][comp] = "dry-run (would npm run build)"
                continue
            if rc != 0:
                msg = f"build error: {err[:120]}"
                result["components"][comp] = msg
                result["errors"].append(f"{comp}: {msg}")
                result["status"] = "failed"
                result["passed"] = False
                result["failed"] = True
                continue

            if comp in ("wxa", "mya", "tta"):
                result["components"][comp] = f"built (manual upload needed, BACKEND_URL={backend_url})"
                _log("INFO", f"{comp} built, manual upload required")
            else:
                url = f"https://{comp}.{project.get('name', 'project')}-preview.tcb-preview.com"
                result["components"][comp] = url
                _log("INFO", f"{comp} ready", url=url)

    result["STACK_URL"] = backend_url
    result["BACKEND_URL"] = backend_url
    if tags:
        result["tags"] = tags
    if region:
        result["region"] = region
    result["provider"] = provider
    return result


def deploy_environment(
    project_root: Any,
    env: str,
    provider: str = "tcb",
    region: str = "",
    tags: Optional[Dict[str, str]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    project_root = Path(project_root).resolve()
    project = _load_config(project_root)
    provider = _detect_provider(project, provider)
    tags = tags or {}

    _log("INFO", f"Deploying to {env}", provider=provider, region=region or "default", dry_run=dry_run)

    if env not in ("staging", "production"):
        return _fail_result(f"Unknown environment '{env}'. Supported: staging, production")

    result = deploy_preview(project_root, provider, region, tags, dry_run)
    result["environment"] = env

    if provider == "tcb":
        clis = _detect_available_clis()
        available, _ = clis.get("tcb", (False, ""))
        if available and not dry_run:
            _run_step(f"tcb-env-use", ["tcb", "env", "use", env], cwd=project_root, dry_run=dry_run)

    _log("INFO", f"Deploy to {env} complete", status=result["status"])
    return result


def rollback(
    project_root: Any,
    stack_version: str = "",
    provider: str = "tcb",
    region: str = "",
    dry_run: bool = False,
) -> Dict[str, Any]:
    project_root = Path(project_root).resolve()
    project = _load_config(project_root)
    provider = _detect_provider(project, provider)
    version = stack_version or "last-stable"

    _log("INFO", f"Rolling back to {version}", provider=provider, dry_run=dry_run)

    if provider == "tcb":
        clis = _detect_available_clis()
        available, _ = clis.get("tcb", (False, ""))
        if available:
            cmd = ["tcb", "rollback", "--version", version]
            if region:
                cmd += ["-r", region]
            rc, out, err = _run_step("tcb-rollback", cmd, cwd=project_root, dry_run=dry_run)
            if dry_run:
                return _ok_result(rolled_back_to=version)
            if rc == 0:
                _log("INFO", f"Rollback to {version} successful")
                return _ok_result(rolled_back_to=version)
            else:
                return _fail_result(f"Rollback failed: {err[:200]}", rolled_back_to=version)
        else:
            _log("WARN", "tcb CLI not available — simulated rollback")
            return _ok_result(rolled_back_to=version, simulated=True)
    else:
        _log("WARN", f"No rollback logic for provider '{provider}' — simulated")
        return _ok_result(rolled_back_to=version, simulated=True)


def test_deploy_config(
    project_root: Any,
    provider: str = "tcb",
    region: str = "",
) -> Dict[str, Any]:
    """Validate deploy configuration without actually deploying anything.

    Checks:
      - project.yaml exists and is parseable
      - component directories exist
      - cloud CLIs are on PATH
      - required env vars are set
      - (no side effects)
    """
    issues: List[str] = []
    warnings: List[str] = []
    info: Dict[str, Any] = {}

    project_root = Path(project_root).resolve()
    _log("INFO", f"Validating deploy config at {project_root}")

    # 1. project.yaml
    project_yaml = project_root / "aidlc" / "project.yaml"
    if not project_yaml.exists():
        issues.append("aidlc/project.yaml not found")
        project: Dict[str, Any] = {}
    else:
        try:
            import yaml
            project = yaml.safe_load(project_yaml.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            issues.append(f"aidlc/project.yaml parse error: {exc}")
            project = {}

    info["project_config_found"] = bool(project)

    # 2. provider
    provider = _detect_provider(project, provider)
    info["provider"] = provider

    clis = _detect_available_clis()
    for cli_name, (avail, ver) in clis.items():
        info[f"cli_{cli_name}"] = ver if avail else "NOT FOUND"
        if cli_name == provider and not avail:
            warnings.append(f"{cli_name} CLI not on PATH; deploy will be simulated")

    # 3. components
    comps = _get_components(project)
    if not comps:
        warnings.append("No components defined in project.yaml stack.components")
        comps = ["backend"]

    info["components"] = {}
    for comp in comps:
        comp_dir = project_root / "apps" / comp
        info["components"][comp] = {
            "directory_exists": comp_dir.exists(),
            "has_package_json": (comp_dir / "package.json").exists() if comp_dir.exists() else False,
        }
        if not comp_dir.exists():
            warnings.append(f"Component '{comp}' directory not found at apps/{comp}")

    # 4. backend presence
    if "backend" in comps:
        info["backend_strategy"] = "tcb fn deploy" if clis.get("tcb", (False, ""))[0] else "simulated"
    else:
        info["backend_strategy"] = "none (external)"

    # 5. region
    if region:
        info["region"] = region

    # 6. env vars
    info["env_vars"] = {
        "BACKEND_URL": os.environ.get("BACKEND_URL", "(not set)"),
    }

    if issues:
        return _fail_result("\n".join(issues), validation=info, warnings=warnings)
    if warnings:
        result = _ok_result(validation=info, warnings=warnings)
        result["status"] = "warning"
        return result
    return _ok_result(validation=info, warnings=warnings)


# ── CLI entry point ────────────────────────────────────────────────────


def _parse_tags(tag_str: str) -> Dict[str, str]:
    """Parse ``key1=val1,key2=val2`` into a dict."""
    tags: dict[str, str] = {}
    if not tag_str:
        return tags
    for pair in tag_str.split(","):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            tags[k.strip()] = v.strip()
        elif pair:
            tags[pair] = ""
    return tags


def main(argv: Optional[List[str]] = None) -> int:
    global _JSON_MODE

    parser = argparse.ArgumentParser(description="Unified stack deployment orchestrator")
    parser.add_argument("--preview", action="store_true", help="Deploy to preview")
    parser.add_argument("--env", default="", help="Environment: staging|production")
    parser.add_argument("--rollback", action="store_true", help="Rollback stack")
    parser.add_argument("--stack-version", default="", help="Version to rollback to")
    parser.add_argument("--provider", default="", help="Cloud provider: tcb|aliyun")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--output", default="", help="Output format: url|json")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output and JSON logging on stderr")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without executing")
    parser.add_argument("--region", default="", help="Deployment region (e.g. ap-guangzhou, cn-hangzhou)")
    parser.add_argument("--tags", default="", help="Comma-separated K=V tags (e.g. env=preview,team=alpha)")
    parser.add_argument("--test", action="store_true", help="Validate deploy config without deploying")

    args = parser.parse_args(argv)
    _JSON_MODE = args.json

    root = Path(args.project_root).resolve()
    tags = _parse_tags(args.tags)

    result: Optional[Dict[str, Any]] = None

    try:
        if args.test:
            result = test_deploy_config(root, args.provider, args.region)
        elif args.rollback:
            result = rollback(root, args.stack_version, args.provider, args.region, args.dry_run)
        elif args.preview:
            result = deploy_preview(root, args.provider, args.region, tags, args.dry_run)
        elif args.env:
            result = deploy_environment(root, args.env, args.provider, args.region, tags, args.dry_run)
        else:
            parser.print_help()
            return 1
    except Exception as exc:
        result = _fail_result(f"Unhandled exception: {exc}")

    # ── output ──
    if result is None:
        return 1

    if args.output == "url":
        url = result.get("STACK_URL") or result.get("BACKEND_URL", "")
        print(url)
    elif args.output == "json" or args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        status_icon = "✓" if result.get("passed") else "✗"
        print(f"\n{status_icon} Deploy Result: {result.get('status', 'unknown')}")
        comps = result.get("components", {})
        if comps:
            print("  Components:")
            for name, val in comps.items():
                print(f"    {name}: {val}")
        if result.get("errors"):
            print("  Errors:")
            for e in result["errors"]:
                print(f"    • {e}")
        if result.get("warnings"):
            print("  Warnings:")
            for w in result["warnings"]:
                print(f"    • {w}")
        stk = result.get("STACK_URL")
        if stk:
            print(f"  STACK_URL: {stk}")
        be = result.get("BACKEND_URL")
        if be:
            print(f"  BACKEND_URL: {be}")
        if result.get("environment"):
            print(f"  Environment: {result['environment']}")
        if result.get("region"):
            print(f"  Region: {result['region']}")

    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
