#!/usr/bin/env python3
"""contract_diff.py — Compare contract versions for backward compatibility.

Supports OpenAPI 3.1 and AsyncAPI 3.0 contract formats.
Outputs a contract-diff artifact and exits 0 if backward-compatible,
1 if breaking changes detected.

Usage:
  contract_diff.py --base main --head HEAD [--project-root PATH] [--output json|markdown|summary] [--fail-on-breaking]
"""

import argparse
import json
import sys
import tempfile
import subprocess
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, List
from enum import Enum


class ChangeType(Enum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"


class ChangeSeverity(Enum):
    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"


@dataclass
class Change:
    type: ChangeType
    severity: ChangeSeverity
    category: str
    location: str
    detail: str
    file: str = ""
    line: int = 0
    breaking: bool = False
    old_value: Optional[str] = None
    new_value: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        d["severity"] = self.severity.value
        return d


@dataclass
class DiffResult:
    breaking: bool = False
    changes: List[Change] = field(default_factory=list)
    file_count: int = 0
    version_bump: ChangeSeverity = ChangeSeverity.PATCH
    base_ref: str = ""
    head_ref: str = ""
    files_checked: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["changes"] = [c.to_dict() for c in self.changes]
        d["version_bump"] = self.version_bump.value
        return d


class YAMLLocationResolver:
    def __init__(self, content: str):
        self.lines = content.splitlines()
        self.line_map = self._build_line_map()

    def _build_line_map(self) -> dict[str, int]:
        mapping = {}
        path_stack = []
        for i, line in enumerate(self.lines, 1):
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(stripped)
            key = stripped.split(":")[0].strip()
            if key and not key.startswith("-"):
                while path_stack and path_stack[-1][1] >= indent:
                    path_stack.pop()
                path_stack.append((key, indent))
                path = ".".join(p[0] for p in path_stack)
                mapping[path] = i
        return mapping

    def get_line(self, path: str) -> int:
        return self.line_map.get(path, 0)


def _load_yaml_with_lines(path: Path) -> tuple[dict, YAMLLocationResolver]:
    import yaml
    content = path.read_text(encoding="utf-8")
    data = yaml.safe_load(content) or {}
    return data, YAMLLocationResolver(content)


def _load_yaml_from_string(content: str) -> dict:
    import yaml
    return yaml.safe_load(content) or {}


def _find_contracts(project_root: Path) -> list[Path]:
    contracts_dir = project_root / "aidlc" / "contracts"
    result = []
    for sub in ["api", "events"]:
        d = contracts_dir / sub
        if d.exists():
            result.extend(sorted(d.glob("*.yaml")))
    return result


def _get_yaml_line(resolver: Optional[YAMLLocationResolver], path: str) -> int:
    if resolver:
        return resolver.get_line(path)
    return 0


def _compare_values(old: Any, new: Any, path: str) -> List[Change]:
    changes = []
    if old == new:
        return changes

    if isinstance(old, dict) and isinstance(new, dict):
        all_keys = set(old.keys()) | set(new.keys())
        for k in sorted(all_keys):
            subpath = f"{path}.{k}" if path else k
            if k not in old:
                changes.append(Change(ChangeType.ADDED, ChangeSeverity.MINOR, "property", subpath,
                                    f"Added property '{k}'", new_value=str(new[k])))
            elif k not in new:
                changes.append(Change(ChangeType.REMOVED, ChangeSeverity.MAJOR, "property", subpath,
                                    f"BREAKING: Removed property '{k}'", old_value=str(old[k]), breaking=True))
            else:
                changes.extend(_compare_values(old[k], new[k], subpath))
    elif isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new) or any(o != n for o, n in zip(old, new)):
            changes.append(Change(ChangeType.CHANGED, ChangeSeverity.MINOR, "array", path,
                                f"Array changed", old_value=str(old), new_value=str(new)))
    else:
        changes.append(Change(ChangeType.CHANGED, ChangeSeverity.PATCH, "value", path,
                            f"Value changed", old_value=str(old), new_value=str(new)))
    return changes


