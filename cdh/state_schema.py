from __future__ import annotations

import re
from datetime import datetime
from typing import Any

try:
    import jsonschema

    HAS_JSONSCHEMA = True
except ImportError:
    jsonschema = None
    HAS_JSONSCHEMA = False


ISO_DATE_TIME = r"^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?(?:Z|[+-]\\d{2}:\\d{2})$"
PHASES = ["init", "understand", "plan", "verify", "deliver"]

SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "state_version", "schema_version", "current_phase", "completed_phases",
        "gate_results", "fingerprint", "task_registry",
    ],
    "properties": {
        "state_version": {"type": "integer"},
        "schema_version": {"type": "string"},
        "current_phase": {"type": "string", "enum": PHASES},
        "completed_phases": {
            "type": "array", "items": {"type": "string", "enum": PHASES},
        },
        "gate_results": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "required": ["status", "summary", "recorded_at"],
                "properties": {
                    "status": {"type": "string", "enum": ["passed", "failed", "skipped"]},
                    "summary": {"type": "string"},
                    "recorded_at": {"type": "string", "format": "date-time"},
                },
            },
        },
        "fingerprint": {"type": "string"},
        "task_registry": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["fingerprint", "intent", "status", "created_at", "updated_at"],
                "properties": {
                    "fingerprint": {"type": "string", "minLength": 24, "maxLength": 24},
                    "intent": {"type": "string"},
                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "failed"]},
                    "created_at": {"type": "string", "format": "date-time"},
                    "updated_at": {"type": "string", "format": "date-time"},
                    "result": {"type": "string"},
                },
            },
        },
    },
}


def _date_time(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(ISO_DATE_TIME, value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _type_matches(value: Any, expected: str) -> bool:
    checks = {
        "string": lambda: isinstance(value, str),
        "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
        "array": lambda: isinstance(value, list),
        "object": lambda: isinstance(value, dict),
        "boolean": lambda: isinstance(value, bool),
    }
    return checks.get(expected, lambda: True)()


def _minimal_validate(value: Any, schema: dict[str, Any], path: str = "$", errors: list[str] | None = None) -> list[str]:
    errors = [] if errors is None else errors
    expected = schema.get("type")
    if expected and not _type_matches(value, expected):
        errors.append(f"{path}: expected {expected}")
        return errors
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: must be one of {schema['enum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than maxLength")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: does not match pattern")
        if schema.get("format") == "date-time" and not _date_time(value):
            errors.append(f"{path}: invalid date-time")
    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}: missing required property '{name}'")
        for name, child in schema.get("properties", {}).items():
            if name in value:
                _minimal_validate(value[name], child, f"{path}.{name}", errors)
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            for name, item in value.items():
                if name not in schema.get("properties", {}):
                    _minimal_validate(item, additional, f"{path}.{name}", errors)
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            _minimal_validate(item, schema["items"], f"{path}[{index}]", errors)
    return errors


def validate_state(state: Any) -> tuple[bool, list[str]]:
    if HAS_JSONSCHEMA:
        validator = jsonschema.Draft202012Validator(SCHEMA)
        errors = sorted(validator.iter_errors(state), key=lambda error: list(error.path))
        return not errors, [f"{'/'.join(map(str, error.path)) or '$'}: {error.message}" for error in errors]
    errors = _minimal_validate(state, SCHEMA)
    return not errors, errors
