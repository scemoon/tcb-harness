import re
from pathlib import Path

_FR_TAG_RE = re.compile(r"@(?P<prefix>[A-Z]+)-FR-(?P<number>\d+)")
_SCENARIO_RE = re.compile(r"^\s*(Scenario|Scenario Outline|Scenario Template)\s*:")
_TAG_CATEGORY_RE = re.compile(r"@(?P<cat>positive|negative|edge)")


def _find_feature_files(root: Path) -> list[Path]:
    return sorted(Path(root).rglob("*.feature"))


def _parse_feature_file(path: Path) -> list[dict]:
    scenarios = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return scenarios

    lines = text.split("\n")
    current_tags = set()
    current_frs = set()
    in_scenario = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("@"):
            for m in _FR_TAG_RE.finditer(stripped):
                current_frs.add(f"{m.group('prefix')}-FR-{m.group('number')}")
            for m in _TAG_CATEGORY_RE.finditer(stripped):
                current_tags.add(m.group("cat"))
            continue

        if _SCENARIO_RE.match(stripped):
            if current_frs or current_tags:
                scenarios.append({
                    "frs": set(current_frs),
                    "tags": set(current_tags),
                    "file": str(path),
                    "name": stripped,
                })
            current_tags = set()
            current_frs = set()

    return scenarios


def run_bdd_check(root: Path) -> dict:
    checks = []
    feature_files = _find_feature_files(root)

    if not feature_files:
        return {
            "passed": True,
            "checks": [{
                "name": "bdd-feature-found",
                "status": "pass",
                "message": "No .feature files found yet (project may be empty)",
            }],
        }

    fr_scenarios: dict[str, list[dict]] = {}
    total_scenarios = 0

    for ff in feature_files:
        for sc in _parse_feature_file(ff):
            total_scenarios += 1
            for fr in sc["frs"]:
                fr_scenarios.setdefault(fr, []).append(sc)

    if total_scenarios == 0:
        checks.append({
            "name": "bdd-scenarios",
            "status": "fail",
            "message": f"Found {len(feature_files)} .feature files but no Scenario definitions",
        })
        return {"passed": False, "checks": checks}

    checks.append({
        "name": "bdd-total-scenarios",
        "status": "pass",
        "message": f"Found {total_scenarios} scenarios across {len(feature_files)} feature files",
    })

    frs_with_issues = []
    frs_ok = []

    for fr, scenarios in sorted(fr_scenarios.items()):
        positive = sum(1 for s in scenarios if "positive" in s["tags"])
        negative = sum(1 for s in scenarios if "negative" in s["tags"])
        edge = sum(1 for s in scenarios if "edge" in s["tags"])
        categories = {"positive": positive, "negative": negative, "edge": edge}

        missing = [cat for cat, count in categories.items() if count == 0]
        if missing:
            frs_with_issues.append((fr, missing, categories))
        else:
            frs_ok.append(fr)

    if frs_ok:
        checks.append({
            "name": "bdd-fr-coverage",
            "status": "pass",
            "message": f"FRs with complete coverage (positive+negative+edge): {', '.join(frs_ok)}",
        })

    for fr, missing, categories in frs_with_issues:
        details = ", ".join(f"{k}={v}" for k, v in categories.items())
        checks.append({
            "name": "bdd-fr-incomplete",
            "status": "warn",
            "message": f"{fr}: missing categories: {', '.join(missing)} ({details})",
        })

    # Check cross-stack coverage for INT-FR
    cross_stack_files = [f for f in feature_files if "cross-stack" in str(f)]
    int_frs = {fr for fr in fr_scenarios if fr.startswith("INT-")}

    if int_frs:
        cross_int_frs = set()
        for f in cross_stack_files:
            for sc in _parse_feature_file(f):
                for fr in sc["frs"]:
                    if fr.startswith("INT-"):
                        cross_int_frs.add(fr)

        missing_cross = int_frs - cross_int_frs
        if missing_cross:
            checks.append({
                "name": "bdd-cross-stack-missing",
                "status": "warn",
                "message": f"INT-FRs without cross-stack feature: {', '.join(sorted(missing_cross))}",
            })
        else:
            checks.append({
                "name": "bdd-cross-stack",
                "status": "pass",
                "message": f"All {len(int_frs)} INT-FRs have cross-stack feature coverage",
            })

    has_fail = any(c["status"] == "fail" for c in checks)
    return {"passed": not has_fail, "checks": checks}