def _diff_openapi(base: dict, head: dict, base_resolver: Optional[YAMLLocationResolver],
                  head_resolver: Optional[YAMLLocationResolver], file: str) -> List[Change]:
    changes = []
    base_paths = base.get("paths", {})
    head_paths = head.get("paths", {})
    all_paths = set(base_paths.keys()) | set(head_paths.keys())

    for p in sorted(all_paths):
        base_methods = base_paths.get(p, {})
        head_methods = head_paths.get(p, {})

        for method in sorted(set(base_methods.keys()) | set(head_methods.keys())):
            loc = f"paths.{p}.{method}"
            line = _get_yaml_line(head_resolver, loc) if head_resolver else 0
            base_loc = _get_yaml_line(base_resolver, loc) if base_resolver else 0

            if method not in base_methods:
                changes.append(Change(ChangeType.ADDED, ChangeSeverity.MINOR, "endpoint", f"{method.upper()} {p}",
                                    f"New endpoint: {method.upper()} {p}", file, line, severity=ChangeSeverity.MINOR))
                continue
            if method not in head_methods:
                changes.append(Change(ChangeType.REMOVED, ChangeSeverity.MAJOR, "endpoint", f"{method.upper()} {p}",
                                    f"BREAKING: Removed {method.upper()} {p}", file, base_loc, breaking=True))
                continue

            b_op = base_methods[method]
            h_op = head_methods[method]

            b_params = {f"{p.get('in')}:{p.get('name')}": p for p in b_op.get("parameters", [])}
            h_params = {f"{p.get('in')}:{p.get('name')}": p for p in h_op.get("parameters", [])}
            all_params = set(b_params.keys()) | set(h_params.keys())

            for pk in sorted(all_params):
                param_loc = f"{loc}.parameters.{pk}"
                pline = _get_yaml_line(head_resolver, param_loc) if head_resolver else 0
                if pk not in b_params:
                    changes.append(Change(ChangeType.ADDED, ChangeSeverity.MINOR, "parameter", f"{method.upper()} {p} {pk}",
                                        f"New parameter: {pk}", file, pline))
                elif pk not in h_params:
                    changes.append(Change(ChangeType.REMOVED, ChangeSeverity.MAJOR, "parameter", f"{method.upper()} {p} {pk}",
                                        f"BREAKING: Removed parameter {pk}", file, pline, breaking=True))
                else:
                    b_req = b_params[pk].get("required", False)
                    h_req = h_params[pk].get("required", False)
                    if not b_req and h_req:
                        changes.append(Change(ChangeType.CHANGED, ChangeSeverity.MAJOR, "parameter", f"{method.upper()} {p} {pk}",
                                            f"BREAKING: Parameter {pk} became required", file, pline, breaking=True))

            b_resp = b_op.get("responses", {})
            h_resp = h_op.get("responses", {})
            for code in sorted(set(b_resp.keys()) | set(h_resp.keys())):
                resp_loc = f"{loc}.responses.{code}"
                rline = _get_yaml_line(head_resolver, resp_loc) if head_resolver else 0
                if code not in b_resp:
                    changes.append(Change(ChangeType.ADDED, ChangeSeverity.MINOR, "response", f"{method.upper()} {p} {code}",
                                        f"New response status {code}", file, rline))
                elif code not in h_resp:
                    changes.append(Change(ChangeType.REMOVED, ChangeSeverity.MAJOR, "response", f"{method.upper()} {p} {code}",
                                        f"BREAKING: Removed response status {code}", file, rline, breaking=True))
                else:
                    b_content = b_resp[code].get("content", {})
                    h_content = h_resp[code].get("content", {})
                    for mt in sorted(set(b_content.keys()) | set(h_content.keys())):
                        if mt not in b_content:
                            changes.append(Change(ChangeType.ADDED, ChangeSeverity.MINOR, "response_content", f"{method.upper()} {p} {code} {mt}",
                                                f"New response media type {mt}", file, rline))
                        elif mt not in h_content:
                            changes.append(Change(ChangeType.REMOVED, ChangeSeverity.MAJOR, "response_content", f"{method.upper()} {p} {code} {mt}",
                                                f"BREAKING: Removed response media type {mt}", file, rline, breaking=True))

            b_req_body = b_op.get("requestBody", {})
            h_req_body = h_op.get("requestBody", {})
            if b_req_body and not h_req_body:
                changes.append(Change(ChangeType.REMOVED, ChangeSeverity.MAJOR, "request_body", f"{method.upper()} {p}",
                                    f"BREAKING: Removed request body", file, _get_yaml_line(base_resolver, f"{loc}.requestBody") or 0, breaking=True))
            elif not b_req_body and h_req_body:
                changes.append(Change(ChangeType.ADDED, ChangeSeverity.MINOR, "request_body", f"{method.upper()} {p}",
                                    f"New request body", file, _get_yaml_line(head_resolver, f"{loc}.requestBody") or 0))
            elif b_req_body and h_req_body:
                b_content = b_req_body.get("content", {})
                h_content = h_req_body.get("content", {})
                for mt in sorted(set(b_content.keys()) | set(h_content.keys())):
                    if mt not in b_content:
                        changes.append(Change(ChangeType.ADDED, ChangeSeverity.MINOR, "request_content", f"{method.upper()} {p} {mt}",
                                            f"New request media type {mt}", file, _get_yaml_line(head_resolver, f"{loc}.requestBody.content.{mt}") or 0))
                    elif mt not in h_content:
                        changes.append(Change(ChangeType.REMOVED, ChangeSeverity.MAJOR, "request_content", f"{method.upper()} {p} {mt}",
                                            f"BREAKING: Removed request media type {mt}", file, _get_yaml_line(base_resolver, f"{loc}.requestBody.content.{mt}") or 0, breaking=True))

    base_components = base.get("components", {}).get("schemas", {})
    head_components = head.get("components", {}).get("schemas", {})
    all_schemas = set(base_components.keys()) | set(head_components.keys())

    for sname in sorted(all_schemas):
        sloc = f"components.schemas.{sname}"
        line = _get_yaml_line(head_resolver, sloc) if head_resolver else 0
        if sname not in base_components:
            changes.append(Change(ChangeType.ADDED, ChangeSeverity.MINOR, "schema", sname,
                                f"New schema: {sname}", file, line))
        elif sname not in head_components:
            changes.append(Change(ChangeType.REMOVED, ChangeSeverity.MAJOR, "schema", sname,
                                f"BREAKING: Removed schema: {sname}", file, line, breaking=True))
        else:
            b_schema = base_components[sname]
            h_schema = head_components[sname]

            b_req = set(b_schema.get("required", []))
            h_req = set(h_schema.get("required", []))
            for f in sorted(h_req - b_req):
                changes.append(Change(ChangeType.CHANGED, ChangeSeverity.MAJOR, "schema_required", f"{sname}.required.{f}",
                                    f"BREAKING: Required field added to {sname}: '{f}'", file, line, breaking=True))

            b_props = b_schema.get("properties", {})
            h_props = h_schema.get("properties", {})
            for f in sorted(set(b_props.keys()) - set(h_props.keys())):
                changes.append(Change(ChangeType.REMOVED, ChangeSeverity.MAJOR, "schema_property", f"{sname}.properties.{f}",
                                    f"BREAKING: Field removed from {sname}: '{f}'", file, line, breaking=True))

            for f in sorted(set(h_props.keys()) - set(b_props.keys())):
                changes.append(Change(ChangeType.ADDED, ChangeSeverity.MINOR, "schema_property", f"{sname}.properties.{f}",
                                    f"New field added to {sname}: '{f}'", file, line))

            for f in sorted(set(b_props.keys()) & set(h_props.keys())):
                changes.extend(_compare_values(b_props[f], h_props[f], f"{sname}.properties.{f}"))

            b_enum = b_schema.get("enum")
            h_enum = h_schema.get("enum")
            if b_enum != h_enum:
                if h_enum and b_enum and set(b_enum).issubset(set(h_enum)):
                    changes.append(Change(ChangeType.CHANGED, ChangeSeverity.MINOR, "schema_enum", f"{sname}.enum",
                                        f"Enum values added to {sname}", file, line))
                else:
                    changes.append(Change(ChangeType.CHANGED, ChangeSeverity.MAJOR, "schema_enum", f"{sname}.enum",
                                        f"BREAKING: Enum values changed for {sname}", file, line, breaking=True))

    return changes


