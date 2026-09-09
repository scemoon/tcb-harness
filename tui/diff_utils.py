from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

GIT_STATUS_TIMEOUT = 5.0

IGNORED_DIRS = frozenset(
    {
        ".venv",
        ".git",
        ".pytest_cache",
        "__pycache__",
        ".mypy_cache",
        "node_modules",
        ".uv-cache",
        "dist",
        "build",
        ".idea",
    }
)

STATUS_ICONS = {"?": "?", "M": "M", "A": "A", "D": "D", "R": "R", "C": "C"}
STATUS_COLORS = {"?": "green", "M": "yellow", "A": "green", "D": "red", "R": "#888888", "C": "green"}
DIFF_COLORS = {"add": "green", "del": "red", "mix": "yellow", "dim": "#555555"}


@dataclass
class ModifiedFile:
    filepath: str
    status: str
    added: int
    deleted: int


def _status_info(raw: str) -> tuple[str, str]:
    ch = raw.strip()[:1] or "M"
    return STATUS_ICONS.get(ch, "M"), STATUS_COLORS.get(ch, "yellow")


def get_modified_files(project_dir: Path) -> list[ModifiedFile]:
    if any(part in IGNORED_DIRS for part in project_dir.parts):
        return []
    try:
        status = subprocess.run(
            ["git", "-C", str(project_dir), "status", "--porcelain"],
            capture_output=True, text=True,
            timeout=GIT_STATUS_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return []
    if status.returncode != 0:
        return []

    raw_lines = [line for line in status.stdout.splitlines() if line.strip()]
    if not raw_lines:
        return []

    diffmap: dict[str, tuple[int, int]] = {}
    for diff_cmd in (
        ["git", "-C", str(project_dir), "diff", "--numstat"],
        ["git", "-C", str(project_dir), "diff", "--cached", "--numstat"],
    ):
        try:
            r = subprocess.run(
                diff_cmd, capture_output=True, text=True,
                timeout=GIT_STATUS_TIMEOUT,
            )
        except Exception:
            continue
        for dl in r.stdout.splitlines():
            parts = dl.split("\t", 2)
            if len(parts) == 3:
                added, deleted = parts[0], parts[1]
                if added != "-":
                    a, d = int(added), int(deleted)
                    fp = parts[2]
                    prev_a, prev_d = diffmap.get(fp, (0, 0))
                    diffmap[fp] = (prev_a + a, prev_d + d)

    result: list[ModifiedFile] = []
    for raw_line in raw_lines:
        filepath = raw_line[3:]
        raw_status = raw_line[:2]
        is_deleted = "D" in raw_status
        is_untracked = "?" in raw_status
        if is_deleted:
            status_label = "D"
        elif is_untracked:
            status_label = "?"
        elif "A" in raw_status or "R" in raw_status or "C" in raw_status:
            status_label = raw_status.strip()[:1]
        else:
            status_label = "M"
        added, deleted = diffmap.get(filepath, (0, 0))
        result.append(ModifiedFile(
            filepath=filepath,
            status=status_label,
            added=added,
            deleted=deleted,
        ))
    return result


def get_file_diff_content(
    project_dir: Path, filepath: str
) -> tuple[str | None, str | None]:
    after: str | None = None
    current_path = project_dir / filepath
    try:
        after = current_path.read_text()
    except Exception:
        after = "" if current_path.exists() else None

    before: str | None = None
    try:
        r = subprocess.run(
            ["git", "-C", str(project_dir), "show", f"HEAD:{filepath}"],
            capture_output=True, text=True, timeout=5.0,
        )
        if r.returncode == 0:
            before = r.stdout
    except Exception:
        pass

    if before == after:
        return None, None
    if before is None and after is None:
        return None, None
    return before, after or ""
