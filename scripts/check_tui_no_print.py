"""Guard: forbid bare print() in TUI production paths.

Background
----------
Debug ``print("TODO DCS")`` calls inside the ANSI escape parser
(``tui/ansi/_ansi.py``) leaked the literal ``P`` onto the terminal at TUI
startup, because the parser runs before the alt-screen buffer is fully
claimed.  This script prevents that class of regression by statically
scanning Python files under ``tui/ansi/`` for any ``print(...)`` call that
would be executed on the production code path.

Rules
-----
A ``print(...)`` call is a **violation** when it appears in code that
runs in production.  Concretely:

* module-level (top-level) ``print``          -> violation
* any class / function / method body ``print`` -> violation
* aliasing via ``from builtins import print`` or attribute access
  ``builtins.print(...)``                   -> violation

A ``print(...)`` call is **allowed** when it is clearly test-only:

* inside an ``if __name__ == "__main__":`` block (any depth)
* inside a file marked with the sentinel constant
  ``__tui_no_print_self_check__ = True`` (this script's own marker, so
  the guard can exercise itself without self-flagging)
* inside a string literal or docstring (these aren't ``Call`` nodes)

The scan uses :mod:`ast` rather than regex to avoid false positives
inside strings, comments, or unrelated identifiers that happen to
contain the substring ``print(``.

Usage
-----
::

    python scripts/check_tui_no_print.py            # exit 0 if clean, 1 if violations
    python scripts/check_tui_no_print.py --self-test  # run the script's own self-checks
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable, Iterator, NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = REPO_ROOT / "tui" / "ansi"

SELF_CHECK_MARKER = "__tui_no_print_self_check__"


class Violation(NamedTuple):
    path: Path
    lineno: int
    col: int
    reason: str

    def render(self) -> str:
        try:
            rel = self.path.relative_to(REPO_ROOT)
        except ValueError:
            rel = self.path
        return f"{rel}:{self.lineno}:{self.col}: {self.reason}"


def _is_print_call(node: ast.AST) -> bool:
    """True if ``node`` is a call to the builtin ``print``."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "print":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "print":
        return True
    return False


def _iter_calls(tree: ast.AST) -> Iterator[ast.Call]:
    """Yield every ``ast.Call`` node in ``tree``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def _in_main_guard(call: ast.Call) -> bool:
    """True if ``call`` is nested inside an ``if __name__ == "__main__":`` block."""
    for parent in ast.walk(ast.Module(body=[call])):
        pass

    for ancestor in ast.walk(_AncestorVisitor.build(call)):
        if not isinstance(ancestor, ast.If):
            continue
        test = ancestor.test
        if (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
        ):
            return True
    return False


class _AncestorVisitor:
    """Build a synthetic tree where each call knows its enclosing ``if`` block.

    This is a tiny helper: we walk the tree once, tracking the stack of
    ``ast.If`` nodes, then for each call record which ``If`` blocks enclose
    it.  Implemented manually to avoid the overhead of a full parent
    pointer build for what is a single boolean check.
    """

    @classmethod
    def build(cls, target: ast.Call) -> ast.AST:
        """Return the original tree; the real work happens in :func:`_in_main_guard`."""
        return target


def _in_main_guard_v2(tree: ast.Module, call: ast.Call) -> bool:
    """Walk the real tree and detect whether ``call`` is inside a main guard."""
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _if_is_main_guard(node):
            for inner in _walk_including_nested(node):
                if inner is call:
                    return True
    return False


def _if_is_main_guard(node: ast.If) -> bool:
    test = node.test
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
    )


def _walk_including_nested(node: ast.AST) -> Iterator[ast.AST]:
    """Like :func:`ast.walk` but only over ``node`` and its descendants."""
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _walk_including_nested(child)


def _file_has_self_check_marker(tree: ast.Module) -> bool:
    """True if the module assigns the self-check sentinel at module level."""
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == SELF_CHECK_MARKER
        ):
            return True
    return False


def scan_file(path: Path) -> list[Violation]:
    """Return all violations found in ``path``."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [Violation(path, 0, 0, f"could not read file: {exc}")]

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [Violation(path, exc.lineno or 0, exc.offset or 0, f"syntax error: {exc.msg}")]

    violations: list[Violation] = []

    if _file_has_self_check_marker(tree):
        return violations

    for call in _iter_calls(tree):
        if not _is_print_call(call):
            continue
        if _in_main_guard_v2(tree, call):
            continue
        violations.append(
            Violation(
                path,
                call.lineno,
                call.col_offset,
                "bare print() in TUI production path; use logging or move to __main__ guard",
            )
        )

    return violations


def scan_paths(targets: Iterable[Path]) -> list[Violation]:
    """Scan every ``.py`` file under each target directory (or file)."""
    results: list[Violation] = []
    for target in targets:
        if target.is_file():
            results.extend(scan_file(target))
        elif target.is_dir():
            for py in sorted(target.rglob("*.py")):
                results.extend(scan_file(py))
        else:
            print(f"warning: {target} does not exist", file=sys.stderr)
    return results


def _self_test() -> int:
    """Run built-in checks against the guard itself.  Returns exit code."""
    import tempfile
    import textwrap

    cases: list[tuple[str, str, bool]] = [
        (
            "module-level print",
            "print('hello')\n",
            True,
        ),
        (
            "function-body print",
            "def f():\n    print('x')\n",
            True,
        ),
        (
            "class-method print",
            "class C:\n    def m(self):\n        print('x')\n",
            True,
        ),
        (
            "main-guard print",
            textwrap.dedent(
                """\
                if __name__ == "__main__":
                    print("ok")
                """
            ),
            False,
        ),
        (
            "commented print",
            "# print('nope')\n",
            False,
        ),
        (
            "docstring with print(",
            '"""see print() example."""\n',
            False,
        ),
        (
            "string literal with print(",
            'x = "print() is forbidden"\n',
            False,
        ),
        (
            "builtins.print attribute call",
            "import builtins\nbuiltins.print('x')\n",
            True,
        ),
        (
            "self-check marker file",
            f"{SELF_CHECK_MARKER} = True\nprint('x')\n",
            False,
        ),
    ]

    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for label, source, should_flag in cases:
            f = tmpdir / "case.py"
            f.write_text(source)
            found = scan_file(f)
            flagged = bool(found)
            ok = flagged == should_flag
            status = "PASS" if ok else "FAIL"
            print(f"  [{status}] {label}: flagged={flagged} expected={should_flag}")
            if not ok:
                failures += 1
                for v in found:
                    print(f"         {v.render()}")

    return 0 if failures == 0 else 1


def main(argv: list[str]) -> int:
    args = list(argv[1:])

    if "--self-test" in args:
        print("running self-test...")
        rc = _self_test()
        print("self-test", "OK" if rc == 0 else "FAILED")
        return rc

    targets = [DEFAULT_TARGET]
    for raw in args:
        if raw.startswith("--"):
            continue
        targets.append(Path(raw).resolve())

    violations = scan_paths(targets)
    if violations:
        print("TUI no-print guard: violations found:", file=sys.stderr)
        for v in violations:
            print(f"  {v.render()}", file=sys.stderr)
        print(
            f"\n{len(violations)} violation(s). "
            "Move prints into an `if __name__ == \"__main__\":` block, "
            "use logging, or delete them.",
            file=sys.stderr,
        )
        return 1

    print("TUI no-print guard: clean.")
    return 0


__tui_no_print_self_check__ = True


if __name__ == "__main__":
    sys.exit(main(sys.argv))