def _get_yaml_line(resolver: Optional[YAMLLocationResolver], path: str) -> int:
    if resolver:
        return resolver.get_line(path)
    return 0


def _diff_asyncapi(base: dict, head: dict, base_resolver: Optional[YAMLLocationResolver],
                   head_resolver: Optional[YAMLLocationResolver], file: str) -> List[Change]:
    changes = []
    base_channels = base.get("channels", {})
    head_channels = head.get("channels", {})
    all_channels = set(base_channels.keys()) | set(head_channels.keys())

    for ch in sorted(all_channels):
        cloc = f"channels.{ch}"
        line = _get_yaml_line(head_resolver, cloc) if head_resolver else 0
        base_line = _get_yaml_line(base_resolver, cloc) if base_resolver else 0

        if ch not in base_channels:
            changes.append(Change(ChangeType.ADDED, ChangeSeverity.MINOR, "channel", ch,
                                f"New channel: {ch}", file, line, severity=ChangeSeverity.MINOR))
        elif ch not in head_channels:
            changes.append(Change(ChangeType.REMOVED, ChangeSeverity.MAJOR, "channel", ch,
                                f"BREAKING: Removed channel: {ch}", file, base_line, breaking=True))
        else:
            b_ch = base_channels[ch]
            h_ch = head_channels[ch]

            b_ops = b_ch.get("operations", {})
            h_ops = h_ch.get("operations", {})
            all_ops = set(b_ops.keys()) | set(h_ops.keys())

            for op in sorted(all_ops):
                op_loc = f"{cloc}.operations.{op}"
                op_line = _get_yaml_line(head_resolver, op_loc) if head_resolver else 0
                b_op_line = _get_yaml_line(base_resolver, op_loc) if base_resolver else 0

                if op not in b_ops:
                    changes.append(Change(ChangeType.ADDED, ChangeSeverity.MINOR, "operation", f"{ch}.{op}",
                                        f"New operation: {op} on {ch}", file, op_line))
                elif op not in h_ops:
                    changes.append(Change(ChangeType.REMOVED, ChangeSeverity.MAJOR, "operation", f"{ch}.{op}",
                                        f"BREAKING: Removed operation {op} on {ch}", file, b_op_line, breaking=True))
                else:
                    b_op = b_ops[op]
                    h_op = h_ops[op]

                    b_msg = b_op.get("message", {})
                    h_msg = h_op.get("message", {})

                    if b_msg.get("$ref") != h_msg.get("$ref"):
                        if not b_msg.get("$ref"):
                            changes.append(Change(ChangeType.ADDED, ChangeSeverity.MINOR, "message", f"{ch}.{op}.message",
                                                f"New message reference on {ch}.{op}", file, op_line))
                        elif not h_msg.get("$ref"):
                            changes.append(Change(ChangeType.REMOVED, ChangeSeverity.MAJOR, "message", f"{ch}.{op}.message",
                                                f"BREAKING: Removed message reference on {ch}.{op}", file, b_op_line, breaking=True))
                        else:
                            changes.append(Change(ChangeType.CHANGED, ChangeSeverity.MAJOR, "message", f"{ch}.{op}.message",
                                                f"BREAKING: Message reference changed on {ch}.{op}", file, op_line, breaking=True))

                    b_bindings = b_op.get("bindings", {})
                    h_bindings = h_op.get("bindings", {})
                    all_bindings = set(b_bindings.keys()) | set(h_bindings.keys())
                    for bnd in sorted(all_bindings):
                        if bnd not in b_bindings:
                            changes.append(Change(ChangeType.ADDED, ChangeSeverity.MINOR, "binding", f"{ch}.{op}.bindings.{bnd}",
                                                f"New binding {bnd} on {ch}.{op}", file, op_line))
                        elif bnd not in h_bindings:
                            changes.append(Change(ChangeType.REMOVED, ChangeSeverity.MAJOR, "binding", f"{ch}.{op}.bindings.{bnd}",
                                                f"BREAKING: Removed binding {bnd} on {ch}.{op}", file, op_line, breaking=True))

            b_ch_bindings = b_ch.get("bindings", {})
            h_ch_bindings = h_ch.get("bindings", {})
            all_ch_bindings = set(b_ch_bindings.keys()) | set(h_ch_bindings.keys())
            for bnd in sorted(all_ch_bindings):
                if bnd not in b_ch_bindings:
                    changes.append(Change(ChangeType.ADDED, ChangeSeverity.MINOR, "channel_binding", f"{ch}.bindings.{bnd}",
                                        f"New channel binding {bnd} on {ch}", file, line))
                elif bnd not in h_ch_bindings:
                    changes.append(Change(ChangeType.REMOVED, ChangeSeverity.MAJOR, "channel_binding", f"{ch}.bindings.{bnd}",
                                        f"BREAKING: Removed channel binding {bnd} on {ch}", file, base_line, breaking=True))

            b_messages = b_ch.get("messages", {})
            h_messages = h_ch.get("messages", {})
            all_msgs = set(b_messages.keys()) | set(h_messages.keys())
            for msg in sorted(all_msgs):
                msg_loc = f"{cloc}.messages.{msg}"
                msg_line = _get_yaml_line(head_resolver, msg_loc) if head_resolver else 0
                b_msg_line = _get_yaml_line(base_resolver, msg_loc) if base_resolver else 0
                if msg not in b_messages:
                    changes.append(Change(ChangeType.ADDED, ChangeSeverity.MINOR, "message", f"{ch}.messages.{msg}",
                                        f"New message: {msg} on {ch}", file, msg_line))
                elif msg not in h_messages:
                    changes.append(Change(ChangeType.REMOVED, ChangeSeverity.MAJOR, "message", f"{ch}.messages.{msg}",
                                        f"BREAKING: Removed message: {msg} on {ch}", file, b_msg_line, breaking=True))

    base_components = base.get("components", {}).get("schemas", {})
    head_components = head.get("components", {}).get("schemas", {})
    all_schemas = set(base_components.keys()) | set(head_components.keys())

    for sname in sorted(all_schemas):
        sloc = f"components.schemas.{sname}"
        line = _get_yaml_line(head_resolver, sloc) if head_resolver else 0
        if sname not in base_components:
            changes.append(Change(ChangeType.ADDED, ChangeSeverity.MINOR, "schema", sname,
                                f"New schema: {sname}", file, line))
        elif sname not in head_components:
            changes.append(Change(ChangeType.REMOVED, ChangeSeverity.MAJOR, "schema", sname,
                                f"BREAKING: Removed schema: {sname}", file, line, breaking=True))
        else:
            b_schema = base_components[sname]
            h_schema = head_components[sname]

            b_req = set(b_schema.get("required", []))
            h_req = set(h_schema.get("required", []))
            for f in sorted(h_req - b_req):
                changes.append(Change(ChangeType.CHANGED, ChangeSeverity.MAJOR, "schema_required", f"{sname}.required.{f}",
                                    f"BREAKING: Required field added to {sname}: '{f}'", file, line, breaking=True))

            b_props = b_schema.get("properties", {})
            h_props = h_schema.get("properties", {})
            for f in sorted(set(b_props.keys()) - set(h_props.keys())):
                changes.append(Change(ChangeType.REMOVED, ChangeSeverity.MAJOR, "schema_property", f"{sname}.properties.{f}",
                                    f"BREAKING: Field removed from {sname}: '{f}'", file, line, breaking=True))

            for f in sorted(set(h_props.keys()) - set(b_props.keys())):
                changes.append(Change(ChangeType.ADDED, ChangeSeverity.MINOR, "schema_property", f"{sname}.properties.{f}",
                                    f"New field added to {sname}: '{f}'", file, line))

            for f in sorted(set(b_props.keys()) & set(h_props.keys())):
                changes.extend(_compare_values(b_props[f], h_props[f], f"{sname}.properties.{f}"))

            b_enum = b_schema.get("enum")
            h_enum = h_schema.get("enum")
            if b_enum != h_enum:
                if h_enum and b_enum and set(b_enum).issubset(set(h_enum)):
                    changes.append(Change(ChangeType.CHANGED, ChangeSeverity.MINOR, "schema_enum", f"{sname}.enum",
                                        f"Enum values added to {sname}", file, line))
                else:
                    changes.append(Change(ChangeType.CHANGED, ChangeSeverity.MAJOR, "schema_enum", f"{sname}.enum",
                                        f"BREAKING: Enum values changed for {sname}", file, line, breaking=True))

    return changes


