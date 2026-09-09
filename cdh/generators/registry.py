from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


DEFAULT_GENERATORS_DIR = Path(__file__).parent


class TemplateError(ValueError):
    pass


@dataclass(frozen=True)
class PluginManifest:
    name: str
    display_name: str
    file_extension: str
    mime_type: str
    default_outdir: str
    output_filename_template: str
    package_name_default: str
    supports: tuple[str, ...]
    format_hints: tuple[str, ...]
    imports: Mapping[str, str]
    directory: Path
    template_path: Path
    imports_template_path: Path | None = None

    @property
    def template_file(self) -> Path:
        return self.template_path


def _load_manifest(directory: Path) -> PluginManifest:
    manifest_path = directory / "MANIFEST.toml"
    try:
        document = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"Invalid plugin manifest {manifest_path}: {exc}") from exc
    plugin = document.get("plugin", {})
    features = document.get("features", {})
    required = ("name", "display_name", "file_extension")
    missing = [key for key in required if not plugin.get(key)]
    if missing:
        raise ValueError(f"Plugin manifest {manifest_path} is missing: {', '.join(missing)}")
    templates = sorted(directory.glob("template.*.tmpl"))
    if len(templates) != 1:
        raise ValueError(f"Plugin {plugin['name']} must contain exactly one template.*.tmpl")
    extension = str(plugin["file_extension"])
    if not extension.startswith("."):
        extension = f".{extension}"
    supported = tuple(
        key for key in ("enums", "allOf", "oneOf", "anyOf", "nullable", "readOnly", "writeOnly")
        if bool(features.get(key, False))
    )
    imports_template = directory / "imports.go.tmpl"
    return PluginManifest(
        name=str(plugin["name"]),
        display_name=str(plugin["display_name"]),
        file_extension=extension,
        mime_type=str(plugin.get("mime_type", "text/plain")),
        default_outdir=str(plugin.get("default_outdir", plugin["name"])),
        output_filename_template=str(plugin.get("output_filename_template", "{name}" + extension)),
        package_name_default=str(plugin.get("package_name_default", "types")),
        supports=supported,
        format_hints=tuple(str(value) for value in features.get("format_hints", [])),
        imports={str(key): str(value) for key, value in document.get("imports", {}).items()},
        directory=directory,
        template_path=templates[0],
        imports_template_path=imports_template if imports_template.is_file() else None,
    )


def discover_plugins(generators_dir: Path = DEFAULT_GENERATORS_DIR) -> dict[str, PluginManifest]:
    directory = Path(generators_dir).expanduser().resolve()
    if not directory.is_dir():
        raise ValueError(f"Generators directory does not exist: {directory}")
    plugins: dict[str, PluginManifest] = {}
    for child in sorted(directory.iterdir()):
        if not child.is_dir() or not (child / "MANIFEST.toml").is_file():
            continue
        manifest = _load_manifest(child)
        if manifest.name in plugins:
            raise ValueError(f"Duplicate plugin name: {manifest.name}")
        plugins[manifest.name] = manifest
    return plugins


LANGUAGE_RENDERERS: dict[str, PluginManifest] = discover_plugins()
_ACTIVE_RENDERERS = dict(LANGUAGE_RENDERERS)


_TOKEN_RE = re.compile(r"\{\{(?P<trim_l>-)?\s*(?P<body>.+?)\s*(?P<trim_r>-)?\}\}", re.DOTALL)


def _lookup(context: Any, path: str) -> Any:
    if path == ".":
        return context
    current = context
    for part in path.lstrip(".").split("."):
        if not part:
            continue
        if isinstance(current, Mapping):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
    return current


def _truthy(value: Any) -> bool:
    return bool(value)


def _matching_end(tokens: list[tuple[int, str]], start: int) -> tuple[int, int | None]:
    """Find matching {{end}} for a block starting at token index start."""
    depth = 0
    else_idx: int | None = None
    for i in range(start + 1, len(tokens)):
        _, body = tokens[i]
        stripped = body.strip()
        if stripped.startswith("if ") or stripped.startswith("range "):
            depth += 1
        elif stripped == "end":
            if depth == 0:
                return i, else_idx
            depth -= 1
        elif stripped == "else" and depth == 0:
            else_idx = i
    raise TemplateError(f"Unclosed block: {tokens[start]!r}")


def _render_tokens(tokens: list[tuple[int, str]], context: Any, root: Mapping[str, Any]) -> str:
    output: list[str] = []
    i = 0
    while i < len(tokens):
        kind, body = tokens[i]
        stripped = body.strip()
        if kind == 0:  # text
            output.append(body)
        elif stripped.startswith("range "):
            end, else_idx = _matching_end(tokens, i)
            values = _lookup(context, stripped[6:].strip()) or []
            inner_tokens = tokens[i + 1:end]
            if values:
                for item in values:
                    output.append(_render_tokens(inner_tokens, item, root))
            elif else_idx is not None:
                output.append(_render_tokens(tokens[else_idx + 1:end], context, root))
            i = end + 1
        elif stripped.startswith("if "):
            end, else_idx = _matching_end(tokens, i)
            value = _lookup(context, stripped[3:].strip())
            if _truthy(value):
                branch = tokens[i + 1:else_idx] if else_idx is not None else tokens[i + 1:end]
                output.append(_render_tokens(branch, context, root))
            elif else_idx is not None:
                output.append(_render_tokens(tokens[else_idx + 1:end], context, root))
            i = end
        elif stripped in ("else", "end"):
            pass
        else:
            value = _lookup(context, body)
            if value is None and context is not root:
                value = _lookup(root, body)
            output.append("" if value is None else str(value))
        i += 1
    return "".join(output)


def _tokenize(template: str) -> list[tuple[int, str]]:
    """Tokenize: 0=text, 1=action. Tracks {{ }} bodies."""
    tokens: list[tuple[int, str]] = []
    last_end = 0
    for m in _TOKEN_RE.finditer(template):
        text = template[last_end:m.start()]
        if text:
            tokens.append((0, text))
        tokens.append((1, m.group("body").strip()))
        last_end = m.end()
    remainder = template[last_end:]
    if remainder:
        tokens.append((0, remainder))
    return tokens


def _render_template(template: str, context: Mapping[str, Any]) -> str:
    return _render_tokens(_tokenize(template), context, context)


def set_plugins(plugins: dict[str, PluginManifest]) -> None:
    _ACTIVE_RENDERERS.clear()
    _ACTIVE_RENDERERS.update(plugins)


def render(plugin_name: str, context: dict[str, Any]) -> str:
    try:
        plugin = _ACTIVE_RENDERERS[plugin_name]
    except KeyError as exc:
        raise ValueError(f"Unknown generator plugin: {plugin_name}") from exc
    values = dict(context)
    values.setdefault("PackageName", plugin.package_name_default)
    imports_str = ""
    if plugin.imports_template_path:
        imports_str = _render_template(plugin.imports_template_path.read_text(encoding="utf-8"), values)
    values["Imports"] = imports_str.rstrip()
    result = _render_template(plugin.template_path.read_text(encoding="utf-8"), values)
    return result.rstrip() + "\n"
