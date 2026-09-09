"""Semgrep-style pattern detection for brownfield migration and code quality.

Provides a rule engine that scans source code files for patterns defined in
YAML/JSON rule files. Supports metavariables, file path filtering, and
structured JSON output for CI integration.

Usage::

    from cdh.tools.pattern_detect import PatternEngine, load_rules
    rules = load_rules("rules.yaml")
    engine = PatternEngine(rules)
    findings = engine.scan(["src/"])
    for f in findings:
        print(f"{f['file']}:{f['line']} {f['severity']} {f['message']}")
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["PatternEngine", "load_rules", "Finding", "Rule"]

DEFAULT_RULES_DIR = Path(__file__).parent.parent / "rules"
DEFAULT_RULES_FILE = "patterns.yaml"


@dataclass
class Rule:
    """A pattern detection rule."""

    id: str
    message: str
    severity: str
    languages: list[str]
    pattern: str | None = None
    regex: str | None = None
    path_filter: str | None = None
    metavariable_regex: dict[str, str] | None = None
    fix: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def matches_language(self, filename: str) -> bool:
        if not self.languages or "*" in self.languages:
            return True
        ext = os.path.splitext(filename)[1].lstrip(".")
        return ext in self.languages or filename.endswith(self.languages)


@dataclass
class Finding:
    """A pattern match finding."""

    rule_id: str
    file: str
    line: int
    column: int
    end_line: int | None
    matched_text: str
    message: str
    severity: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "matched_text": self.matched_text,
            "message": self.message,
            "severity": self.severity,
            "metadata": self.metadata,
        }


def _parse_yaml_rules(content: str) -> list[Rule]:
    import yaml

    rules: list[Rule] = []
    doc = yaml.safe_load(content)
    if not doc:
        return rules

    for category, rules_dict in doc.items():
        if not isinstance(rules_dict, dict):
            continue
        for rule_id, rule_def in rules_dict.items():
            if not isinstance(rule_def, dict):
                continue
            languages = rule_def.get("languages") or rule_def.get("language") or []
            if isinstance(languages, str):
                languages = [languages]
            rules.append(Rule(
                id=f"{category}.{rule_id}",
                message=rule_def.get("message", ""),
                severity=rule_def.get("severity", "WARNING"),
                languages=languages,
                pattern=rule_def.get("pattern"),
                regex=rule_def.get("regex"),
                path_filter=rule_def.get("path"),
                metavariable_regex=rule_def.get("metavariable_regex"),
                fix=rule_def.get("fix"),
                metadata=rule_def.get("metadata", {}),
            ))

    return rules


def _parse_json_rules(content: str) -> list[Rule]:
    rules: list[Rule] = []
    doc = json.loads(content)

    for rule_def in doc.get("rules", []):
        languages = rule_def.get("languages") or []
        if isinstance(languages, str):
            languages = [languages]
        rules.append(Rule(
            id=rule_def.get("id", "unknown"),
            message=rule_def.get("message", ""),
            severity=rule_def.get("severity", "WARNING"),
            languages=languages,
            pattern=rule_def.get("pattern"),
            regex=rule_def.get("regex"),
            path_filter=rule_def.get("path"),
            metavariable_regex=rule_def.get("metavariable_regex"),
            fix=rule_def.get("fix"),
            metadata=rule_def.get("metadata", {}),
        ))

    return rules


def load_rules(source: str | Path | dict | list) -> list[Rule]:
    """Load pattern rules from a file path, YAML/JSON string, or dict/list."""
    if isinstance(source, (list, tuple)):
        rules: list[Rule] = []
        for item in source:
            rules.extend(load_rules(item))
        return rules

    if isinstance(source, dict):
        return _parse_json_rules(json.dumps(source)) if "rules" in source else _parse_yaml_rules(json.dumps(source))

    if isinstance(source, str):
        if os.path.isfile(source):
            content = Path(source).read_text(encoding="utf-8")
        else:
            content = source

        if source.endswith(".json") or (os.path.isfile(source) and json.loads(content).get("rules")):
            return _parse_json_rules(content)
        return _parse_yaml_rules(content)

    path = Path(source)
    if path.is_file():
        content = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            return _parse_json_rules(content)
        return _parse_yaml_rules(content)

    return []


class PatternEngine:
    """Semgrep-style pattern detection engine."""

    def __init__(self, rules: list[Rule] | dict | str | Path):
        if not isinstance(rules, list):
            rules = load_rules(rules)
        self.rules = rules
        self._compiled: dict[str, tuple[re.Pattern, dict[str, re.Pattern]]] = {}
        self._compile()

    def _compile(self) -> None:
        for rule in self.rules:
            if rule.regex:
                self._compiled[rule.id] = (
                    re.compile(rule.regex, re.MULTILINE),
                    {},
                )
            elif rule.pattern:
                py_pattern, meta_map = _pattern_to_python(rule.pattern)
                self._compiled[rule.id] = (
                    re.compile(py_pattern, re.MULTILINE),
                    {k: re.compile(v) for k, v in (meta_map or {}).items()},
                )

    def scan(
        self,
        paths: list[str | Path],
        *,
        exclude_paths: list[str] | None = None,
        max_file_size_mb: int = 10,
        gitignore: bool = True,
    ) -> list[Finding]:
        """Scan files/directories for pattern matches.

        Args:
            paths: List of files or directories to scan
            exclude_paths: List of glob patterns to exclude
            max_file_size_mb: Skip files larger than this
            gitignore: Respect .gitignore files

        Returns:
            List of Finding objects
        """
        findings: list[Finding] = []
        exclude_patterns = exclude_paths or []

        for base_path in paths:
            base = Path(base_path)
            if base.is_dir():
                files = _iter_files(
                    base,
                    exclude=exclude_patterns,
                    max_size_mb=max_file_size_mb,
                    gitignore=gitignore,
                )
            elif base.is_file():
                files = [base]
            else:
                continue

            for fpath in files:
                findings.extend(self._scan_file(fpath))

        return findings

    def _scan_file(self, fpath: Path) -> list[Finding]:
        findings: list[Finding] = []
        filename = str(fpath)

        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return findings

        for rule in self.rules:
            if not rule.matches_language(filename):
                continue

            if rule.path_filter:
                if not re.search(rule.path_filter, filename):
                    continue

            compiled = self._compiled.get(rule.id)
            if not compiled:
                continue

            pattern_re, meta_regexes = compiled

            for m in pattern_re.finditer(content):
                matched_text = m.group(0)
                line, col = _offset_to_line_col(content, m.start())
                end_line, _ = _offset_to_line_col(content, m.end())

                if meta_regexes:
                    meta_matches = {}
                    for meta_name, meta_re in meta_regexes.items():
                        for gname, gval in m.groupdict().items():
                            if gval and meta_re.fullmatch(str(gval)):
                                meta_matches[meta_name] = gval
                    if len(meta_matches) < len(meta_regexes):
                        continue

                fix = None
                if rule.fix:
                    fix = _apply_fix(content, m, rule.fix)

                findings.append(Finding(
                    rule_id=rule.id,
                    file=filename,
                    line=line,
                    column=col,
                    end_line=end_line,
                    matched_text=matched_text,
                    message=rule.message,
                    severity=rule.severity,
                    metadata={"fix": fix} if fix else {},
                ))

        return findings

    def scan_json(self, paths: list[str | Path], **kwargs) -> str:
        """Scan and return results as JSON."""
        findings = self.scan(paths, **kwargs)
        return json.dumps({
            "results": [f.to_dict() for f in findings],
            "total": len(findings),
            "rules": {r.id: r.message for r in self.rules},
        }, indent=2)


def _pattern_to_python(pattern: str) -> tuple[str, dict[str, str]]:
    """Convert Semgrep pattern syntax to Python regex.

    Handles: $VAR, $TYPE, $NUM, string literals, basic operators.
    """
    meta_map: dict[str, str] = {}
    counter = 0

    def _make_meta(name: str, regex: str) -> str:
        nonlocal counter
        key = f"_M{counter}_"
        counter += 1
        meta_map[key] = regex
        return key

    result = []
    i = 0
    n = len(pattern)

    while i < n:
        c = pattern[i]
        if c == "$":
            j = i + 1
            while j < n and pattern[j].isalnum():
                j += 1
            var_name = pattern[i:j]

            meta_types = {
                "STRING": r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"",
                "NUMBER": r"\d+(?:\.\d+)?",
                "ID": r"[a-zA-Z_]\w*",
                "TYPE": r"[A-Z][a-zA-Z0-9_]*",
                "BOOL": r"true|false",
                "NULL": r"null|nil",
            }

            if var_name in meta_types:
                result.append(_make_meta(var_name, meta_types[var_name]))
            elif var_name == "...":
                result.append(".*")
            elif var_name.startswith("...") and var_name.endswith("..."):
                mid = var_name[3:-3]
                result.append(f".*{re.escape(mid)}.*")
            else:
                result.append(_make_meta(var_name, r"\w+"))

            i = j
        elif c == "'" or c == '"':
            quote = c
            j = i + 1
            while j < n and pattern[j] != quote:
                if pattern[j] == "\\" and j + 1 < n:
                    j += 2
                else:
                    j += 1
            literal = pattern[i:j + 1]
            result.append(re.escape(literal))
            i = j + 1
        else:
            result.append(re.escape(c))
            i += 1

    return "".join(result), meta_map


def _offset_to_line_col(text: str, offset: int) -> tuple[int, int]:
    """Convert byte offset to (line, column) 1-indexed."""
    lines = text[:offset].split("\n")
    return len(lines), len(lines[-1]) + 1 if lines else 1


def _apply_fix(content: str, match: re.Match, fix: str) -> str | None:
    """Apply a fix (replacement) to the matched text."""
    try:
        return content[:match.start()] + fix + content[match.end():]
    except Exception:
        return None


def _iter_files(
    base: Path,
    exclude: list[str],
    max_size_mb: int,
    gitignore: bool,
) -> list[Path]:
    """Iterate over files in a directory, respecting gitignore and exclusions."""
    import fnmatch

    gitignore_patterns: set[str] = set()
    if gitignore:
        gi_file = base / ".gitignore"
        if gi_file.is_file():
            gitignore_patterns = set(gi_file.read_text().splitlines())

    skip_suffixes = {"__pycache__", ".pyc", ".pyo", ".so", ".o", ".a", ".dylib"}

    files: list[Path] = []
    for root, dirs, filenames in os.walk(base):
        root_path = Path(root)

        dirs[:] = [d for d in dirs if d not in skip_suffixes and not d.startswith(".")]

        for pattern in gitignore_patterns:
            dirs = [d for d in dirs if not fnmatch.fnmatch(d, pattern)]

        for fname in filenames:
            if fname.startswith("."):
                continue
            fpath = root_path / fname
            if any(fnmatch.fnmatch(str(fpath.relative_to(base)), p) for p in exclude):
                continue
            if any(fnmatch.fnmatch(fname, p) for p in gitignore_patterns):
                continue
            try:
                size_mb = fpath.stat().st_size / (1024 * 1024)
                if size_mb > max_size_mb:
                    continue
            except OSError:
                continue
            files.append(fpath)

    return files


def run_pattern_check(
    target: str | Path,
    rules_file: str | Path | None = None,
    output_format: str = "text",
    exclude: list[str] | None = None,
) -> list[Finding]:
    """Convenience function to run pattern detection on a target.

    Args:
        target: File or directory to scan
        rules_file: Path to rules file (default: ~/.cdh/rules/patterns.yaml)
        output_format: 'text' or 'json'
        exclude: List of patterns to exclude

    Returns:
        List of findings
    """
    if rules_file is None:
        default_rules = Path.home() / ".cdh" / "rules" / "patterns.yaml"
        if default_rules.is_file():
            rules_file = default_rules
        else:
            rules_file = Path(__file__).parent.parent / "rules" / "patterns.yaml"

    rules = load_rules(rules_file) if isinstance(rules_file, (str, Path)) and os.path.isfile(rules_file) else []
    engine = PatternEngine(rules)
    return engine.scan([target], exclude_paths=exclude or [])