def _calculate_version_bump(changes: List[Change]) -> ChangeSeverity:
    max_severity = ChangeSeverity.PATCH
    for c in changes:
        if c.breaking or c.severity == ChangeSeverity.MAJOR:
            return ChangeSeverity.MAJOR
        elif c.severity == ChangeSeverity.MINOR:
            max_severity = ChangeSeverity.MINOR
    return max_severity


def diff(project_root: Path, base_ref: str = "main", head_ref: str = "HEAD") -> DiffResult:
    import subprocess

    contracts = _find_contracts(project_root)
    result = DiffResult(base_ref=base_ref, head_ref=head_ref, file_count=len(contracts))
    result.files_checked = [str(c.relative_to(project_root)) for c in contracts]

    for contract_file in contracts:
        rel = contract_file.relative_to(project_root)
        try:
            base_content = subprocess.run(
                ["git", "show", f"{base_ref}:{rel}"],
                capture_output=True, text=True, cwd=project_root,
            ).stdout
        except Exception as e:
            base_content = ""
            result.changes.append(Change(ChangeType.CHANGED, ChangeSeverity.PATCH, "git", str(rel),
                                       f"Warning: Could not read base ref {base_ref}:{rel}: {e}",
                                       file=str(rel), severity=ChangeSeverity.PATCH))

        try:
            head_content = subprocess.run(
                ["git", "show", f"{head_ref}:{rel}"],
                capture_output=True, text=True, cwd=project_root,
            ).stdout
        except Exception as e:
            try:
                head_content = contract_file.read_text(encoding="utf-8")
            except Exception as e2:
                head_content = ""
                result.changes.append(Change(ChangeType.CHANGED, ChangeSeverity.PATCH, "git", str(rel),
                                           f"Warning: Could not read head ref {head_ref}:{rel} or local file: {e2}",
                                           file=str(rel), severity=ChangeSeverity.PATCH))

        if not base_content.strip() and not head_content.strip():
            continue

        base_data = {}
        base_resolver = None
        if base_content.strip():
            with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
                f.write(base_content)
                base_path = f.name
            try:
                base_data, base_resolver = _load_yaml_with_lines(Path(base_path))
            finally:
                Path(base_path).unlink(missing_ok=True)

        head_data, head_resolver = _load_yaml_with_lines(contract_file)

        if not base_data and not head_data:
            continue

        is_openapi = "openapi" in base_data or "openapi" in head_data
        if is_openapi:
            changes = _diff_openapi(base_data, head_data, base_resolver, head_resolver, str(rel))
        else:
            changes = _diff_asyncapi(base_data, head_data, base_resolver, head_resolver, str(rel))

        for c in changes:
            c.file = str(rel)
            if c.breaking:
                result.breaking = True

        result.changes.extend(changes)

    result.version_bump = _calculate_version_bump(result.changes)
    return result


