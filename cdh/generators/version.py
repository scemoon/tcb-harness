"""SemVer 2.0 parsing, comparison, and dependency resolution for aidlc plugins.

Usage::

    from cdh.generators.version import SemVer, resolve_dependencies
    v1 = SemVer.from_string("1.2.3")
    v2 = SemVer.from_string("2.0.0-alpha.1")
    print(v1 < v2)  # True

    deps = [{"name": "kotlin", "version": ">=1.0.0"}, {"name": "jvm", "version": "^2.0.0"}]
    resolved = resolve_dependencies(deps, available={"kotlin": SemVer("1.5.0"), "jvm": SemVer("2.1.0")})
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

__all__ = ["SemVer", "VersionSpec", "resolve_dependencies", "parse_version_spec"]


@dataclass(frozen=True, order=True)
class SemVer:
    """Semantic version 2.0.0."""

    major: int
    minor: int
    patch: int
    pre: tuple[str, ...] = ()
    build: tuple[str, ...] = ()

    _RE = re.compile(
        r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
        r"(?:-(?P<pre>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
        r"(?:\+(?P<build>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?$"
    )

    @classmethod
    def from_string(cls, s: str) -> "SemVer":
        m = cls._RE.match(s.strip())
        if not m:
            raise ValueError(f"Invalid semver: {s!r}")
        pre = tuple(m["pre"].split(".")) if m["pre"] else ()
        build = tuple(m["build"].split(".")) if m["build"] else ()
        return cls(
            major=int(m["major"]),
            minor=int(m["minor"]),
            patch=int(m["patch"]),
            pre=pre,
            build=build,
        )

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre:
            base += "-" + ".".join(self.pre)
        if self.build:
            base += "+" + ".".join(self.build)
        return base

    def satisfies(self, spec: "VersionSpec") -> bool:
        return spec.matches(self)


@dataclass(frozen=True)
class VersionSpec:
    """A version constraint like ^1.0.0, >=2.0.0, <3.0.0."""

    op: str
    version: SemVer

    _OPS = {"==", "!=", ">=", "<=", ">", "<", "~>", "^", "="}

    @classmethod
    def parse(cls, s: str) -> "VersionSpec":
        s = s.strip()
        if s.startswith((">=", "<=", "==", "!=", ">", "<", "~>", "^")):
            op = s[:2] if s.startswith((">=", "<=", "==", "!=", "~>", "^")) else s[:1]
            ver_str = s[len(op):]
        elif s.startswith("="):
            op, ver_str = "==", s[1:]
        else:
            raise ValueError(f"Cannot parse version spec: {s!r}")
        return cls(op=op, version=SemVer.from_string(ver_str.strip()))

    def matches(self, v: SemVer) -> bool:
        base = self.version
        if self.op == "==":
            return v == base
        if self.op == "!=":
            return v != base
        if self.op == ">":
            return v > base
        if self.op == ">=":
            return v >= base
        if self.op == "<":
            return v < base
        if self.op == "<=":
            return v <= base
        if self.op == "^":
            return v.major == base.major and (v.minor > base.minor or (v.minor == base.minor and v.patch >= base.patch))
        if self.op == "~>":
            return v.major == base.major and v.minor == base.minor and v.patch >= base.patch
        if self.op == "=":
            return v == base
        raise ValueError(f"Unknown op: {self.op!r}")


def parse_version_spec(constraint: str) -> VersionSpec:
    """Parse a single version constraint string."""
    return VersionSpec.parse(constraint)


def resolve_dependencies(
    deps: Iterable[dict[str, str]],
    available: dict[str, SemVer],
) -> dict[str, SemVer]:
    """Resolve plugin dependencies.

    Args:
        deps: Iterable of {"name": str, "version": str} constraints
        available: Map of plugin name -> installed SemVer

    Returns:
        Dict of plugin name -> resolved SemVer that satisfies constraints

    Raises:
        ValueError: If a dependency cannot be satisfied
    """
    resolved: dict[str, SemVer] = {}
    for dep in deps:
        name = dep.get("name") or dep.get("plugin")
        constraint_str = dep.get("version") or dep.get("spec") or ">=0.0.0"
        if not name:
            continue

        if name in resolved:
            continue

        if name not in available:
            raise ValueError(f"Dependency {name} {constraint_str} not available")

        spec = parse_version_spec(constraint_str)
        candidate = available[name]

        if not spec.matches(candidate):
            raise ValueError(
                f"Plugin {name}@{candidate} does not satisfy {spec.op}{spec.version} "
                f"(available: {name}@{candidate})"
            )

        resolved[name] = candidate

    return resolved


class PluginRegistry:
    """Plugin registry with version tracking and dependency resolution."""

    def __init__(self):
        self._plugins: dict[str, dict[str, SemVer | list[dict[str, str]]]] = {}

    def add_plugin(
        self,
        name: str,
        version: SemVer,
        dependencies: list[dict[str, str]] | None = None,
    ) -> None:
        self._plugins[name] = {
            "version": version,
            "dependencies": dependencies or [],
        }

    def get_version(self, name: str) -> SemVer | None:
        entry = self._plugins.get(name)
        return entry["version"] if entry else None

    def get_dependencies(self, name: str) -> list[dict[str, str]]:
        entry = self._plugins.get(name)
        return entry["dependencies"] if entry else []

    def resolve_all(self) -> dict[str, SemVer]:
        """Resolve all plugins and their transitive dependencies."""
        resolved: dict[str, SemVer] = {}
        to_resolve: list[tuple[str, list[dict[str, str]]]] = [
            (name, deps) for name, info in self._plugins.items()
            for deps in [info["dependencies"]]
        ]

        while to_resolve:
            name, deps = to_resolve.pop(0)
            if name in resolved:
                continue
            version = self.get_version(name)
            if version is None:
                raise ValueError(f"Plugin {name} not found in registry")
            resolved[name] = version
            for dep in deps:
                dep_name = dep.get("name") or dep.get("plugin")
                if dep_name:
                    dep_deps = self.get_dependencies(dep_name)
                    to_resolve.append((dep_name, dep_deps))

        return resolved

    def check_conflicts(self, selected: dict[str, SemVer]) -> list[str]:
        """Check for version conflicts in selected plugins."""
        conflicts: list[str] = []
        for name, version in selected.items():
            current = self.get_version(name)
            if current and current != version:
                conflicts.append(f"{name}: tried to set {version} but registry has {current}")
        return conflicts
