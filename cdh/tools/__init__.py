import shutil
from pathlib import Path


_TOOL_FILES = [
    "generate_shared.py",
    "contract_diff.py",
    "deploy_stack.py",
]


def install_tools(project_root: Path) -> list[str]:
    source_dir = Path(__file__).parent
    target_dir = project_root / "aidlc" / "tools"
    target_dir.mkdir(parents=True, exist_ok=True)

    installed = []
    for tf in _TOOL_FILES:
        src = source_dir / tf
        if not src.exists():
            continue
        dst = target_dir / tf
        shutil.copy2(src, dst)
        dst.chmod(0o755)
        installed.append(tf)
    return installed


def tools_status(project_root: Path) -> dict[str, str]:
    tools_dir = project_root / "aidlc" / "tools"
    result = {}
    for tf in _TOOL_FILES:
        f = tools_dir / tf
        if not f.exists():
            result[tf] = "missing"
        else:
            content = f.read_text(encoding="utf-8")
            if "not yet implemented" in content:
                result[tf] = "stub"
            else:
                result[tf] = "installed"
    return result


def update_tools(project_root: Path) -> list[str]:
    installed = install_tools(project_root)
    return installed
