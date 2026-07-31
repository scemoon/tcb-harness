"""Plugin lifecycle CLI for aidlc code generators.

Provides:
    discover_all()          — scan built-in + user + project plugin dirs
    install_plugin()        — copy built-in plugin to project dir
    create_plugin_scaffold() — scaffold a new plugin directory
    search_index()          — search the built-in plugin index
    validate_plugin()       — validate MANIFEST + template smoke test
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .registry import (
    DEFAULT_GENERATORS_DIR,
    PluginManifest,
    _load_manifest,
    discover_plugins,
    render,
)

_BUILTIN_INDEX = Path(__file__).parent / "builtin_index.json"


def _builtin_index() -> dict[str, Any]:
    if _BUILTIN_INDEX.is_file():
        try:
            return json.loads(_BUILTIN_INDEX.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {"plugins": []}


# ─────────────────────────────────────────────────────────────
#  Multi-source discovery
# ─────────────────────────────────────────────────────────────

PluginSource = tuple[str, str, PluginManifest]  # (source_name, plugin_name, manifest)


def discover_all(project_root: Path | None = None) -> list[PluginSource]:
    """Scan all 3 plugin sources, return [(source, name, manifest), ...].

    Sources are checked in order: built-in < user < project.
    Duplicate names are resolved by the later source winning.
    """
    results: list[PluginSource] = []
    seen: set[str] = set()

    # 1. Built-in (cdh/generators/)
    for name, manifest in discover_plugins(DEFAULT_GENERATORS_DIR).items():
        results.append(("built-in", name, manifest))
        seen.add(name)

    # 2. User (~/.cdh/generators/)
    user_dir = Path.home() / ".cdh" / "generators"
    if user_dir.is_dir():
        for name, manifest in discover_plugins(user_dir).items():
            if name not in seen:
                results.append(("user", name, manifest))
                seen.add(name)

    # 3. Project (./aidlc/generators/)
    if project_root is not None:
        proj_dir = project_root / "aidlc" / "generators"
        if proj_dir.is_dir():
            for name, manifest in discover_plugins(proj_dir).items():
                if name not in seen:
                    results.append(("project", name, manifest))
                    seen.add(name)

    return results


def discover_all_as_dict(project_root: Path | None = None) -> dict[str, PluginManifest]:
    """Same as discover_all but merged into a single dict (later source wins)."""
    merged: dict[str, PluginManifest] = {}
    for source, name, manifest in discover_all(project_root):
        merged[name] = manifest
    return merged


def discover_all_plugins(project_root: Path | None = None) -> list[PluginSource]:
    """Alias for discover_all for CLI compatibility."""
    return discover_all(project_root)


def discover_all_plugins_merged(project_root: Path | None = None) -> dict[str, tuple[str, PluginManifest]]:
    """Return dict[name -> (source, manifest)] for CLI compatibility.

    Unlike discover_all_as_dict which returns dict[name -> manifest],
    this returns dict[name -> (source, manifest)] so callers can know
    which source each plugin came from.
    """
    merged: dict[str, tuple[str, PluginManifest]] = {}
    for source, name, manifest in discover_all(project_root):
        merged[name] = (source, manifest)
    return merged


def filter_by_source(plugins: list[PluginSource], source: str) -> list[PluginSource]:
    """Filter a list of PluginSource entries by source name."""
    return [(src, name, manifest) for src, name, manifest in plugins if src == source]


# ─────────────────────────────────────────────────────────────
#  Index search
# ─────────────────────────────────────────────────────────────

def search_index(
    query: str | None = None,
    tag: str | None = None,
    language_family: str | None = None,
) -> list[dict[str, Any]]:
    """Search the built-in plugin index."""
    idx = _builtin_index()
    results: list[dict[str, Any]] = []

    for entry in idx.get("plugins", []):
        if query:
            q = query.lower()
            if not (
                q in entry.get("name", "").lower()
                or q in entry.get("display_name", "").lower()
                or q in entry.get("description", "").lower()
            ):
                continue
        if tag and tag not in entry.get("tags", []):
            continue
        if language_family and entry.get("language_family") != language_family:
            continue
        results.append(entry)

    return results


def get_index_entry(name: str) -> dict[str, Any] | None:
    """Look up a plugin by name in the built-in index."""
    idx = _builtin_index()
    for entry in idx.get("plugins", []):
        if entry.get("name") == name:
            return entry
    return None


# ─────────────────────────────────────────────────────────────
#  Install
# ─────────────────────────────────────────────────────────────

def install_plugin(name: str, target_dir: Path) -> Path:
    """Copy a built-in plugin to target_dir.

    Args:
        name: plugin name (must exist in built-in index)
        target_dir: directory to copy into (e.g. ./aidlc/generators)

    Returns:
        Path to the installed plugin directory

    Raises:
        ValueError: if plugin not found in built-in or already exists in target
    """
    # Find in built-in
    builtin_dir = DEFAULT_GENERATORS_DIR / name
    if not builtin_dir.is_dir():
        raise ValueError(
            f"Plugin '{name}' not found in built-in generators. "
            f"Run 'cdh aidlc generators search {name}' to check availability."
        )

    target_plugin_dir = Path(target_dir).expanduser().resolve() / name
    if target_plugin_dir.is_dir():
        raise ValueError(
            f"Plugin '{name}' already exists at {target_plugin_dir}. "
            f"Remove it first to reinstall."
        )

    target_plugin_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(builtin_dir, target_plugin_dir)
    return target_plugin_dir


# ─────────────────────────────────────────────────────────────
#  Scaffold
# ─────────────────────────────────────────────────────────────

_SCAFFOLD_MANIFEST_TOML = """\
# Plugin manifest for {name}
# See: https://github.com/aidlc/aidlc-generators/blob/main/docs/PLUGIN_SPEC.md

