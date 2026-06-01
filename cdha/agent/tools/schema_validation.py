from __future__ import annotations

from typing import Any, Mapping

from cdha.agent.tools.errors import ToolInputError


def validate_json_schema(
    input_data: dict[str, Any],
    schema: Mapping[str, Any],
    tool_name: str = "",
) -> None:
    """Validate input against JSON Schema.

    Supports: required fields, type checks, string patterns, enums,
    nested objects, and arrays.
    """
    if not schema:
        return

    errors: list[str] = []
    props = schema.get("properties", {})
    required = set(schema.get("required", []))

    # Check required fields
    for field in required:
        if field not in input_data or input_data[field] is None:
            errors.append(f"missing required field: '{field}'")

    # Validate each present field
    for field, value in input_data.items():
        prop_schema = props.get(field)
        if prop_schema is None:
            continue
        _validate_field(field, value, prop_schema, errors, input_data)

    if errors:
        prefix = f" in tool '{tool_name}'" if tool_name else ""
        msg = f"input validation failed{prefix}:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ToolInputError(msg)


def _validate_field(
    field: str,
    value: Any,
    schema: dict[str, Any],
    errors: list[str],
    root_input: dict[str, Any],
) -> None:
    json_type = schema.get("type", "")

    if json_type == "string":
        if not isinstance(value, str):
            errors.append(f"'{field}': expected string, got {type(value).__name__}")
        else:
            pattern = schema.get("pattern")
            if pattern:
                import re
                if not re.match(pattern, value):
                    errors.append(f"'{field}': does not match pattern {pattern!r}")

    elif json_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"'{field}': expected integer, got {type(value).__name__}")

    elif json_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f"'{field}': expected number, got {type(value).__name__}")

    elif json_type == "boolean":
        if not isinstance(value, bool):
            errors.append(f"'{field}': expected boolean, got {type(value).__name__}")

    elif json_type == "array":
        if not isinstance(value, list):
            errors.append(f"'{field}': expected array, got {type(value).__name__}")
        else:
            items_schema = schema.get("items")
            if items_schema:
                for i, item in enumerate(value):
                    _validate_field(f"{field}[{i}]", item, items_schema, errors, root_input)

    elif json_type == "object":
        if not isinstance(value, dict):
            errors.append(f"'{field}': expected object, got {type(value).__name__}")
        else:
            sub_required = set(schema.get("required", []))
            sub_props = schema.get("properties", {})
            for sub_field in sub_required:
                if sub_field not in value:
                    errors.append(f"'{field}.{sub_field}': missing required field")
            for sub_field, sub_value in value.items():
                sub_schema = sub_props.get(sub_field)
                if sub_schema:
                    _validate_field(f"{field}.{sub_field}", sub_value, sub_schema, errors, root_input)

    # Check enum values
    enum_values = schema.get("enum")
    if enum_values is not None and value not in enum_values:
        errors.append(f"'{field}': must be one of {enum_values}, got {value!r}")
