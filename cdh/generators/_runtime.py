from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Mapping


_KIND_KEYS = ("oneOf", "anyOf")


def _identifier(name: str, style: str) -> str:
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", name) if part]
    if not parts:
        parts = ["field"]
    if style in {"pascal", "go", "csharp", "kotlin", "swift"}:
        value = "".join(part[:1].upper() + part[1:] for part in parts)
    elif style in {"snake", "rust"}:
        value = "_".join(part.lower() for part in parts)
    else:
        value = parts[0][:1].lower() + parts[0][1:] + "".join(part[:1].upper() + part[1:] for part in parts[1:])
    if value[0].isdigit():
        value = f"T{value}"
    return value


def _ref_name(schema: Mapping[str, Any]) -> str | None:
    ref = schema.get("$ref")
    return str(ref).split("/")[-1] if ref else None


def _union(schema: Mapping[str, Any], mapper: Callable[[Mapping[str, Any]], str], fallback: str) -> str:
    for key in _KIND_KEYS:
        if key in schema:
            members = [mapper(item) for item in schema[key] if isinstance(item, Mapping)]
            return " | ".join(members) if members else fallback
    return fallback


def _type_mapper(language: str) -> Callable[[Mapping[str, Any]], str]:
    def map_type(schema: Mapping[str, Any]) -> str:
        ref = _ref_name(schema)
        if ref:
            return _identifier(ref, "pascal")
        kind = schema.get("type", "object")
        fmt = schema.get("format", "")
        if language == "typescript":
            union = _union(schema, map_type, "unknown")
            if any(key in schema for key in _KIND_KEYS):
                return union
            base = {"string": "string", "integer": "number", "number": "number", "boolean": "boolean", "object": "Record<string, unknown>"}.get(kind, "unknown")
            if kind == "array":
                base = f"{map_type(schema.get('items', {}))}[]"
            return base
        if language == "python":
            if any(key in schema for key in _KIND_KEYS):
                values = _union(schema, map_type, "Any").split(" | ")
                return f"Union[{', '.join(values)}]"
            base = {"string": {"date-time": "datetime", "date": "date", "time": "time"}.get(fmt, "str"), "integer": "int", "number": "float", "boolean": "bool", "object": "dict[str, Any]"}.get(kind, "Any")
            if kind == "array":
                base = f"list[{map_type(schema.get('items', {}))}]"
            return base
        if language in {"java", "csharp", "kotlin"}:
            maps = {
                "java": {"string": {"date-time": "OffsetDateTime", "uuid": "UUID"}.get(fmt, "String"), "integer": "Long", "number": "BigDecimal" if fmt == "double" else "Double", "boolean": "Boolean", "object": "Object"},
                "csharp": {"string": {"date-time": "DateTimeOffset", "uuid": "Guid"}.get(fmt, "string"), "integer": "long", "number": "decimal" if fmt == "double" else "double", "boolean": "bool", "object": "object"},
                "kotlin": {"string": {"date-time": "Instant", "uuid": "UUID"}.get(fmt, "String"), "integer": "Long", "number": "Double", "boolean": "Boolean", "object": "Any"},
            }
            base = maps[language].get(kind, maps[language]["object"])
            if kind == "array":
                wrapper = "List" if language != "csharp" else "IReadOnlyList"
                base = f"{wrapper}<{map_type(schema.get('items', {}))}>"
            return base
        if language == "go":
            base = {"string": {"date-time": "time.Time", "uuid": "uuid.UUID"}.get(fmt, "string"), "integer": "int64", "number": "float64", "boolean": "bool", "object": "any"}.get(kind, "any")
            if kind == "array":
                base = f"[]{map_type(schema.get('items', {}))}"
            return base
        if language == "rust":
            base = {"string": {"date-time": "DateTime<Utc>", "uuid": "Uuid"}.get(fmt, "String"), "integer": "i64", "number": "f64", "boolean": "bool", "object": "serde_json::Value"}.get(kind, "serde_json::Value")
            if kind == "array":
                base = f"Vec<{map_type(schema.get('items', {}))}>"
            return base
        if language == "swift":
            base = {"string": {"date-time": "Date", "uuid": "UUID"}.get(fmt, "String"), "integer": "Int", "number": "Double", "boolean": "Bool", "object": "JSONValue"}.get(kind, "JSONValue")
            if kind == "array":
                base = f"[{map_type(schema.get('items', {}))}]"
            return base
        if language == "graphql-schema":
            base = {"string": "ID" if fmt == "uuid" else "String", "integer": "Int", "number": "Float", "boolean": "Boolean", "object": "JSON"}.get(kind, "JSON")
            if kind == "array":
                base = f"[{map_type(schema.get('items', {}))}!]"
            return base
        if language == "protobuf":
            base = {"string": "string", "integer": "int64", "number": "double", "boolean": "bool", "object": "google.protobuf.Struct"}.get(kind, "google.protobuf.Value")
            if fmt == "date-time":
                base = "google.protobuf.Timestamp"
            if kind == "array":
                base = f"repeated {map_type(schema.get('items', {}))}"
            return base
        return "object"
    return map_type


