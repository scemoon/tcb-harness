"""Tests for the TUI no-print guard.

These tests pin down the contract of ``scripts/check_tui_no_print.py``:

* module-level / function-body / method-body ``print`` are violations
* ``if __name__ == "__main__":``-guarded ``print`` is allowed
* commented-out ``print`` is allowed
* string literals and docstrings that contain the substring ``print(`` are
  ignored
* ``builtins.print(...)`` is also flagged
* a file that declares the self-check sentinel is fully exempt
* the real ``tui/ansi/`` tree scans clean
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_tui_no_print.py"
ANSI_DIR = REPO_ROOT / "tui" / "ansi"


def _write(tmp_path: Path, name: str, source: str) -> Path:
    f = tmp_path / name
    f.write_text(textwrap.dedent(source))
    return f


def _scan_source(source: str, tmp_path: Path) -> list:
    """Import the guard and run it against a single temp file."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        from check_tui_no_print import scan_file

        return scan_file(_write(tmp_path, "case.py", source))
    finally:
        sys.path.pop(0)


def test_module_level_print_is_violation(tmp_path):
    violations = _scan_source('print("hello")\n', tmp_path)
    assert len(violations) == 1
    assert "bare print()" in violations[0].reason


def test_function_body_print_is_violation(tmp_path):
    src = (
        "def f():\n"
        "    print('x')\n"
    )
    violations = _scan_source(src, tmp_path)
    assert len(violations) == 1
    assert violations[0].lineno == 2


def test_class_method_print_is_violation(tmp_path):
    src = (
        "class C:\n"
        "    def m(self):\n"
        "        print('x')\n"
    )
    violations = _scan_source(src, tmp_path)
    assert len(violations) == 1


def test_print_inside_main_guard_is_allowed(tmp_path):
    src = (
        'if __name__ == "__main__":\n'
        '    print("ok")\n'
    )
    assert _scan_source(src, tmp_path) == []


def test_print_nested_inside_main_guard_is_allowed(tmp_path):
    src = (
        'def helper():\n'
        '    print("nope")\n'
        '\n'
        'if __name__ == "__main__":\n'
        '    helper()\n'
    )
    violations = _scan_source(src, tmp_path)
    assert len(violations) == 1
    assert violations[0].lineno == 2


def test_commented_print_is_allowed(tmp_path):
    assert _scan_source("# print('nope')\n", tmp_path) == []


def test_docstring_containing_print_is_allowed(tmp_path):
    src = '"""see print() example."""\n'
    assert _scan_source(src, tmp_path) == []


def test_string_literal_containing_print_is_allowed(tmp_path):
    src = 'x = "print() is forbidden"\n'
    assert _scan_source(src, tmp_path) == []


def test_builtins_print_attribute_call_is_violation(tmp_path):
    src = (
        "import builtins\n"
        "builtins.print('x')\n"
    )
    violations = _scan_source(src, tmp_path)
    assert len(violations) == 1


def test_self_check_marker_file_is_exempt(tmp_path):
    src = (
        "__tui_no_print_self_check__ = True\n"
        "print('x')\n"
    )
    assert _scan_source(src, tmp_path) == []


def test_syntax_error_file_is_reported_as_violation(tmp_path):
    f = _write(tmp_path, "bad.py", "def f(:\n")
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        from check_tui_no_print import scan_file

        violations = scan_file(f)
    finally:
        sys.path.pop(0)
    assert len(violations) == 1
    assert "syntax error" in violations[0].reason


def test_real_tui_ansi_directory_is_clean():
    """The actual production tree must not contain bare prints."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"guard failed on real tree:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "clean" in result.stdout


def test_guard_self_test_subcommand_succeeds():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--self-test"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"self-test failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "self-test OK" in result.stdout
    assert result.stdout.count("[PASS]") == 9


def test_smoke_injecting_print_makes_guard_fail(tmp_path):
    """Inject a violation into a copy of tui/ansi/ and confirm exit 1."""
    fake = tmp_path / "tui" / "ansi"
    fake.mkdir(parents=True)
    (fake / "_evil.py").write_text("print('debug')\n")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(fake)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 1
    assert "_evil.py:1" in result.stderr
    assert "violation" in result.stderr.lower()