[plugin]
name = "{name}"
display_name = "{display_name}"
file_extension = ".{ext}"
mime_type = "text/plain"
default_outdir = "{name}"
output_filename_template = "{{{{name}}}}.{ext}"
package_name_default = "types"

[features]
enums = true
nullable = true
format_hints = ["date-time", "uuid", "email"]

[imports]
# Add import statements keyed by format hint
"""

_SCAFFOLD_TEMPLATE_TMPL = """\
// Auto-generated from {{{{SourceFile}}}}
{{{{range .Types}}}}
// {{.Name}} — {{.Description}}
{{.Name}}
{{{{- end}}}}
"""


def create_plugin_scaffold(name: str, target_dir: Path, display_name: str = "", ext: str = "") -> Path:
    """Scaffold a new plugin directory.

    Args:
        name: plugin name (used as directory name)
        target_dir: parent directory (e.g. ./aidlc/generators)
        display_name: human-readable name (defaults to name.title())
        ext: file extension (defaults to name)

    Returns:
        Path to the created plugin directory
    """
    disp = display_name or name.title()
    file_ext = ext or name

    plugin_dir = Path(target_dir).expanduser().resolve() / name
    if plugin_dir.is_dir():
        raise ValueError(f"Plugin directory already exists: {plugin_dir}")

    plugin_dir.mkdir(parents=True, exist_ok=True)

    manifest = _SCAFFOLD_MANIFEST_TMPL.format(
        name=name,
        display_name=disp,
        ext=file_ext,
    )
    plugin_dir.joinpath("MANIFEST.toml").write_text(manifest, encoding="utf-8")

    template_file = f"template.{file_ext}.tmpl"
    template = _SCAFFOLD_TEMPLATE_TMPL.format(
        name=name,
        display_name=disp,
        ext=file_ext,
    )
    plugin_dir.joinpath(template_file).write_text(template, encoding="utf-8")

    return plugin_dir


# ─────────────────────────────────────────────────────────────
#  Validate
# ─────────────────────────────────────────────────────────────

def validate_plugin(plugin_dir: Path) -> tuple[bool, list[str]]:
    """Validate a plugin directory: MANIFEST + template + smoke test.

    Returns (is_valid, list_of_errors).
    """
    errors: list[str] = []
    directory = Path(plugin_dir).expanduser().resolve()

    if not directory.is_dir():
        return False, [f"Not a directory: {directory}"]

    # MANIFEST.toml
    manifest_path = directory / "MANIFEST.toml"
    if not manifest_path.is_file():
        errors.append("MANIFEST.toml not found")
        return False, errors

    try:
        manifest = _load_manifest(directory)
    except Exception as e:
        errors.append(f"Invalid MANIFEST.toml: {e}")
        return False, errors

    # template
    if not manifest.template_path.is_file():
        errors.append(f"Template file not found: {manifest.template_path}")

    if errors:
        return False, errors

    # Smoke test: render with dummy context
    dummy_context = {
        "PackageName": "TestTypes",
        "SourceFile": "test.yaml",
        "Types": [
            {
                "Name": "TestEntity",
                "Description": "A test entity",
                "Properties": [
                    {
                        "Name": "id",
                        "Type": "string",
                        "JsonName": "id",
                        "Format": "uuid",
                        "IsRequired": True,
                        "IsNullable": False,
                        "IsEnum": False,
                        "EnumValues": [],
                        "Description": "Unique ID",
                        "Children": [],
                    },
                ],
            },
        ],
        "HasUUID": True,
        "HasDateTime": True,
        "HasNullable": True,
        "HasEnums": False,
        "HasAllOf": False,
        "HasOneOf": False,
        "HasAnyOf": False,
        "HasReadOnly": False,
        "HasWriteOnly": False,
    }

    try:
        output = render(manifest.name, dummy_context)
        if not output or len(output) < 10:
            errors.append("Template rendered empty or too short output")
    except Exception as e:
        errors.append(f"Template render failed: {e}")

    return not errors, errors


# ─────────────────────────────────────────────────────────────
#  Summary helpers
# ─────────────────────────────────────────────────────────────

def format_plugin_table(plugins: list[PluginSource]) -> str:
    """Format a list of (source, name, manifest) as a text table."""
    if not plugins:
        return "No plugins found."

    lines = [
        f"{'SOURCE':<10} {'NAME':<18} {'DISPLAY':<20} {'EXT':<8} {'SUPPORTS'}"
        f"{'─' * 60}",
    ]
    for source, name, manifest in plugins:
        supports = ", ".join(manifest.supports) if manifest.supports else "-"
        lines.append(
            f"{source:<10} {name:<18} {manifest.display_name:<20} "
            f"{manifest.file_extension:<8} {supports}"
        )
    return "\n".join(lines)


def format_index_table(entries: list[dict[str, Any]]) -> str:
    """Format plugin index entries as a text table."""
    if not entries:
        return "No plugins found."

    lines = [
        f"{'NAME':<18} {'DISPLAY':<20} {'LANGUAGE':<12} {'DESCRIPTION'}",
        f"{'─' * 70}",
    ]
    for entry in entries:
        desc = entry.get("description", "")[:40]
        lines.append(
            f"{entry.get('name', ''):<18} "
            f"{entry.get('display_name', ''):<20} "
            f"{entry.get('language_family', ''):<12} "
            f"{desc}"
        )
    return "\n".join(lines)
