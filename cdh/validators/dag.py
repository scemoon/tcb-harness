import re
from pathlib import Path

import yaml


def _find_task_lists(root: Path) -> list[Path]:
    changes_dir = root / "aidlc" / "openspec" / "changes"
    if not changes_dir.exists():
        return []
    return sorted(changes_dir.rglob("task-list.md"))


def _parse_task_list(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []

    yaml_blocks = re.findall(
        r"```yaml\s*\n(.*?)```", text, re.DOTALL
    )
    if not yaml_blocks:
        yaml_blocks = re.findall(
            r"```\s*\n(.*?)```", text, re.DOTALL
        )

    for block in yaml_blocks:
        try:
            data = yaml.safe_load(block)
        except Exception:
            continue
        if isinstance(data, dict) and "units" in data:
            return data["units"]
        if isinstance(data, list):
            return data
    return []


def _detect_cycles(units: list[dict]) -> list[str]:
    node_map = {}
    for u in units:
        uid = u.get("id", "")
        if uid:
            node_map[uid] = {
                "depends_on": u.get("depends_on", []) or [],
            }

    edges: list[tuple[str, str]] = []
    for uid, info in node_map.items():
        for dep in info["depends_on"]:
            if dep in node_map:
                edges.append((uid, dep))

    adj: dict[str, list[str]] = {uid: [] for uid in node_map}
    in_degree: dict[str, int] = {uid: 0 for uid in node_map}
    for src, tgt in edges:
        adj[src].append(tgt)
        in_degree[tgt] = in_degree.get(tgt, 0) + 1

    queue = [uid for uid, deg in in_degree.items() if deg == 0]
    visited = 0

    while queue:
        node = queue.pop(0)
        visited += 1
        for neighbor in adj.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited != len(node_map):
        cycle_nodes = [uid for uid, deg in in_degree.items() if deg > 0]
        return cycle_nodes
    return []


def run_dag_check(root: Path) -> dict:
    checks = []
    task_lists = _find_task_lists(root)

    if not task_lists:
        return {
            "passed": True,
            "checks": [{
                "name": "dag-task-list-found",
                "status": "pass",
                "message": "No task-list.md found yet (project may be in Understand phase)",
            }],
        }

    all_units = []
    for tl in task_lists:
        units = _parse_task_list(tl)
        if units:
            all_units.extend(units)

    if not all_units:
        return {
            "passed": True,
            "checks": [{
                "name": "dag-units-parsed",
                "status": "pass",
                "message": "task-list.md exists but no YAML units found (may be placeholder)",
            }],
        }

    checks.append({
        "name": "dag-units-found",
        "status": "pass",
        "message": f"Found {len(all_units)} task units across {len(task_lists)} files",
    })

    cycle_nodes = _detect_cycles(all_units)
    if cycle_nodes:
        checks.append({
            "name": "dag-cycle",
            "status": "fail",
            "message": f"Cycle detected involving units: {', '.join(cycle_nodes)}",
        })
    else:
        checks.append({
            "name": "dag-cycle",
            "status": "pass",
            "message": "No cycles detected in task DAG",
        })

    # Check for units with no depends_on (isolated roots)
    unit_ids = {u.get("id") for u in all_units if u.get("id")}
    all_deps = set()
    for u in all_units:
        for dep in (u.get("depends_on") or []):
            all_deps.add(dep)

    unresolved = all_deps - unit_ids
    if unresolved:
        checks.append({
            "name": "dag-unresolved-dep",
            "status": "warn",
            "message": f"depends_on references units not in task list: {', '.join(sorted(unresolved))}",
        })
    else:
        checks.append({
            "name": "dag-unresolved-dep",
            "status": "pass",
            "message": "All depends_on references resolve to defined units",
        })

    # Check cross-component: tasks consuming INT contract should depend on INT task
    fr_to_unit = {}
    for u in all_units:
        fr = u.get("fr", "")
        if fr:
            fr_to_unit[fr] = u.get("id", "")

    int_fr_defined = {fr for fr in fr_to_unit if fr.startswith("INT-")}
    int_unit_ids = {fr_to_unit[fr] for fr in int_fr_defined}
    consuming_frs = {fr for fr in fr_to_unit if not fr.startswith("INT-") and fr != ""}

    for fr in consuming_frs:
        uid = fr_to_unit[fr]
        unit = next((u for u in all_units if u.get("id") == uid), None)
        if not unit:
            continue
        affected = unit.get("affects", [])
        deps = unit.get("depends_on", [])
        affects = [a for a in (affected or []) if a != "contracts"]

        if len(affects) >= 2:
            has_int_dep = any(d in int_unit_ids for d in deps)
            if not has_int_dep and int_unit_ids:
                checks.append({
                    "name": "dag-cross-component-int",
                    "status": "warn",
                    "message": f"Unit '{uid}' affects {len(affects)} components but has no INT-FR dependency",
                })

    has_fail = any(c["status"] == "fail" for c in checks)
    return {"passed": not has_fail, "checks": checks}
