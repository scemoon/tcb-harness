#!/usr/bin/env python3
"""generate_shared.py — Generate shared types from OpenAPI/AsyncAPI contracts.

Reads aidlc/contracts/api/*.yaml and aidlc/contracts/events/*.yaml,
generates TypeScript/Python types.

Usage:
  generate_shared.py [--project-root PATH]
                     [--ts-outdir DIR] [--py-outdir DIR]
                     [--watch]
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

# ──────────────────────────────────────────────
#  Error Reporting
# ──────────────────────────────────────────────


class GenerateError(Exception):
    def __init__(
        self,
        message: str,
        file: Optional[Path] = None,
        pointer: str = "",
    ):
        self.file = file
        self.pointer = pointer
        parts = []
        if file:
            parts.append(str(file))
        if pointer:
            parts.append(pointer)
        prefix = f"[{' / '.join(parts)}] " if parts else ""
        super().__init__(f"{prefix}{message}")


def _load_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise GenerateError("Root YAML value must be a mapping", file=path)
        return data
    except yaml.YAMLError as e:
        raise GenerateError(f"YAML parse error: {e}", file=path) from e


# ──────────────────────────────────────────────
#  JSON Pointer resolution (RFC 6901)
# ──────────────────────────────────────────────

def _resolve_json_pointer(data: Any, pointer: str) -> Any:
    if not pointer or pointer == "#":
        return data
    parts = pointer.lstrip("#/").split("/")
    current = data
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if current is None:
            return None
    return current


# ──────────────────────────────────────────────
#  $ref Resolution
# ──────────────────────────────────────────────

@dataclass
class RefResult:
    schema: dict
    root: dict
    base_path: Path


def _resolve_ref(ref: str, root: dict, base_path: Path) -> RefResult:
    """Resolve a $ref value.

    Handles:
      - '#/components/schemas/Foo'       (local JSON Pointer)
      - './other.yaml'                   (external file, full doc)
      - './other.yaml#/components/...'   (external file + pointer)
    """
    if ref.startswith("#"):
        resolved = _resolve_json_pointer(root, ref)
        if resolved is None:
            raise GenerateError(f"Cannot resolve $ref '{ref}'", pointer=ref)
        return RefResult(resolved, root, base_path)

    if "#" in ref:
        file_part, pointer = ref.split("#", 1)
        pointer = f"#{pointer}"
    else:
        file_part, pointer = ref, "#"

    ref_path = (base_path.parent / file_part).resolve()
    if not ref_path.exists():
        raise GenerateError(f"$ref file not found: {ref_path}", pointer=ref)
    ext_root = _load_yaml(ref_path)
    if pointer and pointer != "#":
        resolved = _resolve_json_pointer(ext_root, pointer)
        if resolved is None:
            raise GenerateError(
                f"Cannot resolve $ref '{ref}' in {ref_path}",
                file=ref_path,
                pointer=pointer,
            )
        return RefResult(resolved, ext_root, ref_path)
    return RefResult(ext_root, ext_root, ref_path)


# ──────────────────────────────────────────────
#  Schema Normalization ($ref, allOf/oneOf/anyOf)
# ──────────────────────────────────────────────

MAX_DEPTH = 50


def _normalize_schema(
    schema: Any,
    root: dict,
    base_path: Path,
    depth: int = 0,
    *,
    _resolve_refs: bool = True,
) -> Any:
    """Recursively resolve $refs, allOf, oneOf, anyOf.

    When _resolve_refs=False, $ref is preserved as-is (used for
    property/items values so named type references are kept).
    """
    if depth > MAX_DEPTH:
        raise GenerateError("Max recursion depth exceeded resolving schema")
    if not isinstance(schema, dict):
        return schema

    schema = dict(schema)

    # 1. Resolve $ref (only when _resolve_refs is True)
    if _resolve_refs:
        ref = schema.get("$ref")
        if ref:
            rr = _resolve_ref(ref, root, base_path)
            resolved = rr.schema
            if not isinstance(resolved, dict):
                return resolved
            merged = dict(resolved)
            for k, v in schema.items():
                if k != "$ref":
                    merged[k] = v
            return _normalize_schema(merged, rr.root, rr.base_path, depth + 1)

    # 2. Resolve allOf → merge
    if "allOf" in schema:
        merged: dict = {"type": "object"}
        for sub in schema["allOf"]:
            sub = _normalize_schema(sub, root, base_path, depth + 1)
            if isinstance(sub, dict):
                _merge_schemas(merged, sub)
        for k, v in schema.items():
            if k != "allOf":
                merged[k] = v
        return _normalize_schema(merged, root, base_path, depth + 1)

    # 3. Normalize oneOf/anyOf subschemas
    for comp in ("oneOf", "anyOf"):
        if comp in schema:
            schema[comp] = [
                _normalize_schema(s, root, base_path, depth + 1)
                for s in schema[comp]
            ]

    # 4. Recurse into children — preserve $ref in property values
    if "properties" in schema:
        schema["properties"] = {
            k: _normalize_schema(v, root, base_path, depth + 1, _resolve_refs=False)
            for k, v in schema["properties"].items()
        }
    if "items" in schema and isinstance(schema["items"], dict):
        schema["items"] = _normalize_schema(
            schema["items"], root, base_path, depth + 1, _resolve_refs=False
        )
    if "additionalProperties" in schema and isinstance(schema["additionalProperties"], dict):
        schema["additionalProperties"] = _normalize_schema(
            schema["additionalProperties"], root, base_path, depth + 1, _resolve_refs=False
        )

    return schema


def _merge_schemas(target: dict, source: dict) -> None:
    """Merge source schema into target (for allOf resolution)."""
    if not isinstance(source, dict):
        return
    src_props = source.get("properties")
    if isinstance(src_props, dict):
        target.setdefault("properties", {}).update(src_props)
    src_req = source.get("required")
    if isinstance(src_req, list):
        existing = set(target.get("required", []))
        target["required"] = list(existing | set(src_req))
    if "type" in source and "type" not in target:
        target["type"] = source["type"]
    if "enum" in source:
        existing = set(target.get("enum", []))
        target["enum"] = list(existing | set(source["enum"]))
    if "description" in source and "description" not in target:
        target["description"] = source["description"]
    if "nullable" in source and "nullable" not in target:
        target["nullable"] = source["nullable"]
    if "format" in source and "format" not in target:
        target["format"] = source["format"]
    for attr in ("readOnly", "writeOnly"):
        if attr in source and attr not in target:
            target[attr] = source[attr]


# ──────────────────────────────────────────────
#  TypeScript Type Mapping
# ──────────────────────────────────────────────

_FORMAT_TS_HINTS: dict[str, str] = {
    "date-time": "string",
    "date": "string",
    "time": "string",
    "uuid": "string",
    "uri": "string",
    "email": "string",
    "hostname": "string",
    "ipv4": "string",
    "ipv6": "string",
    "int32": "number",
    "int64": "number",
    "float": "number",
    "double": "number",
    "byte": "string",
    "binary": "string",
    "password": "string",
}


def _json_type_to_ts(schema: Any, root: dict, base_path: Path) -> str:
    """Map a normalized schema to a TypeScript type string."""
    if not isinstance(schema, dict):
        return "unknown"

    # oneOf / anyOf → union
    if "oneOf" in schema:
        members = [
            _json_type_to_ts(s, root, base_path) for s in schema["oneOf"]
        ]
        ts = " | ".join(members)
        return f"({ts})" if len(members) > 1 else ts
    if "anyOf" in schema:
        members = [
            _json_type_to_ts(s, root, base_path) for s in schema["anyOf"]
        ]
        ts = " | ".join(members)
        return f"({ts})" if len(members) > 1 else ts

    # $ref (should have been resolved by normalization, but handle defensively)
    ref = schema.get("$ref")
    if ref:
        return ref.split("/")[-1]

    enum_vals = schema.get("enum")
    if enum_vals:
        return " | ".join(f"'{v}'" for v in enum_vals)

    fmt = schema.get("format", "")
    t = schema.get("type", "any")

    if t == "string":
        base = _FORMAT_TS_HINTS.get(fmt, "string")
    elif t in ("integer", "number"):
        base = "number"
    elif t == "boolean":
        base = "boolean"
    elif t == "array":
        items = schema.get("items", {})
        return f"{_json_type_to_ts(items, root, base_path)}[]"
    elif t == "object":
        props = schema.get("properties")
        if props:
            return _inline_object_to_ts(schema, root, base_path)
        additional = schema.get("additionalProperties", {})
        if additional:
            val_type = _json_type_to_ts(additional, root, base_path)
            return f"Record<string, {val_type}>"
        return "Record<string, unknown>"
    else:
        base = "unknown"

    if schema.get("nullable"):
        return f"{base} | null"
    return base


def _inline_object_to_ts(schema: dict, root: dict, base_path: Path) -> str:
    """Generate inline anonymous object type for TypeScript."""
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    parts = []
    for pname, pschema in props.items():
        ptype = _json_type_to_ts(pschema, root, base_path)
        opt_flag = "" if pname in required else "?"
        parts.append(f"  {pname}{opt_flag}: {ptype}")
    return "{\n" + ";\n".join(parts) + "\n}"


# ──────────────────────────────────────────────
#  TypeScript Schema Generation
# ──────────────────────────────────────────────

TYPESCRIPT_HEADER = "// Auto-generated by generate_shared.py"


def _schema_to_typescript(
    schema: Any,
    name: str,
    root: dict,
    base_path: Path,
    *,
    _nested_objects: Optional[list[tuple[str, dict]]] = None,
) -> list[str]:
    """Generate TypeScript type definitions from a schema.

    Returns a list of source lines. Nested object schemas are extracted
    into _nested_objects (a list of (type_name, schema) pairs).
    """
    if _nested_objects is None:
        _nested_objects = []

    lines: list[str] = []
    safe_name = _safe_name(name)

    schema = _normalize_schema(schema, root, base_path)

    if not isinstance(schema, dict):
        lines.append(f"export type {safe_name} = unknown;")
        return lines

    t = schema.get("type", "")

    # enum
    if "enum" in schema:
        vals = " | ".join(f"'{v}'" for v in schema["enum"])
        desc = schema.get("description", "")
        lines.extend(_ts_jsdoc(desc, schema))
        lines.append(f"export type {safe_name} = {vals};")
        return lines

    # oneOf / anyOf → union type alias
    if "oneOf" in schema or "anyOf" in schema:
        key = "oneOf" if "oneOf" in schema else "anyOf"
        members = [
            _json_type_to_ts(s, root, base_path) for s in schema[key]
        ]
        union = " | ".join(members)
        desc = schema.get("description", "")
        lines.extend(_ts_jsdoc(desc, schema))
        lines.append(f"export type {safe_name} = {union};")
        return lines

    if t == "object":
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        if not props:
            desc = schema.get("description", "")
            lines.extend(_ts_jsdoc(desc, schema))
            lines.append(
                f"// eslint-disable-next-line @typescript-eslint/no-empty-interface"
            )
            lines.append(f"export interface {safe_name} {{}}")
            return lines

        desc = schema.get("description", "")
        lines.extend(_ts_jsdoc(desc, schema))
        lines.append(f"export interface {safe_name} {{")
        for pname, pschema in props.items():
            prop_lines, prop_type = _property_to_typescript(
                pname, pschema, root, base_path, safe_name, _nested_objects
            )
            lines.extend(prop_lines)
        lines.append("}")
        # Append any nested objects generated from this schema's properties
        for nname, nschema in _nested_objects:
            lines.extend(_schema_to_typescript(nschema, nname, root, base_path))
        _nested_objects.clear()
        return lines

    if t == "array":
        items = schema.get("items", {})
        item_type = _json_type_to_ts(items, root, base_path)
        desc = schema.get("description", "")
        lines.extend(_ts_jsdoc(desc, schema))
        lines.append(f"export type {safe_name} = {item_type}[];")
        return lines

    # scalar type alias
    ts_type = _json_type_to_ts(schema, root, base_path)
    desc = schema.get("description", "")
    lines.extend(_ts_jsdoc(desc, schema))
    lines.append(f"export type {safe_name} = {ts_type};")
    return lines


def _property_to_typescript(
    pname: str,
    pschema: Any,
    root: dict,
    base_path: Path,
    parent_name: str,
    nested_objects: list[tuple[str, dict]],
    *,
    parent_required: set[str] | None = None,
) -> tuple[list[str], str]:
    """Generate TypeScript property line(s). Returns (lines, resolved_type_name).

    For nested inline objects, extracts a named type and returns its name.
    """
    pschema_norm = _normalize_schema(pschema, root, base_path)
    prop_required = parent_required is not None and pname in parent_required
    optional = ""
    readonly = ""
    lines: list[str] = []

    if pschema_norm.get("readOnly"):
        readonly = "readonly "

    if not prop_required or pschema_norm.get("nullable"):
        optional = "?"

    fmt = pschema_norm.get("format", "")
    desc = pschema_norm.get("description", "")

    # Check for inline object (nested schema with properties)
    if (
        isinstance(pschema_norm, dict)
        and pschema_norm.get("type") == "object"
        and pschema_norm.get("properties")
        and not pschema_norm.get("$ref")
    ):
        nested_name = f"{_safe_name(parent_name)}_{_safe_name(pname)}"
        nested_objects.append((nested_name, pschema_norm))
        ts_type = nested_name
    else:
        ts_type = _json_type_to_ts(pschema_norm, root, base_path)

    jsdoc_parts = []
    if desc:
        jsdoc_parts.append(desc)
    if fmt:
        jsdoc_parts.append(f"@format {fmt}")
    if pschema_norm.get("writeOnly"):
        jsdoc_parts.append("@writeOnly")
    if pschema_norm.get("deprecated"):
        jsdoc_parts.append("@deprecated")
    if jsdoc_parts:
        lines.append(f"  /** {' '.join(jsdoc_parts)} */")

    lines.append(
        f"  {readonly}{pname}{optional}: {ts_type};"
    )
    return lines, ts_type


def _ts_jsdoc(description: str, schema: dict) -> list[str]:
    """Generate JSDoc comment lines from description and schema metadata."""
    parts: list[str] = []
    if description:
        parts.append(description)
    fmt = schema.get("format", "")
    if fmt:
        parts.append(f"@format {fmt}")
    if schema.get("deprecated"):
        parts.append("@deprecated")
    if not parts:
        return []
    if len(parts) == 1:
        return [f"/** {parts[0]} */"]
    return ["/**"] + [f" * {p}" for p in parts] + [" */"]


def _safe_name(name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip("/{} "))
    if safe[0].isdigit():
        safe = f"T_{safe}"
    if not safe:
        safe = "T"
    return safe


# ──────────────────────────────────────────────
#  Python Type Mapping
# ──────────────────────────────────────────────

_FORMAT_PYTHON_TYPES: dict[str, str] = {
    "date-time": "datetime",
    "date": "date",
    "time": "time",
    "uuid": "str",
    "uri": "str",
    "email": "str",
    "hostname": "str",
    "ipv4": "str",
    "ipv6": "str",
    "int32": "int",
    "int64": "int",
    "float": "float",
    "double": "float",
    "byte": "str",
    "binary": "bytes",
    "password": "str",
}

_FORMAT_PYTHON_IMPORTS: dict[str, str] = {
    "date-time": "datetime",
    "date": "datetime",
    "time": "datetime",
}


def _json_type_to_python(schema: Any, root: dict, base_path: Path) -> str:
    """Map a normalized schema to a Python type annotation string."""
    if not isinstance(schema, dict):
        return "Any"

    # oneOf / anyOf → Union
    if "oneOf" in schema:
        members = [
            _json_type_to_python(s, root, base_path) for s in schema["oneOf"]
        ]
        return f"Union[{', '.join(members)}]"
    if "anyOf" in schema:
        members = [
            _json_type_to_python(s, root, base_path) for s in schema["anyOf"]
        ]
        return f"Union[{', '.join(members)}]"

    ref = schema.get("$ref")
    if ref:
        return ref.split("/")[-1]

    enum_vals = schema.get("enum")
    if enum_vals:
        return f"Literal[{', '.join(repr(v) for v in enum_vals)}]"

    fmt = schema.get("format", "")
    t = schema.get("type", "any")

    if t == "string":
        py_type = _FORMAT_PYTHON_TYPES.get(fmt, "str")
    elif t == "integer":
        py_type = "int"
    elif t == "number":
        py_type = "float"
    elif t == "boolean":
        py_type = "bool"
    elif t == "array":
        items = schema.get("items", {})
        return f"list[{_json_type_to_python(items, root, base_path)}]"
    elif t == "object":
        props = schema.get("properties")
        if props:
            # Use TypedDict for struct-like objects
            return "dict"
        additional = schema.get("additionalProperties", {})
        if additional:
            val_type = _json_type_to_python(additional, root, base_path)
            return f"dict[str, {val_type}]"
        return "dict"
    else:
        py_type = "Any"

    if schema.get("nullable"):
        return f"Optional[{py_type}]"
    return py_type


# ──────────────────────────────────────────────
#  Python Schema Generation
# ──────────────────────────────────────────────

PYTHON_HEADER = '"""Auto-generated by generate_shared.py"""'


def _schema_to_python(
    schema: Any,
    name: str,
    root: dict,
    base_path: Path,
    *,
    _nested_objects: Optional[list[tuple[str, dict]]] = None,
) -> list[str]:
    """Generate Python type definitions from a schema.

    Returns source lines. Nested objects are extracted into
    _nested_objects as (type_name, schema) pairs.
    """
    if _nested_objects is None:
        _nested_objects = []

    lines: list[str] = []
    safe_name = _safe_name(name)

    schema = _normalize_schema(schema, root, base_path)

    if not isinstance(schema, dict):
        lines.append(f"{safe_name} = Any")
        return lines

    # enum → Literal type alias
    if "enum" in schema:
        vals = ", ".join(repr(v) for v in schema["enum"])
        desc = schema.get("description", "")
        if desc:
            lines.append(f"# {desc}")
        lines.append(f"{safe_name} = Literal[{vals}]")
        return lines

    # oneOf / anyOf → Union type alias
    if "oneOf" in schema or "anyOf" in schema:
        key = "oneOf" if "oneOf" in schema else "anyOf"
        members = [
            _json_type_to_python(s, root, base_path) for s in schema[key]
        ]
        desc = schema.get("description", "")
        if desc:
            lines.append(f"# {desc}")
        lines.append(f"{safe_name} = Union[{', '.join(members)}]")
        return lines

    t = schema.get("type", "")

    if t == "object":
        props = schema.get("properties", {})
        required = schema.get("required", [])
        if not props:
            desc = schema.get("description", "")
            if desc:
                lines.append(f"# {desc}")
            lines.append(f"{safe_name} = dict")
            return lines

        desc = schema.get("description", "")
        if desc:
            lines.append(f"# {desc}")
        lines.append("@dataclass")
        lines.append(f"class {safe_name}:")
        if not props:
            lines.append("    pass")
        else:
            for pname, pschema in props.items():
                prop_lines = _property_to_python(
                    pname, pschema, root, base_path, safe_name, _nested_objects
                )
                lines.extend(prop_lines)
        lines.append("")
        # Append nested objects
        for nname, nschema in _nested_objects:
            lines.extend(_schema_to_python(nschema, nname, root, base_path))
        _nested_objects.clear()
        return lines

    if t == "array":
        items = schema.get("items", {})
        item_type = _json_type_to_python(items, root, base_path)
        desc = schema.get("description", "")
        if desc:
            lines.append(f"# {desc}")
        lines.append(f"{safe_name} = list[{item_type}]")
        return lines

    # scalar type alias
    py_type = _json_type_to_python(schema, root, base_path)
    desc = schema.get("description", "")
    if desc:
        lines.append(f"# {desc}")
    lines.append(f"{safe_name} = {py_type}")
    return lines


def _property_to_python(
    pname: str,
    pschema: Any,
    root: dict,
    base_path: Path,
    parent_name: str,
    nested_objects: list[tuple[str, dict]],
) -> list[str]:
    """Generate Python property line(s). Returns source lines."""
    pschema_norm = _normalize_schema(pschema, root, base_path)
    required = pschema_norm.get("required", [])
    prop_required = pname in required
    lines: list[str] = []

    fmt = pschema_norm.get("format", "")
    desc = pschema_norm.get("description", "")

    # Check for inline object
    if (
        isinstance(pschema_norm, dict)
        and pschema_norm.get("type") == "object"
        and pschema_norm.get("properties")
        and not pschema_norm.get("$ref")
    ):
        nested_name = f"{_safe_name(parent_name)}_{_safe_name(pname)}"
        nested_objects.append((nested_name, pschema_norm))
        py_type = nested_name
    else:
        py_type = _json_type_to_python(pschema_norm, root, base_path)

    # Add comment for readOnly/writeOnly/format/description
    comments = []
    if pschema_norm.get("readOnly"):
        comments.append("readOnly")
    if pschema_norm.get("writeOnly"):
        comments.append("writeOnly")
    if fmt:
        comments.append(f"format:{fmt}")
    if comments:
        lines.append(f"    # {' / '.join(comments)}")

    if not prop_required or pschema_norm.get("nullable"):
        lines.append(f"    {pname}: Optional[{py_type}] = None")
    else:
        lines.append(f"    {pname}: {py_type}")

    return lines


# ──────────────────────────────────────────────
#  Detect import needs from generated lines
# ──────────────────────────────────────────────

_KNOWN_PYTHON_BUILTIN_TYPES = {
    "str",
    "int",
    "float",
    "bool",
    "dict",
    "list",
    "bytes",
    "Any",
}


def _detect_python_imports(lines: list[str]) -> dict[str, set[str]]:
    """Detect what imports are needed from generated Python source lines.

    Returns mapping of module → set of names.
    """
    imports: dict[str, set[str]] = {}
    text = "\n".join(lines)

    if "datetime" in text:
        if "datetime" in text or "date" in text or "time" in text:
            imports.setdefault("datetime", set()).add("datetime")
        if "date" in text and "from datetime import" not in text:
            imports.setdefault("datetime", set()).add("date")
        if "time" in text and "from datetime import" not in text:
            imports.setdefault("datetime", set()).add("time")

    if "Optional[" in text or "Optional[" in text:
        imports.setdefault("typing", set()).add("Optional")
    if "Union[" in text:
        imports.setdefault("typing", set()).add("Union")
    if "Literal[" in text:
        imports.setdefault("typing", set()).add("Literal")
    if "Any" in text:
        imports.setdefault("typing", set()).add("Any")
    if "list[" in text:
        imports.setdefault("typing", set()).add("List")

    return imports


def _detect_ts_imports(lines: list[str]) -> list[str]:
    """Detect cross-file type references for TypeScript imports.

    This is a best-effort scan for type names that look like they
    might come from other generated files.
    """
    # For now, we generate independent files and rely on the index.ts
    # to re-export everything. Cross-file refs work as long as the
    # consumer imports from the index.
    return []


# ──────────────────────────────────────────────
#  Project / Language Detection
# ──────────────────────────────────────────────


def _detect_stack(project_root: Path) -> dict:
    project_yaml = project_root / "aidlc" / "project.yaml"
    if not project_yaml.exists():
        return {}
    try:
        data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
        return data or {}
    except Exception:
        return {}


def _find_lang(project: dict) -> str:
    comps = project.get("stack", {}).get("components", [])
    langs = {c.get("default_language", "") for c in comps if c.get("default_language")}
    if "typescript" in langs or "javascript" in langs:
        return "typescript"
    if "python" in langs:
        return "python"
    if "go" in langs:
        return "go"
    if "dart" in langs:
        return "dart"
    return "typescript"


# ──────────────────────────────────────────────
#  File Generation
# ──────────────────────────────────────────────

_PYTHON_IMPORT_BLOCK = """from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Literal, Optional, Union
"""

_PYTHON_DATACLASS_IMPORT = "from dataclasses import dataclass"


def _generate_typescript_file(yaml_path: Path, output: Path) -> list[str]:
    """Generate a TypeScript file from a YAML contract file. Returns list of generated names."""
    root = _load_yaml(yaml_path)
    lines = [TYPESCRIPT_HEADER, f"// Source: {yaml_path.name}", ""]
    generated_names: list[str] = []

    # Paths (HTTP API operations)
    paths = root.get("paths", {})
    for path_name, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, spec in methods.items():
            if not isinstance(spec, dict):
                continue
            # Request body
            req_body = spec.get("requestBody", {})
            if isinstance(req_body, dict):
                content = req_body.get("content", {})
                if isinstance(content, dict):
                    for media_type, media_schema in content.items():
                        schema = media_schema.get("schema", {}) if isinstance(media_schema, dict) else {}
                        if schema:
                            type_name = f"{method}_{path_name}_request"
                            type_lines = _schema_to_typescript(
                                schema, type_name, root, yaml_path
                            )
                            lines.extend(type_lines)
                            lines.append("")
                            generated_names.append(type_name)

            # Responses
            responses = spec.get("responses", {})
            if isinstance(responses, dict):
                for status_code in ("200", "201", "202", "204"):
                    resp = responses.get(status_code, {})
                    if isinstance(resp, dict):
                        content = resp.get("content", {})
                        if isinstance(content, dict):
                            for media_type, media_schema in content.items():
                                schema = media_schema.get("schema", {}) if isinstance(media_schema, dict) else {}
                                if schema:
                                    type_name = f"{method}_{path_name}_response"
                                    type_lines = _schema_to_typescript(
                                        schema, type_name, root, yaml_path
                                    )
                                    lines.extend(type_lines)
                                    lines.append("")
                                    generated_names.append(type_name)

    # Components / schemas
    components = root.get("components", {}).get("schemas", {})
    if isinstance(components, dict):
        for name, schema in components.items():
            if isinstance(schema, dict):
                type_lines = _schema_to_typescript(schema, name, root, yaml_path)
                lines.extend(type_lines)
                lines.append("")
                generated_names.append(name)

    # AsyncAPI message payloads
    channels = root.get("channels", {})
    if isinstance(channels, dict):
        for channel_name, channel in channels.items():
            if not isinstance(channel, dict):
                continue
            for direction in ("publish", "subscribe"):
                op = channel.get(direction, {})
                if isinstance(op, dict):
                    message = op.get("message", {})
                    if isinstance(message, dict):
                        # message may have a #ref or inline payload
                        if "$ref" in message:
                            ref = message["$ref"]
                            try:
                                rr = _resolve_ref(ref, root, yaml_path)
                                message = rr.schema
                            except GenerateError:
                                message = {}
                        payload = message.get("payload", {})
                        if isinstance(payload, dict):
                            type_name = f"{channel_name}_{direction}_payload"
                            safe_type_name = _safe_name(type_name)
                            type_lines = _schema_to_typescript(
                                payload, safe_type_name, root, yaml_path
                            )
                            lines.extend(type_lines)
                            lines.append("")
                            generated_names.append(safe_type_name)

    if not generated_names:
        lines.append(f"// No types extracted from {yaml_path.name}")

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return generated_names


def _generate_python_file(yaml_path: Path, output: Path) -> list[str]:
    """Generate a Python file from a YAML contract file. Returns list of generated names."""
    root = _load_yaml(yaml_path)
    lines: list[str] = []
    generated_names: list[str] = []

    all_type_lines: list[str] = []

    # Components / schemas
    components = root.get("components", {}).get("schemas", {})
    if isinstance(components, dict):
        for name, schema in components.items():
            if isinstance(schema, dict):
                type_lines = _schema_to_python(schema, name, root, yaml_path)
                all_type_lines.extend(type_lines)
                all_type_lines.append("")
                generated_names.append(name)

    # Channels (AsyncAPI)
    channels = root.get("channels", {})
    if isinstance(channels, dict):
        for channel_name, channel in channels.items():
            if not isinstance(channel, dict):
                continue
            for direction in ("publish", "subscribe"):
                op = channel.get(direction, {})
                if isinstance(op, dict):
                    message = op.get("message", {})
                    if isinstance(message, dict):
                        if "$ref" in message:
                            try:
                                rr = _resolve_ref(message["$ref"], root, yaml_path)
                                message = rr.schema
                            except GenerateError:
                                message = {}
                        payload = message.get("payload", {})
                        if isinstance(payload, dict):
                            type_name = f"{_safe_name(channel_name)}_{direction}_payload"
                            type_lines = _schema_to_python(
                                payload, type_name, root, yaml_path
                            )
                            all_type_lines.extend(type_lines)
                            all_type_lines.append("")
                            generated_names.append(type_name)

    # Detect required imports
    if all_type_lines:
        imports = _detect_python_imports(all_type_lines)

        lines.append(PYTHON_HEADER)
        lines.append(f"# Source: {yaml_path.name}")
        lines.append("")

        # Build import block
        import_parts = []
        # Always include dataclasses and typing basics when we have types
        import_parts.append("from __future__ import annotations")
        import_parts.append("")
        import_parts.append("from dataclasses import dataclass")
        typing_imports = set()
        for mod, names in imports.items():
            if mod == "typing":
                typing_imports |= names
        if typing_imports:
            sorted_imports = sorted(typing_imports, key=lambda x: (x != "Any", x))
            import_parts.append(
                f"from typing import {', '.join(sorted_imports)}"
            )
        if "datetime" in imports:
            datetime_names = sorted(imports["datetime"])
            import_parts.append(
                f"from datetime import {', '.join(datetime_names)}"
            )
        lines.extend(import_parts)
        lines.append("")
        lines.extend(all_type_lines)

    if not generated_names:
        lines.append(PYTHON_HEADER)
        lines.append(f"# Source: {yaml_path.name}")
        lines.append("# No schemas found to generate")

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return generated_names


def _generate_index_ts(output_dir: Path, stubs: list[Path]) -> None:
    """Generate a TypeScript index file that re-exports all generated modules."""
    lines = [TYPESCRIPT_HEADER, ""]
    for p in stubs:
        rel = p.relative_to(output_dir).with_suffix("")
        # Convert to POSIX path for import
        rel_posix = str(rel).replace("\\", "/")
        lines.append(f"export * from './{rel_posix}';")
    (output_dir / "index.ts").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _generate_init_py(output_dir: Path, stubs: list[Path]) -> None:
    """Generate Python __init__.py that imports all generated modules."""
    lines = [PYTHON_HEADER, ""]
    for p in stubs:
        mod_name = p.stem
        lines.append(f"from .{mod_name} import *  # noqa: F401, F403")
    (output_dir / "__init__.py").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ──────────────────────────────────────────────
#  Main Generate Logic
# ──────────────────────────────────────────────


def _find_yaml_files(project_root: Path) -> list[Path]:
    """Find all contract YAML files under aidlc/contracts/."""
    contracts_dirs = [
        project_root / "aidlc" / "contracts" / "api",
        project_root / "aidlc" / "contracts" / "events",
    ]
    files: list[Path] = []
    for d in contracts_dirs:
        if d.exists():
            files.extend(sorted(d.glob("*.yaml")))
    return files


def generate(
    project_root: Path,
    ts_outdir: Optional[Path] = None,
    py_outdir: Optional[Path] = None,
) -> list[Path]:
    """Generate shared type files from all contract YAML files.

    Args:
        project_root: Root of the project.
        ts_outdir: Output directory for TypeScript files (default: aidlc/packages/shared).
        py_outdir: Output directory for Python files (default: aidlc/packages/shared).

    Returns:
        List of generated file paths.
    """
    project = _detect_stack(project_root)
    lang = _find_lang(project)
    yaml_files = _find_yaml_files(project_root)

    if not yaml_files:
        return []

    # Determine output dirs
    if ts_outdir is None:
        ts_outdir = project_root / "aidlc" / "packages" / "shared"
    if py_outdir is None:
        py_outdir = project_root / "aidlc" / "packages" / "shared"

    generated: list[Path] = []
    ts_stubs: list[Path] = []
    py_stubs: list[Path] = []

    # Generate TypeScript if requested
    if lang == "typescript" or ts_outdir != py_outdir or True:
        ts_outdir.mkdir(parents=True, exist_ok=True)
        for yaml_file in yaml_files:
            try:
                target = ts_outdir / f"{yaml_file.stem}.ts"
                names = _generate_typescript_file(yaml_file, target)
                generated.append(target)
                ts_stubs.append(target)
                if names:
                    print(f"  TS  {target.relative_to(project_root)}  ({len(names)} types)")
                else:
                    print(f"  TS  {target.relative_to(project_root)}  (no types)")
            except GenerateError as e:
                print(f"  TS  ERROR: {e}", file=sys.stderr)
            except Exception as e:
                print(f"  TS  UNEXPECTED ERROR in {yaml_file.name}: {e}", file=sys.stderr)
                traceback.print_exc()

        if ts_stubs:
            _generate_index_ts(ts_outdir, ts_stubs)
            idx = ts_outdir / "index.ts"
            if idx not in generated:
                generated.append(idx)

    # Generate Python if requested
    if lang == "python" or py_outdir.exists() or True:
        py_outdir.mkdir(parents=True, exist_ok=True)
        for yaml_file in yaml_files:
            try:
                target = py_outdir / f"{yaml_file.stem}.py"
                names = _generate_python_file(yaml_file, target)
                generated.append(target)
                py_stubs.append(target)
                if names:
                    print(f"  PY  {target.relative_to(project_root)}  ({len(names)} types)")
                else:
                    print(f"  PY  {target.relative_to(project_root)}  (no types)")
            except GenerateError as e:
                print(f"  PY  ERROR: {e}", file=sys.stderr)
            except Exception as e:
                print(f"  PY  UNEXPECTED ERROR in {yaml_file.name}: {e}", file=sys.stderr)
                traceback.print_exc()

        if py_stubs:
            _generate_init_py(py_outdir, py_stubs)
            init = py_outdir / "__init__.py"
            if init not in generated:
                generated.append(init)

    return generated


# ──────────────────────────────────────────────
#  Watch Mode
# ──────────────────────────────────────────────


def _watch_loop(
    project_root: Path,
    ts_outdir: Optional[Path],
    py_outdir: Optional[Path],
    poll_interval: float = 2.0,
) -> None:
    """Watch YAML contract files for changes and regenerate on modification.

    Uses watchdog if available, otherwise falls back to polling.
    """
    try:
        import watchdog.events  # noqa: F401
        import watchdog.observers  # noqa: F401

        _watch_with_watchdog(project_root, ts_outdir, py_outdir)
    except ImportError:
        _watch_poll(project_root, ts_outdir, py_outdir, poll_interval)


def _watch_with_watchdog(
    project_root: Path,
    ts_outdir: Optional[Path],
    py_outdir: Optional[Path],
) -> None:
    """Watch using watchdog library."""
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    contracts_dir = project_root / "aidlc" / "contracts"

    class RegenerateHandler(FileSystemEventHandler):
        def __init__(self):
            self._last_trigger: float = 0
            self._debounce: float = 1.0

        def on_any_event(self, event):
            if event.is_directory:
                return
            if not event.src_path.endswith(".yaml"):
                return
            now = time.time()
            if now - self._last_trigger < self._debounce:
                return
            self._last_trigger = now
            print(f"\n  ⚡ Change detected: {Path(event.src_path).name}")
            try:
                generate(project_root, ts_outdir=ts_outdir, py_outdir=py_outdir)
                print(f"  ✓ Regenerated at {time.strftime('%H:%M:%S')}")
            except Exception as e:
                print(f"  ✗ Regeneration failed: {e}", file=sys.stderr)

    event_handler = RegenerateHandler()
    observer = Observer()
    observer.schedule(event_handler, str(contracts_dir), recursive=True)
    observer.start()
    print(f"  👀 Watching {contracts_dir} for changes... (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


def _watch_poll(
    project_root: Path,
    ts_outdir: Optional[Path],
    py_outdir: Optional[Path],
    poll_interval: float = 2.0,
) -> None:
    """Watch by polling mtime of YAML files."""
    yaml_files = _find_yaml_files(project_root)
    if not yaml_files:
        print("  No YAML files to watch.")
        return

    mtimes: dict[Path, float] = {
        f: f.stat().st_mtime for f in yaml_files
    }
    print(f"  👀 Watching {len(yaml_files)} file(s) for changes (polling)... (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(poll_interval)
            for f in yaml_files:
                if not f.exists():
                    continue
                new_mtime = f.stat().st_mtime
                if new_mtime != mtimes.get(f):
                    mtimes[f] = new_mtime
                    print(f"\n  ⚡ Change detected: {f.name}")
                    try:
                        generate(project_root, ts_outdir=ts_outdir, py_outdir=py_outdir)
                        print(f"  ✓ Regenerated at {time.strftime('%H:%M:%S')}")
                    except Exception as e:
                        print(f"  ✗ Regeneration failed: {e}", file=sys.stderr)
    except KeyboardInterrupt:
        pass


# ──────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate shared types from OpenAPI/AsyncAPI contracts",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root directory (default: current dir)",
    )
    parser.add_argument(
        "--ts-outdir",
        default=None,
        help="Output directory for TypeScript files (default: aidlc/packages/shared)",
    )
    parser.add_argument(
        "--py-outdir",
        default=None,
        help="Output directory for Python files (default: aidlc/packages/shared)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch contract files for changes and auto-regenerate",
    )
    args = parser.parse_args()

    root = Path(args.project_root).resolve()

    ts_outdir = Path(args.ts_outdir).resolve() if args.ts_outdir else None
    py_outdir = Path(args.py_outdir).resolve() if args.py_outdir else None

    if args.watch:
        print(f"Starting generate_shared.py in watch mode")
        print(f"  project-root: {root}")
        if ts_outdir:
            print(f"  ts-outdir:    {ts_outdir}")
        if py_outdir:
            print(f"  py-outdir:    {py_outdir}")
        # Do an initial generation
        try:
            generated = generate(root, ts_outdir=ts_outdir, py_outdir=py_outdir)
            if generated:
                print(f"  Initial generation: {len(generated)} file(s)")
            else:
                print(f"  No contract files found under {root / 'aidlc' / 'contracts'}")
        except Exception as e:
            print(f"  Initial generation failed: {e}", file=sys.stderr)
        _watch_loop(root, ts_outdir, py_outdir)
    else:
        try:
            generated = generate(root, ts_outdir=ts_outdir, py_outdir=py_outdir)
            if generated:
                print(f"\nGenerated {len(generated)} file(s):")
                for f in generated:
                    print(f"  {f.relative_to(root)}")
            else:
                print("Nothing to generate (no contract files found)")
        except GenerateError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()
