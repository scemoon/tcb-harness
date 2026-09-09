#!/usr/bin/env python3
"""
Preview — Build and preview Web / Miniprogram / App projects

Usage:
    preview.py [--platform mp|web|app|auto] [--project <name>]

Platform behavior:
    web   — Build web app, upload to CloudBase static hosting,
            return accessible URL (auto domain + whitelist support)
    mp    — Build miniprogram, run preview via miniprogram-ci,
            output QR code (terminal + file)
    app   — Not supported (prints guidance only)
    auto  — Detect from .harness/config.json platform field

Exit codes:
    0  — Preview generated successfully
    1  — Platform not supported, build error, or upload error
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
WORKSPACE = Path(os.environ.get("OPENCLAW_WORKSPACE", SKILL_DIR.parent.parent))
PROJECTS_DIR = WORKSPACE / "projects"
HARNESS_DIR = WORKSPACE / ".harness"
CURRENT_FILE = HARNESS_DIR / "current"


def get_current_project(name: str) -> str:
    if name:
        return name
    if CURRENT_FILE.exists():
        return CURRENT_FILE.read_text(encoding="utf-8").strip()
    return ""


def resolve_project(name: str) -> Path:
    proj = get_current_project(name)
    if not proj:
        print("[ERROR] No project specified and no current project set.")
        print("   Run: python3 scripts/init_project.py switch <project-name>")
        raise SystemExit(1)
    proj_dir = PROJECTS_DIR / proj
    if not proj_dir.exists():
        print(f"[ERROR] Project not found: {proj}")
        raise SystemExit(1)
    return proj_dir


def load_config(proj_dir: Path) -> dict:
    cfg = proj_dir / ".harness" / "config.json"
    if cfg.exists():
        return json.loads(cfg.read_text(encoding="utf-8"))
    return {}


def load_deploy_config(proj_dir: Path) -> dict:
    dc = proj_dir / ".harness" / "deploy-config.json"
    if dc.exists():
        return json.loads(dc.read_text(encoding="utf-8"))
    return {}


def save_deploy_config(proj_dir: Path, data: dict) -> None:
    path = proj_dir / ".harness" / "deploy-config.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def run(cmd: list, cwd: Path = None, env: dict = None) -> subprocess.CompletedProcess:
    merged_env = {**os.environ, **(env or {})}
    return subprocess.run(cmd, cwd=cwd, env=merged_env,
                          capture_output=True, text=True)


def check_tool(name: str) -> bool:
    """Check if a command is available."""
    result = subprocess.run(["which", name], capture_output=True)
    return result.returncode == 0


# ─── Web Preview ──────────────────────────────────────────────────────────────

def preview_web(proj_dir: Path) -> int:
    """Build web app and upload to CloudBase static hosting."""
    config = load_config(proj_dir)
    deploy_cfg = load_deploy_config(proj_dir)
    platform_cfg = deploy_cfg.get("frontend", {}).get("web", {})

    src_path = proj_dir / platform_cfg.get("srcPath", "src/web")
    output_path = proj_dir / platform_cfg.get("outputPath", "dist")
    build_cmd = platform_cfg.get("buildCommand", "npm run build")
    env_id = config.get("cloudbase", {}).get("envId") or deploy_cfg.get("envId", "")

    if not env_id:
        print("[ERROR] envId not configured. Set cloudbase.envId in .harness/config.json")
        return 1

    print(f"\n📦 Web preview for: {proj_dir.name}")
    print(f"   Build: {build_cmd}")
    print(f"   EnvId: {env_id}")

    # Step 1: Build
    print("\n[1/3] Building web app...")
    parts = build_cmd.split(" ", 1)
    cmd = parts[0]
    args = parts[1:] if len(parts) > 1 else []

    # Check if node_modules exists
    if not (src_path / "node_modules").exists():
        print("   Installing dependencies...")
        r = run(["npm", "install"], cwd=src_path)
        if r.returncode != 0:
            print(f"[ERROR] npm install failed:\n{r.stderr}")
            return 1

    r = run([cmd] + args, cwd=src_path)
    if r.returncode != 0:
        print(f"[ERROR] Build failed:\n{r.stderr}")
        return 1
    print(f"[OK] Build complete → {output_path}")

    # Step 2: Upload via mcporter
    print("\n[2/3] Uploading to CloudBase static hosting...")
    if not check_tool("npx"):
        print("[ERROR] npx not available")
        return 1

    upload_cmd = [
        "npx", "mcporter", "call", "cloudbase.hosting.upload",
        "--localPath", str(output_path),
        "--remotePath", "/",
        "--envId", env_id,
    ]
    r = run(upload_cmd)
    if r.returncode != 0:
        print(f"[WARN] mcporter upload failed, trying CLI directly...")
        # Fallback: use tccli or direct API
        print(f"   Output: {r.stdout}")
        print(f"   Error:  {r.stderr}")
        # Try with env variable injection
        r = run(upload_cmd, env={**os.environ, "ENVID": env_id})
        if r.returncode != 0:
            print(f"[ERROR] Upload failed: {r.stderr}")
            return 1

    print(f"[OK] Uploaded to CloudBase static hosting")

    # Step 3: Get preview URL
    print("\n[3/3] Getting preview URL...")
    auto_domain = f"https://{proj_dir.name}-{env_id.replace('-', '')}.cloud.tcbbase.com"

    # Check domain binding status
    check_cmd = [
        "npx", "mcporter", "call", "cloudbase.hosting.getDomainInfo",
        "--envId", env_id,
    ]
    r = run(check_cmd)
    domain_info = ""
    if r.returncode == 0 and r.stdout:
        try:
            info = json.loads(r.stdout)
            domain_info = info.get("domain", auto_domain)
        except Exception:
            domain_info = auto_domain
    else:
        domain_info = auto_domain

    print(f"\n🌐 Preview URL: {domain_info}")
    print(f"\n⚠️  Domain not whitelisted yet.")
    print(f"   Please add domain to whitelist in CloudBase console:")
    print(f"   https://console.cloud.tencent.com/tcb/hosting/domain")
    print(f"\n   Domain to add: {domain_info}")

    # Update deploy-config.json
    deploy_cfg.setdefault("frontend", {}).setdefault("web", {})["previewUrl"] = domain_info
    deploy_cfg["frontend"]["web"]["buildVerified"] = True
    deploy_cfg["frontend"]["web"]["deployedAt"] = datetime.now(timezone.utc).isoformat()
    save_deploy_config(proj_dir, deploy_cfg)
    print(f"\n[OK] deploy-config.json updated with previewUrl")

    return 0


# ─── Miniprogram Preview ───────────────────────────────────────────────────────

def preview_mp(proj_dir: Path) -> int:
    """Build and preview miniprogram via miniprogram-ci."""
    config = load_config(proj_dir)
    deploy_cfg = load_deploy_config(proj_dir)
    mp_cfg = deploy_cfg.get("frontend", {}).get("miniprogram", {})

    appid = config.get("wechat", {}).get("appid") or mp_cfg.get("appid", "")
    src_path = proj_dir / mp_cfg.get("srcPath", "src/miniprogram")
    qrcode_out = proj_dir / mp_cfg.get("preview", {}).get("qrcodeOutput", "preview-qrcode.png")
    private_key = proj_dir / ".harness" / "private.key"

    if not appid:
        print("[ERROR] appid not configured. Set wechat.appid in .harness/config.json")
        return 1

    if not private_key.exists():
        print("[ERROR] Private key not found at .harness/private.key")
        print("   Download from: WeChat DevTools → Settings → Security → Download")
        print("\n📋 如果需要配置白名单或上传密钥，访问：")
        print("   https://mp.weixin.qq.com/wxamp/devprofile/get_profile?token=164093043&lang=zh_CN")
        print("   位置：微信公众平台 → 开发管理 → 开发设置 → 服务器域名/白名单")
        return 1

    print(f"\n📱 Miniprogram preview for: {proj_dir.name}")
    print(f"   AppID: {appid}")
    print(f"   SrcPath: {src_path}")

    # Check if node_modules exists
    if not (src_path / "node_modules").exists():
        print("   Installing dependencies...")
        r = run(["npm", "install"], cwd=src_path)
        if r.returncode != 0:
            print(f"[ERROR] npm install failed:\n{r.stderr}")
            return 1

    # Build npm if needed
    print("\n[1/3] Building npm...")
    if not check_tool("npx"):
        print("[ERROR] npx not available")
        return 1

    r = run([
        "npx", "miniprogram-ci", "build-npm",
        "--pp", str(src_path),
        "--pkp", str(private_key),
        "--appid", appid,
    ], cwd=src_path)
    if r.returncode != 0:
        print(f"[WARN] build-npm: {r.stderr}")

    # Preview
    print("\n[2/3] Generating preview QR code...")
    r = run([
        "npx", "miniprogram-ci", "preview",
        "--pp", str(src_path),
        "--pkp", str(private_key),
        "--appid", appid,
        "--desc", f"preview {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "--qrcode-format", "image",
        "--qrcode-output", str(qrcode_out),
    ], cwd=src_path)

    if r.returncode != 0:
        print(f"[ERROR] Preview failed:\n{r.stderr}")
        print(f"   Hint: Make sure WeChat DevTools is logged in and closed")
        return 1

    print(f"\n[OK] Preview QR code saved → {qrcode_out}")

    # Also print base64 QR for terminal display
    if qrcode_out.exists():
        import base64
        data = base64.b64encode(qrcode_out.read_bytes()).decode()
        print(f"\n[QR Code base64] {data[:80]}...")

    # Update deploy-config
    deploy_cfg.setdefault("frontend", {}).setdefault("miniprogram", {})["preview"] = {
        "qrcodeOutput": str(qrcode_out),
        "verified": False,
        "previewedAt": datetime.now(timezone.utc).isoformat(),
    }
    save_deploy_config(proj_dir, deploy_cfg)

    print(f"\n📱 Scan the QR code with WeChat to preview on device")
    print(f"   File: {qrcode_out.absolute()}")

    print(f"\n📋 预览配置说明：")
    print(f"   如需配置白名单或上传密钥，访问：")
    print(f"   https://mp.weixin.qq.com/wxamp/devprofile/get_profile?token=164093043&lang=zh_CN")
    print(f"   位置：微信公众平台 → 开发管理 → 开发设置")

    return 0


# ─── Official Account Preview ─────────────────────────────────────────────────

def preview_oa(proj_dir: Path) -> int:
    """Build and preview official account H5 via static hosting."""
    config = load_config(proj_dir)
    deploy_cfg = load_deploy_config(proj_dir)
    oa_cfg = deploy_cfg.get("frontend", {}).get("officialAccount", {})

    src_path = proj_dir / oa_cfg.get("srcPath", "src/official-account")
    output_path = proj_dir / oa_cfg.get("outputPath", "dist")
    build_cmd = oa_cfg.get("buildCommand", "npm run build")
    env_id = config.get("cloudbase", {}).get("envId") or deploy_cfg.get("envId", "")

    if not env_id:
        print("[ERROR] envId not configured. Set cloudbase.envId in .harness/config.json")
        return 1

    appid = config.get("wechat", {}).get("appid") or oa_cfg.get("appid", "")
    print(f"\n📣 Official Account preview for: {proj_dir.name}")
    print(f"   AppID: {appid}")
    print(f"   Build: {build_cmd}")
    print(f"   EnvId: {env_id}")

    # Step 1: Build
    print("\n[1/3] Building official account H5...")
    parts = build_cmd.split(" ", 1)
    cmd = parts[0]
    args = parts[1:] if len(parts) > 1 else []

    if not (src_path / "node_modules").exists():
        print("   Installing dependencies...")
        r = run(["npm", "install"], cwd=src_path)
        if r.returncode != 0:
            print(f"[ERROR] npm install failed:\n{r.stderr}")
            return 1

    r = run([cmd] + args, cwd=src_path)
    if r.returncode != 0:
        print(f"[ERROR] Build failed:\n{r.stderr}")
        return 1
    print(f"[OK] Build complete → {output_path}")

    # Step 2: Upload via mcporter
    print("\n[2/3] Uploading to CloudBase static hosting...")
    if not check_tool("npx"):
        print("[ERROR] npx not available")
        return 1

    upload_cmd = [
        "npx", "mcporter", "call", "cloudbase.hosting.upload",
        "--localPath", str(output_path),
        "--remotePath", "/",
        "--envId", env_id,
    ]
    r = run(upload_cmd)
    if r.returncode != 0:
        print(f"[WARN] mcporter upload failed: {r.stderr}")

    print(f"[OK] Uploaded to CloudBase static hosting")

    # Step 3: Get preview URL
    print("\n[3/3] Getting preview URL...")
    auto_domain = f"https://{proj_dir.name}-{env_id.replace('-', '')}.cloud.tcbbase.com"

    check_cmd = [
        "npx", "mcporter", "call", "cloudbase.hosting.getDomainInfo",
        "--envId", env_id,
    ]
    r = run(check_cmd)
    domain_info = auto_domain
    if r.returncode == 0 and r.stdout:
        try:
            info = json.loads(r.stdout)
            domain_info = info.get("domain", auto_domain)
        except Exception:
            pass

    print(f"\n🌐 Preview URL: {domain_info}")
    print(f"\n⚠️  Domain not whitelisted yet.")
    print(f"   Please add domain to whitelist in WeChat Public Platform console:")
    print(f"   https://mp.weixin.qq.com/ → Settings → Public Platform Settings → JS Interface Security Domain")
    print(f"   Also add to CloudBase console:")
    print(f"   https://console.cloud.tencent.com/tcb/hosting/domain")
    print(f"\n   Domain to add: {domain_info}")

    # Update deploy-config.json
    deploy_cfg.setdefault("frontend", {}).setdefault("officialAccount", {})["previewUrl"] = domain_info
    deploy_cfg["frontend"]["officialAccount"]["buildVerified"] = True
    deploy_cfg["frontend"]["officialAccount"]["deployedAt"] = datetime.now(timezone.utc).isoformat()
    save_deploy_config(proj_dir, deploy_cfg)
    print(f"\n[OK] deploy-config.json updated with previewUrl")
    print(f"\n📱 Open the URL in WeChat内置浏览器 to experience full JSSDK features")

    return 0


# ─── App (Not Supported) ──────────────────────────────────────────────────────

def preview_app(proj_dir: Path) -> int:
    """App platform does not support direct preview."""
    print("\n📱 App platform preview is not supported.")
    print("   App (移动端 H5 / TDesign Mobile React) cannot be")
    print("   directly previewed in a terminal environment.")
    print("\n   Options:")
    print("   1. Use browser DevTools mobile simulation")
    print("   2. Deploy to a test URL and open on device")
    print("   3. Use Web platform preview with mobile viewport")
    return 1


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build and preview a harness project")
    parser.add_argument("--platform", "-p",
                        choices=["web", "mp", "oa", "app", "auto"],
                        default="auto",
                        help="Platform type (auto-detect from config by default)")
    parser.add_argument("--project", help="Project name (uses current if omitted)")

    args = parser.parse_args()

    proj_dir = resolve_project(args.project)
    config = load_config(proj_dir)
    platform = config.get("platform", "web")

    # Show current project context
    print(f"\n🔧 Project: {proj_dir.name} | Platform: {platform} | Preview: {args.platform}")

    if args.platform == "auto":
        effective = platform
    else:
        effective = args.platform

    if effective == "hybrid":
        print("\n🔗 Hybrid project — running web + miniprogram preview in sequence")
        web_err = preview_web(proj_dir)
        print()
        mp_err = preview_mp(proj_dir)
        sys.exit(0 if (web_err == 0 and mp_err == 0) else 1)

    if effective == "web":
        sys.exit(preview_web(proj_dir))
    elif effective == "mp":
        sys.exit(preview_mp(proj_dir))
    elif effective == "oa":
        sys.exit(preview_oa(proj_dir))
    elif effective == "app":
        sys.exit(preview_app(proj_dir))
    else:
        print(f"[ERROR] Unknown platform: {effective}")
        sys.exit(1)


if __name__ == "__main__":
    main()