def _collect_schemas(document: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    schemas: list[tuple[str, Mapping[str, Any]]] = []
    components = document.get("components", {}).get("schemas", {})
    if isinstance(components, Mapping):
        schemas.extend((str(name), schema) for name, schema in components.items() if isinstance(schema, Mapping))
    channels = document.get("channels", {})
    if isinstance(channels, Mapping):
        for channel_name, channel in channels.items():
            if not isinstance(channel, Mapping):
                continue
            for direction in ("publish", "subscribe"):
                message = channel.get(direction, {}).get("message", {})
                payload = message.get("payload", {}) if isinstance(message, Mapping) else {}
                if isinstance(payload, Mapping) and payload:
                    schemas.append((f"{channel_name}_{direction}_payload", payload))
    return schemas


def build_context(document: Mapping[str, Any], source_file: Path | str, language: str, package_name: str | None = None) -> dict[str, Any]:
    mapper = _type_mapper(language)
    types: list[dict[str, Any]] = []
    flags = {"nullable": False, "enums": False, "allOf": False, "oneOf": False, "anyOf": False, "uuid": False, "date-time": False}
    for raw_name, schema in _collect_schemas(document):
        required = set(schema.get("required", []))
        properties: list[dict[str, Any]] = []
        for index, (json_name, prop) in enumerate(schema.get("properties", {}).items(), 1):
            if not isinstance(prop, Mapping):
                continue
            for flag in flags:
                flags[flag] = flags[flag] or flag in prop or prop.get("format") == flag
            is_required = json_name in required
            is_nullable = bool(prop.get("nullable")) or not is_required
            value_type = mapper(prop)
            enum_values = list(prop.get("enum", []))
            properties.append({
                "Name": _identifier(str(json_name), "pascal" if language in {"go", "csharp", "kotlin", "swift"} else "snake" if language in {"python", "rust", "protobuf"} else "camel"),
                "JsonName": str(json_name),
                "Type": value_type,
                "Format": str(prop.get("format", "")),
                "IsRequired": is_required,
                "IsNullable": is_nullable,
                "IsEnum": bool(enum_values),
                "EnumValues": enum_values,
                "Description": str(prop.get("description", "")),
                "Children": [],
                "Index": index,
                "OptionalType": f"Option<{value_type}>" if language == "rust" and is_nullable else value_type,
                "NullableType": f"{value_type}?" if language in {"csharp", "kotlin", "swift"} and is_nullable else value_type,
                "GraphQLType": f"{value_type}!" if is_required and not is_nullable else value_type,
            })
            flags["nullable"] = flags["nullable"] or is_nullable
            flags["enums"] = flags["enums"] or bool(enum_values)
        types.append({
            "Name": _identifier(raw_name, "pascal"),
            "Properties": properties,
            "Description": str(schema.get("description", "")),
            "IsEnum": bool(schema.get("enum")),
            "EnumValues": list(schema.get("enum", [])),
        })
        for key in ("allOf", "oneOf", "anyOf"):
            flags[key] = flags[key] or key in schema
    return {
        "PackageName": package_name,
        "SourceFile": Path(source_file).name,
        "Types": types,
        "HasUUID": flags["uuid"],
        "HasDateTime": flags["date-time"],
        "HasNullable": flags["nullable"],
        "HasEnums": flags["enums"],
        "HasAllOf": flags["allOf"],
        "HasOneOf": flags["oneOf"],
        "HasAnyOf": flags["anyOf"],
    }