def write_diff_report(project_root: Path, result: DiffResult, change_id: str = "",
                      output_format: str = "markdown") -> Path:
    change_dir = project_root / "aidlc" / "openspec" / "changes"
    if change_id:
        change_dir = change_dir / change_id
    else:
        changes_list = sorted(change_dir.iterdir()) if change_dir.exists() else []
        change_dir = change_dir / (changes_list[-1].name if changes_list else "latest")
    change_dir.mkdir(parents=True, exist_ok=True)

    if output_format == "json":
        output = change_dir / "contract-diff.json"
        output.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    elif output_format == "summary":
        output = change_dir / "contract-diff-summary.txt"
        breaking_count = sum(1 for c in result.changes if c.breaking)
        major_count = sum(1 for c in result.changes if c.severity == ChangeSeverity.MAJOR)
        minor_count = sum(1 for c in result.changes if c.severity == ChangeSeverity.MINOR)
        patch_count = sum(1 for c in result.changes if c.severity == ChangeSeverity.PATCH)
        lines = [
            "Contract Diff Summary",
            "=" * 40,
            f"Base ref: {result.base_ref}",
            f"Head ref: {result.head_ref}",
            f"Files checked: {result.file_count}",
            f"Total changes: {len(result.changes)}",
            f"  Breaking (major): {breaking_count}",
            f"  Minor: {minor_count}",
            f"  Patch: {patch_count}",
            f"Recommended version bump: {result.version_bump.value.upper()}",
            f"Breaking changes detected: {'YES' if result.breaking else 'NO'}",
        ]
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        output = change_dir / "contract-diff.md"
        lines = ["# Contract Diff", "", f"> Auto-generated by contract_diff.py",
                 f"> Base: {result.base_ref} → Head: {result.head_ref}", "",
                 "## Summary", "",
                 f"| Field | Value |",
                 f"|-------|-------|",
                 f"| Breaking? | {'Yes' if result.breaking else 'No'} |",
                 f"| Recommended version bump | {result.version_bump.value.upper()} |",
                 f"| Files checked | {result.file_count} |",
                 f"| Total changes | {len(result.changes)} |",
                 ""]

        if result.changes:
            lines.append("## Changes")
            lines.append("")
            for c in result.changes:
                icon = "🔴" if c.breaking else ("🟡" if c.severity == ChangeSeverity.MINOR else "🟢")
                lines.append(f"- {icon} **[{c.severity.value.upper()}]** [{c.type.value}] {c.detail}")
                lines.append(f"  - File: `{c.file}`" + (f":{c.line}" if c.line else ""))
                lines.append(f"  - Category: {c.category}")
                if c.old_value:
                    lines.append(f"  - Old: `{c.old_value}`")
                if c.new_value:
                    lines.append(f"  - New: `{c.new_value}`")
            lines.append("")

        if result.breaking:
            lines.append("## ⚠ BREAKING CHANGES DETECTED")
            lines.append("")
            lines.append("Human approval required before merging.")
            lines.append("")

        lines.append("---")
        lines.append(f"*Generated by contract_diff.py*")

        output.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return output


