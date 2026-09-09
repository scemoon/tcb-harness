#!/usr/bin/env python3
"""retrofit_labels.py — Brownfield migration tool.

Scans existing source code for TODO/FIXME/XXX/HACK/REQ/AS-A comments,
extracts them as candidate requirements, prompts the user to confirm or
skip each candidate, and emits a spec-delta.md per confirmed candidate.
Tree-sitter enriches candidates with structural context when available.

Usage:
  retrofit_labels.py [--project-root PATH]
                     [--extensions .py,.ts,.js,.java,.go]
                     [--output-dir PATH]
                     [--batch]
                     [--from-source PATH]
                     [--ast-level none|function|class|module]
                     [--use-ast | --no-ast]
                     [--include-imports]
                     [--include-signatures | --no-include-signatures]
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional


PATTERN = re.compile(r"(?:TODO|FIXME|XXX|HACK|REQ|AS-A):?\s*(.*)")
FR_PREFIX = "BE-FR-"
EARS_PREFIX = "the system shall"
FUNCTION_NODES = {"function_definition", "function_declaration", "method_definition", "method_declaration"}
CLASS_NODES = {"class_definition", "class_declaration", "interface_declaration", "enum_declaration"}
IMPORT_NODES = {"import_statement", "import_from_statement", "import_declaration", "package_clause"}
LANGUAGE_MODULES = {
    ".py": ("tree_sitter_python", "python"),
    ".js": ("tree_sitter_javascript", "javascript"),
    ".jsx": ("tree_sitter_javascript", "javascript"),
    ".ts": ("tree_sitter_typescript", "typescript"),
    ".tsx": ("tree_sitter_typescript", "tsx"),
    ".java": ("tree_sitter_java", "java"),
    ".go": ("tree_sitter_go", "go"),
}


@dataclass
class Definition:
    kind: str
    name: str
    signature: str = ""
    decorators: list[str] = field(default_factory=list)
    docstring: str = ""
    bases: list[str] = field(default_factory=list)
    start_line: int = 0
    end_line: int = 0
    start_byte: int = 0
    end_byte: int = 0


@dataclass
class SourceContext:
    module: str
    imports: list[str] = field(default_factory=list)
    functions: list[Definition] = field(default_factory=list)
    classes: list[Definition] = field(default_factory=list)
    ast_used: bool = False


@dataclass
class Candidate:
    file: Path
    line: int
    raw: str
    tag: str
    text: str
    ears: str
    context: Optional[Definition] = None
    class_context: Optional[Definition] = None
    source_context: Optional[SourceContext] = None
    snippet: str = ""
    ast_level: str = "function"
    include_imports: bool = False
    include_signatures: bool = True

    @property
    def rel_path(self) -> str:
        try:
            return str(self.file.resolve().relative_to(Path.cwd().resolve()))
        except ValueError:
            return str(self.file)


class TreeSitterAnalyzer:
    def __init__(self) -> None:
        self._languages: dict[str, Any] = {}
        self._parser_class: Any = None
        try:
            from tree_sitter import Language, Parser

            self._language_class = Language
            self._parser_class = Parser
        except ImportError:
            self._language_class = None

    @property
    def available(self) -> bool:
        return self._parser_class is not None

    def _language(self, suffix: str) -> Any:
        if suffix in self._languages:
            return self._languages[suffix]
        module_info = LANGUAGE_MODULES.get(suffix)
        if not module_info or not self.available:
            return None
        module_name, dialect = module_info
        try:
            module = __import__(module_name)
            factory = getattr(module, "language", None)
            if suffix in {".ts", ".tsx"}:
                factory = getattr(module, f"language_{dialect}", factory)
            language = factory() if factory else None
            if language is not None and self._language_class is not None:
                try:
                    language = self._language_class(language)
                except (TypeError, ValueError):
                    pass
            self._languages[suffix] = language
            return language
        except (ImportError, AttributeError, TypeError, ValueError):
            self._languages[suffix] = None
            return None

    def _parser(self, suffix: str) -> Any:
        language = self._language(suffix)
        if language is None:
            return None
        try:
            return self._parser_class(language)
        except TypeError:
            parser = self._parser_class()
            try:
                parser.language = language
            except (AttributeError, TypeError):
                parser.set_language(language)
            return parser

    def analyze(self, path: Path, source: bytes) -> SourceContext:
        result = SourceContext(module=path.stem)
        parser = self._parser(path.suffix.lower())
        if parser is None:
            return result
        try:
            root = parser.parse(source).root_node
        except (AttributeError, TypeError, ValueError):
            return result
        result.ast_used = True
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type in IMPORT_NODES:
                value = _node_text(node, source).strip()
                if value and value not in result.imports:
                    result.imports.append(value)
            if node.type in FUNCTION_NODES:
                result.functions.append(self._function(node, source))
            elif node.type in CLASS_NODES:
                result.classes.append(self._class(node, source))
            stack.extend(reversed(node.children))
        return result

    def _function(self, node: Any, source: bytes) -> Definition:
        name_node = node.child_by_field_name("name")
        name = _node_text(name_node, source).strip() if name_node else "<anonymous>"
        body = node.child_by_field_name("body")
        signature_end = body.start_byte if body else node.end_byte
        signature = source[node.start_byte:signature_end].decode("utf-8", "replace").strip().rstrip("{: ")
        decorators: list[str] = []
        parent = node.parent
        if parent is not None and parent.type in {"decorated_definition", "decorator"}:
            decorators = [
                _node_text(child, source).strip()
                for child in parent.children
                if child.type == "decorator"
            ]
        return Definition(
            kind="function",
            name=name,
            signature=" ".join(signature.split()),
            decorators=decorators,
            docstring=_extract_docstring(body, source),
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_byte=node.start_byte,
            end_byte=node.end_byte,
        )

    def _class(self, node: Any, source: bytes) -> Definition:
        name_node = node.child_by_field_name("name")
        name = _node_text(name_node, source).strip() if name_node else "<anonymous>"
        bases_node = node.child_by_field_name("superclasses") or node.child_by_field_name("interfaces")
        bases = []
        if bases_node is not None:
            bases = [
                _node_text(child, source).strip()
                for child in bases_node.named_children
                if _node_text(child, source).strip()
            ]
        body = node.child_by_field_name("body")
        return Definition(
            kind="class",
            name=name,
            bases=bases,
            docstring=_extract_docstring(body, source),
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_byte=node.start_byte,
            end_byte=node.end_byte,
        )


def _node_text(node: Any, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _extract_docstring(body: Any, source: bytes) -> str:
    if body is None:
        return ""
    named = list(body.named_children)
    if not named:
        return ""
    first = named[0]
    expression = first.named_children[0] if first.type == "expression_statement" and first.named_children else first
    if expression.type not in {"string", "string_literal"}:
        return ""
    text = _node_text(expression, source).strip()
    return re.sub(r"^(?:[rubfRUBF]*)(?:'''|\"\"\"|'|\")|(?:'''|\"\"\"|'|\")$", "", text).strip()


def _iter_source_files(root: Path, extensions: list[str], from_source: Optional[Path]) -> Iterator[Path]:
    base = (root / from_source) if from_source else root
    if not base.exists():
        return
    ext_set = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions}
    for path in base.rglob("*"):
        if path.is_file() and path.suffix.lower() in ext_set:
            yield path


def _strip_comment(text: str) -> str:
    for prefix in ("#", "//", "--", "/*", "*"):
        if text.lstrip().startswith(prefix):
            text = text.lstrip()[len(prefix):]
            break
    return text.strip().rstrip("*/").strip()


def _scope_phrase(name: str) -> str:
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    words = re.sub(r"[_\-.]+", " ", words).strip().lower()
    return words


def _to_ears(text: str, scope: str = "") -> str:
    stripped = text.strip()
    if not stripped:
        return stripped
    lowered = stripped.lower()
    if lowered.startswith(EARS_PREFIX):
        requirement = stripped if stripped.endswith(".") else f"{stripped}."
    else:
        rest = stripped[0].lower() + stripped[1:]
        requirement = f"{EARS_PREFIX} {rest.rstrip('.')} .".replace(" .", ".")
    if scope:
        return f"While {_scope_phrase(scope)}, {requirement}"
    return requirement


def _smallest_enclosing(definitions: list[Definition], line: int) -> Optional[Definition]:
    matches = [item for item in definitions if item.start_line <= line <= item.end_line]
    return min(matches, key=lambda item: item.end_line - item.start_line, default=None)


def _snippet(lines: list[str], line: int, context: Optional[Definition]) -> str:
    start = max(1, line - 2)
    end = min(len(lines), line + 2)
    if context:
        start = max(context.start_line, start)
        end = min(context.end_line, end)
    width = len(str(end))
    return "\n".join(f"{number:>{width}} | {lines[number - 1]}" for number in range(start, end + 1))


def _next_fr_id(output_dir: Path) -> str:
    if not output_dir.exists():
        return f"{FR_PREFIX}001"
    nums: list[int] = []
    for file in output_dir.glob("spec-delta-*.md"):
        match = re.search(r"spec-delta-(\d+)", file.name)
        if match:
            nums.append(int(match.group(1)))
    return f"{FR_PREFIX}{(max(nums) if nums else 0) + 1:03d}"


def scan(
    root: Path,
    extensions: list[str],
    from_source: Optional[Path],
    use_ast: bool = True,
    ast_level: str = "function",
    include_imports: bool = False,
    include_signatures: bool = True,
) -> list[Candidate]:
    found: list[Candidate] = []
    analyzer = TreeSitterAnalyzer() if use_ast else None
    for path in _iter_source_files(root, extensions, from_source):
        try:
            source = path.read_bytes()
            lines = source.decode("utf-8", "replace").splitlines()
        except OSError:
            continue
        source_context = analyzer.analyze(path, source) if analyzer else SourceContext(module=path.stem)
        for idx, line in enumerate(lines, start=1):
            for match in PATTERN.finditer(line):
                raw = match.group(1).strip()
                if not raw:
                    continue
                tag = line[match.start():match.end()].split(":", 1)[0].split()[0]
                cleaned = _strip_comment(raw)
                function_context = _smallest_enclosing(source_context.functions, idx)
                class_context = _smallest_enclosing(source_context.classes, idx)
                if ast_level == "function":
                    context = function_context or class_context
                elif ast_level == "class":
                    context = class_context
                elif ast_level == "module":
                    context = Definition("module", source_context.module, start_line=1, end_line=len(lines))
                else:
                    context = None
                found.append(
                    Candidate(
                        file=path,
                        line=idx,
                        raw=line.strip(),
                        tag=tag,
                        text=cleaned,
                        ears=_to_ears(cleaned, context.name if context else ""),
                        context=context,
                        class_context=class_context,
                        source_context=source_context,
                        snippet=_snippet(lines, idx, context),
                        ast_level=ast_level,
                        include_imports=include_imports,
                        include_signatures=include_signatures,
                    )
                )
    return found


def _confirm(prompt: str, batch: bool) -> bool:
    if batch:
        return True
    try:
        answer = input(f"{prompt} [y/N/q]: ").strip().lower()
    except EOFError:
        return False
    if answer in ("q", "quit"):
        raise KeyboardInterrupt
    return answer in ("y", "yes")


def _markdown_value(value: str) -> str:
    return value.replace("`", "\\`").replace("\n", " ")


def render_spec_delta(fr_id: str, candidate: Candidate) -> str:
    title = candidate.text[:80].rstrip(".").strip() or candidate.tag
    context = candidate.context
    ast_used = bool(candidate.source_context and candidate.source_context.ast_used)
    parts = [
        "---",
        f"id: {fr_id}",
        f"title: {title}",
        "status: draft",
        f"source: {candidate.rel_path}:{candidate.line}",
        f"tag: {candidate.tag}",
        f"analysis: {'tree-sitter' if ast_used else 'regex'}",
    ]
    if context:
        parts.extend((f"scope: {context.kind}", f"scope_name: {context.name}"))
    parts.extend(("---", "", f"# {fr_id}: {title}", ""))
    parts.extend(
        (
            f"**Source**: `{candidate.rel_path}:{candidate.line}`",
            f"**Original**: `{_markdown_value(candidate.raw)}`",
            f"**Analysis**: {'tree-sitter AST' if ast_used else 'regex fallback'}",
        )
    )
    if context:
        parts.append(f"**Scope**: {context.kind} `{context.name}`")
    if candidate.class_context and candidate.class_context is not context:
        parts.append(f"**Enclosing class**: `{candidate.class_context.name}`")
    parts.extend(("", "## Requirement (EARS)", "", candidate.ears, "", "## Source Context", ""))
    if context and candidate.include_signatures and context.signature:
        parts.extend(("### Signature", "", f"```{candidate.file.suffix.lstrip('.')}", context.signature, "```", ""))
    if context and context.decorators:
        parts.extend(("### Decorators", "", *(f"- `{_markdown_value(item)}`" for item in context.decorators), ""))
    if context and context.bases:
        parts.extend(("### Base Classes", "", *(f"- `{_markdown_value(item)}`" for item in context.bases), ""))
    if context and context.docstring:
        parts.extend(("### Docstring", "", context.docstring, ""))
    if candidate.include_imports and candidate.source_context and candidate.source_context.imports:
        parts.extend(("### Imports", "", f"```{candidate.file.suffix.lstrip('.')}", *candidate.source_context.imports, "```", ""))
    parts.extend(("### Code Snippet", "", f"```{candidate.file.suffix.lstrip('.')}", candidate.snippet, "```", ""))
    if candidate.source_context and candidate.ast_level == "module":
        if candidate.source_context.classes:
            parts.extend(("### Classes", "", *(f"- `{item.name}`" for item in candidate.source_context.classes), ""))
        if candidate.source_context.functions:
            parts.extend(("### Functions", "", *(f"- `{item.name}`" for item in candidate.source_context.functions), ""))
    parts.extend(("## Rationale", "", "Recovered from source-level comment during brownfield retrofit.", ""))
    return "\n".join(parts)


def _write_delta(output_dir: Path, fr_id: str, body: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    number = int(fr_id[len(FR_PREFIX):])
    output = output_dir / f"spec-delta-{number:03d}.md"
    output.write_text(body, encoding="utf-8")
    return output


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Retrofit source-level comments into spec-delta requirements.")
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument(
        "--extensions",
        default=".py,.ts,.tsx,.js,.jsx,.java,.go",
        help="Comma-separated extension list (default: .py,.ts,.tsx,.js,.jsx,.java,.go)",
    )
    parser.add_argument("--output-dir", default="aidlc/openspec/changes/retrofit/", type=Path)
    parser.add_argument("--batch", action="store_true", help="Auto-confirm all candidates without prompting.")
    parser.add_argument("--from-source", default=None, type=Path, help="Scan only this subdirectory of --project-root.")
    parser.add_argument(
        "--ast-level",
        choices=("none", "function", "class", "module"),
        default="function",
        help="Structural scope included in requirements and output (default: function).",
    )
    ast_group = parser.add_mutually_exclusive_group()
    ast_group.add_argument("--use-ast", dest="use_ast", action="store_true", help="Use tree-sitter when available (default).")
    ast_group.add_argument("--no-ast", dest="use_ast", action="store_false", help="Disable tree-sitter analysis.")
    parser.set_defaults(use_ast=True)
    parser.add_argument("--include-imports", action="store_true", help="Include module imports in output.")
    parser.add_argument(
        "--include-signatures",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include enclosing function signatures in output (default: true).",
    )
    args = parser.parse_args(argv)

    root = args.project_root.resolve()
    if not root.exists():
        print(f"project root does not exist: {root}", file=sys.stderr)
        return 2

    extensions = [extension.strip() for extension in args.extensions.split(",") if extension.strip()]
    output_dir = (root / args.output_dir).resolve() if not args.output_dir.is_absolute() else args.output_dir.resolve()
    candidates = scan(
        root,
        extensions,
        args.from_source,
        use_ast=args.use_ast,
        ast_level=args.ast_level,
        include_imports=args.include_imports,
        include_signatures=args.include_signatures,
    )
    if not candidates:
        print("No candidate comments found.", file=sys.stderr)
        return 0

    written: list[Path] = []
    try:
        for candidate in candidates:
            scope = f" in {candidate.context.kind} {candidate.context.name}" if candidate.context else ""
            header = f"[{candidate.rel_path}:{candidate.line}] ({candidate.tag}) {candidate.text}{scope}"
            if _confirm(header, args.batch):
                fr_id = _next_fr_id(output_dir)
                output = _write_delta(output_dir, fr_id, render_spec_delta(fr_id, candidate))
                written.append(output)
                try:
                    shown = output.relative_to(root)
                except ValueError:
                    shown = output
                print(f"  wrote {shown}", file=sys.stderr)
    except KeyboardInterrupt:
        print("\nAborted by user.", file=sys.stderr)

    print(f"\n{len(written)} spec-delta file(s) written to {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
