from __future__ import annotations

import re
from pathlib import Path

import yaml

_FR_TAG_RE = re.compile(r"@(?P<prefix>[A-Z]+)-FR-(?P<number>\d+)")
_FR_REF_RE = re.compile(
    r"(?P<prefix>[A-Z]+)-FR-(?P<number>\d+)",
)


def _load_project_yaml(root: Path) -> dict | None:
    p = root / "aidlc" / "project.yaml"
    if not p.exists():
        return None
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _build_fr_map(project: dict) -> dict[str, str]:
    fr_map = {}
    components = project.get("stack", {}).get("components", [])
    for c in components:
        prefix = c.get("fr_prefix", "")
        if prefix:
            fr_map[prefix] = c.get("owns", "?")
    cross = project.get("stack", {}).get("cross_cutting", {})
    if cross:
        fr_map["INT"] = "aidlc/contracts/ + aidlc/packages/shared/"
    return fr_map


def _collect_fr_from_spec(root: Path) -> set[str]:
    changes_dir = root / "aidlc" / "openspec" / "changes"
    if not changes_dir.exists():
        return set()
    frs = set()
    for spec_file in changes_dir.rglob("spec-delta.md"):
        text = spec_file.read_text(encoding="utf-8")
        for m in _FR_REF_RE.finditer(text):
            frs.add(f"{m.group('prefix')}-FR-{m.group('number')}")
    return frs


def _collect_fr_from_features(root: Path) -> dict[str, set[str]]:
    frs_by_tag = {}
    for feature_file in Path(root).rglob("*.feature"):
        text = feature_file.read_text(encoding="utf-8")
        for m in _FR_TAG_RE.finditer(text):
            fr = f"{m.group('prefix')}-FR-{m.group('number')}"
            tag = m.group(0)
            frs_by_tag.setdefault(tag, set()).add(fr)
    all_frs = set()
    for fr_set in frs_by_tag.values():
        all_frs.update(fr_set)
    return all_frs, frs_by_tag


def run_fr_check(root: Path) -> dict:
    checks = []

    project = _load_project_yaml(root)
    if project is None:
        return {
            "passed": False,
            "checks": [{
                "name": "fr-project-yaml",
                "status": "fail",
                "message": "aidlc/project.yaml not found",
            }],
        }

    fr_map = _build_fr_map(project)
    if not fr_map:
        checks.append({
            "name": "fr-prefix-defined",
            "status": "fail",
            "message": "No FR prefixes defined in project.yaml stack.components",
        })
        return {"passed": False, "checks": checks}

    spec_frs = _collect_fr_from_spec(root)
    feature_frs, frs_by_tag = _collect_fr_from_features(root)

    if not spec_frs and not feature_frs:
        return {
            "passed": True,
            "checks": [{
                "name": "fr-skip",
                "status": "pass",
                "message": "No FR references found yet (project may be empty)",
            }],
        }

    unknown_prefixes = set()
    for fr in spec_frs | feature_frs:
        prefix = fr.split("-")[0]
        if prefix not in fr_map:
            unknown_prefixes.add(prefix)

    if unknown_prefixes:
        checks.append({
            "name": "fr-unknown-prefix",
            "status": "fail",
            "message": f"FR prefixes not in project.yaml: {', '.join(sorted(unknown_prefixes))}",
        })
    else:
        checks.append({
            "name": "fr-unknown-prefix",
            "status": "pass",
            "message": "All FR prefixes are defined in project.yaml",
        })

    spec_only = spec_frs - feature_frs
    feature_only = feature_frs - spec_frs

    if spec_only:
        checks.append({
            "name": "fr-spec-without-feature",
            "status": "warn",
            "message": f"FRs in spec-delta but not in any .feature file: {', '.join(sorted(spec_only))}",
        })

    if feature_only:
        checks.append({
            "name": "fr-feature-without-spec",
            "status": "warn",
            "message": f"FRs in .feature files but not in spec-delta: {', '.join(sorted(feature_only))}",
        })

    if not spec_only and not feature_only:
        checks.append({
            "name": "fr-consistency",
            "status": "pass",
            "message": f"All {len(spec_frs)} FRs are consistent between spec and feature files",
        })

    has_fail = any(c["status"] == "fail" for c in checks)
    return {"passed": not has_fail, "checks": checks}
