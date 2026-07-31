"""Spectral-style OpenAPI/AsyncAPI linting rules.

Provides a comprehensive set of linting rules for API contracts, inspired by
the Spectral JSON/YAML linter. Rules cover operation, schema, security,
documentation, and consistency checks.

Usage::

    from cdh.validators.spectral import SpectralLinter, load_ruleset
    ruleset = load_ruleset("standard")
    linter = SpectralLinter(ruleset)
    results = linter.lint_document(openapi_dict)
    for r in results:
        print(f"{r['severity']} {r['code']}: {r['message']}")
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

__all__ = ["SpectralLinter", "load_ruleset", "LintResult", "RULESETS"]

DEFAULT_SEVERITY = "warn"


@dataclass
class LintResult:
    code: str
    message: str
    severity: str
    path: list[str]
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "path": ".".join(self.path),
            "source": self.source,
        }


class SpectralLinter:
    """Spectral-style OpenAPI linter."""

    def __init__(self, rules: dict[str, dict]):
        self.rules = rules

    def lint_document(
        self,
        document: dict[str, Any],
        source: str | None = None,
    ) -> list[LintResult]:
        results: list[LintResult] = []
        spec_version = self._detect_version(document)

        for rule_id, rule_def in self.rules.items():
            if not rule_def.get("enabled", True):
                continue
            severity = rule_def.get("severity", DEFAULT_SEVERITY)
            matches = self._evaluate_rule(rule_id, rule_def, document, spec_version)
            for match in matches:
                results.append(LintResult(
                    code=rule_id,
                    message=match["message"],
                    severity=severity,
                    path=match["path"],
                    source=source,
                ))

        return sorted(results, key=lambda x: (["error", "warn", "info", "hint"].index(x.severity) if x.severity in ["error", "warn", "info", "hint"] else 3, x.path))

    def _detect_version(self, doc: dict[str, Any]) -> str:
        if "openapi" in doc:
            return "openapi"
        if "asyncapi" in doc:
            return "asyncapi"
        return "unknown"

    def _evaluate_rule(
        self,
        rule_id: str,
        rule_def: dict[str, Any],
        doc: dict[str, Any],
        spec_version: str,
    ) -> list[dict[str, Any]]:
        rule_type = rule_def.get("type", "rule")
        if rule_type == "rule":
            return self._eval_rule(rule_id, rule_def, doc)
        elif rule_type == "友列":
            return self._eval_taxonomy(rule_id, rule_def, doc)
        return []

    def _eval_rule(
        self,
        rule_id: str,
        rule_def: dict[str, Any],
        doc: dict[str, Any],
    ) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        given = rule_def.get("given")
        then = rule_def.get("then", [])

        if not given or not then:
            return matches

        nodes = self._find_nodes(doc, given)
        if isinstance(then, dict):
            then = [then]

        for node_path, node_value in nodes:
            for then_item in then:
                field_path = then_item.get("field", "")
                function = then_item.get("function", "")
                function_options = then_item.get("functionOptions", {})

                target_value = self._get_at_path(node_value, field_path) if field_path else node_value
                target_path = node_path + ([field_path] if field_path else [])

                if function == "truthy":
                    if not target_value:
                        matches.append({
                            "message": rule_def.get("message", f"{rule_id} must be truthy"),
                            "path": target_path,
                        })
                elif function == "falsy":
                    if target_value:
                        matches.append({
                            "message": rule_def.get("message", f"{rule_id} must be falsy"),
                            "path": target_path,
                        })
                elif function == "pattern":
                    pattern = function_options.get("match", "")
                    if target_value and not re.search(pattern, str(target_value)):
                        matches.append({
                            "message": rule_def.get("message", f"{rule_id} must match {pattern}"),
                            "path": target_path,
                        })
                elif function == "schema":
                    schema = function_options.get("schema", {})
                    errors = self._validate_schema(target_value, schema)
                    for err in errors:
                        matches.append({
                            "message": err,
                            "path": target_path,
                        })
                elif function == "length":
                    min_len = function_options.get("min")
                    max_len = function_options.get("max")
                    if target_value is not None:
                        actual_len = len(target_value) if isinstance(target_value, (str, list, dict)) else target_value
                        if min_len is not None and actual_len < min_len:
                            matches.append({
                                "message": f"{rule_id}: length must be >= {min_len}",
                                "path": target_path,
                            })
                        if max_len is not None and actual_len > max_len:
                            matches.append({
                                "message": f"{rule_id}: length must be <= {max_len}",
                                "path": target_path,
                            })
                elif function == "enumeration":
                    enum_vals = function_options.get("values", [])
                    if target_value not in enum_vals:
                        matches.append({
                            "message": f"{rule_id}: value must be one of {enum_vals}",
                            "path": target_path,
                        })
                elif function == "casing":
                    case_type = function_options.get("type", "camelCase")
                    if target_value and not self._check_casing(str(target_value), case_type):
                        matches.append({
                            "message": f"{rule_id}: must be {case_type}",
                            "path": target_path,
                        })

        return matches

    def _eval_taxonomy(
        self,
        rule_id: str,
        rule_def: dict[str, Any],
        doc: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return []

    def _find_nodes(self, doc: dict[str, Any], given: str | list[str]) -> list[tuple[list[str], Any]]:
        results: list[tuple[list[str], Any]] = []
        if isinstance(given, str):
            given = [given]

        for g in given:
            if g.startswith("$."):
                value = self._get_at_path(doc, g[2:])
                if value is not None:
                    results.append((g[2:].split("."), value))
            elif g == "$":
                results.append(([], doc))
            elif g == "$.paths":
                paths = doc.get("paths", {})
                for path_key, path_val in paths.items():
                    results.append((["paths", path_key], path_val))
            elif g.startswith("$.paths."):
                suffix = g[8:]
                paths = doc.get("paths", {})
                for path_key, path_val in paths.items():
                    if suffix.startswith(path_key) or path_key in suffix:
                        remaining = suffix[len(path_key):].strip(".")
                        if remaining:
                            val = self._get_at_path(path_val, remaining)
                            if val is not None:
                                results.append((["paths", path_key] + remaining.split("."), val))
                        else:
                            results.append((["paths", path_key], path_val))
            elif g == "$.components.schemas":
                schemas = doc.get("components", {}).get("schemas", {})
                for schema_key, schema_val in schemas.items():
                    results.append((["components", "schemas", schema_key], schema_val))
            else:
                value = self._get_at_path(doc, g.lstrip("$."))
                if value is not None:
                    results.append((g.lstrip("$.").split("."), value))

        return results

    def _get_at_path(self, root: Any, path: str) -> Any:
        if not path:
            return root
        parts = path.split(".")
        current = root
        for part in parts:
            if part.startswith("[") and part.endswith("]"):
                idx = int(part[1:-1])
                if isinstance(current, (list, tuple)) and abs(idx) < len(current):
                    current = current[idx]
                else:
                    return None
            elif isinstance(current, dict):
                current = current.get(part)
            else:
                return None
            if current is None:
                return None
        return current

    def _validate_schema(self, value: Any, schema: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if schema.get("type") == "string":
            min_len = schema.get("minLength")
            max_len = schema.get("maxLength")
            pattern = schema.get("pattern")
            if isinstance(value, str):
                if min_len is not None and len(value) < min_len:
                    errors.append(f"String must be at least {min_len} characters")
                if max_len is not None and len(value) > max_len:
                    errors.append(f"String must be at most {max_len} characters")
                if pattern and not re.search(pattern, value):
                    errors.append(f"String must match pattern {pattern}")
        return errors

    def _check_casing(self, value: str, case_type: str) -> bool:
        if case_type == "camelCase":
            return bool(re.match(r"^[a-z][a-zA-Z0-9]*$", value))
        elif case_type == "PascalCase":
            return bool(re.match(r"^[A-Z][a-zA-Z0-9]*$", value))
        elif case_type == "snake_case":
            return bool(re.match(r"^[a-z][a-z0-9_]*$", value))
        elif case_type == "kebab-case":
            return bool(re.match(r"^[a-z][a-z0-9-]*$", value))
        return True


def load_ruleset(name: str) -> dict[str, dict]:
    """Load a built-in ruleset by name."""
    from pathlib import Path

    builtin_path = Path(__file__).parent.parent / "rules" / "spectral.yaml"
    if builtin_path.is_file():
        import yaml
        with open(builtin_path) as f:
            doc = yaml.safe_load(f)
            if name in doc:
                return doc[name]

    return _get_default_ruleset()


def _get_default_ruleset() -> dict[str, dict]:
    return {
        "info-contact": {
            "given": "$.info",
            "then": {
                "field": "contact",
                "function": "truthy",
            },
            "message": "Info object must have contact information",
            "severity": "warn",
            "type": "rule",
            "enabled": True,
        },
        "info-description": {
            "given": "$.info",
            "then": {
                "field": "description",
                "function": "truthy",
            },
            "message": "Info object must have a description",
            "severity": "warn",
            "type": "rule",
            "enabled": True,
        },
        "info-license": {
            "given": "$.info",
            "then": {
                "field": "license",
                "function": "truthy",
            },
            "message": "Info object should have license information",
            "severity": "info",
            "type": "rule",
            "enabled": True,
        },
        "operation-description": {
            "given": "$.paths[*][*]",
            "then": {
                "field": "description",
                "function": "truthy",
            },
            "message": "Operation must have a description",
            "severity": "warn",
            "type": "rule",
            "enabled": True,
        },
        "operation-tags": {
            "given": "$.paths[*][*]",
            "then": {
                "field": "tags",
                "function": "truthy",
            },
            "message": "Operation should have tags for grouping",
            "severity": "info",
            "type": "rule",
            "enabled": True,
        },
        "operation-summary": {
            "given": "$.paths[*][*]",
            "then": {
                "field": "summary",
                "function": "truthy",
            },
            "message": "Operation should have a summary",
            "severity": "info",
            "type": "rule",
            "enabled": True,
        },
        "parameter-description": {
            "given": "$.paths[*][*].parameters[*]",
            "then": {
                "field": "description",
                "function": "truthy",
            },
            "message": "Parameter must have a description",
            "severity": "warn",
            "type": "rule",
            "enabled": True,
        },
        "schema-description": {
            "given": "$.components.schemas[*]",
            "then": {
                "field": "description",
                "function": "truthy",
            },
            "message": "Schema must have a description",
            "severity": "info",
            "type": "rule",
            "enabled": True,
        },
        "path-keys-kebab-case": {
            "given": "$.paths",
            "then": {
                "function": "pattern",
                "functionOptions": {"match": "^\\/([a-z0-9-]+\\/)*[a-z0-9-]*$"},
            },
            "message": "Path keys must be kebab-case",
            "severity": "warn",
            "type": "rule",
            "enabled": True,
        },
        "no scheme steal": {
            "given": "$.servers[*]",
            "then": {
                "field": "url",
                "function": "pattern",
                "functionOptions": {"match": "^https://"},
            },
            "message": "Server URL should use HTTPS",
            "severity": "warn",
            "type": "rule",
            "enabled": False,
        },
        "no-http-in-production": {
            "given": "$.servers[*]",
            "then": {
                "function": "pattern",
                "functionOptions": {"match": "^http://"},
            },
            "message": "Server URL uses HTTP (not recommended for production)",
            "severity": "warn",
            "type": "rule",
            "enabled": True,
        },
        "duplicated entry in enum": {
            "given": "$.components.schemas[*].enum",
            "then": {
                "function": "schema",
                "functionOptions": {"uniqueItems": True},
            },
            "message": "Enum values must be unique",
            "severity": "error",
            "type": "rule",
            "enabled": True,
        },
        "oas3-server-variables": {
            "given": "$.servers[*]",
            "then": {
                "field": "variables",
                "function": "truthy",
            },
            "message": "Server should define variables for templated URLs",
            "severity": "info",
            "type": "rule",
            "enabled": False,
        },
    }


# Built-in rulesets
RULESETS = {
    "standard": _get_default_ruleset(),
}


def lint_openapi(
    document: dict[str, Any],
    ruleset_name: str = "standard",
    source: str | None = None,
) -> list[LintResult]:
    """Lint an OpenAPI/AsyncAPI document.

    Args:
        document: Parsed OpenAPI/AsyncAPI document dict
        ruleset_name: Name of ruleset to use
        source: Optional source file path for error reporting

    Returns:
        List of LintResult objects
    """
    ruleset = load_ruleset(ruleset_name)
    linter = SpectralLinter(ruleset)
    return linter.lint_document(document, source)


def lint_openapi_json(json_str: str, **kwargs) -> list[LintResult]:
    """Lint an OpenAPI document from JSON string."""
    return lint_openapi(json.loads(json_str), **kwargs)


def lint_openapi_yaml(yaml_str: str, **kwargs) -> list[LintResult]:
    """Lint an OpenAPI document from YAML string."""
    import yaml
    return lint_openapi(yaml.safe_load(yaml_str), **kwargs)