def main():
    parser = argparse.ArgumentParser(description="Compare contract versions")
    parser.add_argument("--base-ref", default="main", help="Base git ref (default: main)")
    parser.add_argument("--head-ref", default="HEAD", help="Head git ref (default: HEAD)")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--output", default="markdown", choices=["json", "markdown", "summary"],
                        help="Output format (default: markdown)")
    parser.add_argument("--output-id", default="", help="Output change ID directory (optional)")
    parser.add_argument("--fail-on-breaking", action="store_true",
                        help="Exit with code 1 if breaking changes detected (CI gate)")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    result = diff(root, args.base_ref, args.head_ref)

    if result.changes:
        output_path = write_diff_report(root, result, args.output_id, args.output)
        print(f"Contract diff written to: {output_path.relative_to(root)}")
    else:
        print("No contract changes detected")

    breaking_count = sum(1 for c in result.changes if c.breaking)
    major_count = sum(1 for c in result.changes if c.severity == ChangeSeverity.MAJOR)
    minor_count = sum(1 for c in result.changes if c.severity == ChangeSeverity.MINOR)
    patch_count = sum(1 for c in result.changes if c.severity == ChangeSeverity.PATCH)

    print(f"\nSummary:")
    print(f"  Files checked: {result.file_count}")
    print(f"  Total changes: {len(result.changes)}")
    print(f"  Breaking (major): {breaking_count}")
    print(f"  Minor: {minor_count}")
    print(f"  Patch: {patch_count}")
    print(f"  Recommended version bump: {result.version_bump.value.upper()}")

    if result.changes:
        print("\nChanges:")
        for c in result.changes:
            icon = "BREAKING" if c.breaking else c.severity.value.upper()
            loc = f"{c.file}:{c.line}" if c.line else c.file
            print(f"  [{icon}] {c.category}:{c.location} - {c.detail}")

    if result.breaking:
        print("\n⚠ Breaking changes detected — human approval required")
        if args.fail_on_breaking:
            sys.exit(1)
        else:
            sys.exit(1)
    else:
        print("\n✓ All contract changes are backward-compatible")
        sys.exit(0)


if __name__ == "__main__":
    main()