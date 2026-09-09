"""Tests for the ToolCall widget's read-card expansion logic.

Verifies:
- Small read results (<= 5000 chars) auto-expand so chunked-read content is
  visible without clicking.
- Large read results stay collapsed (ViewMore / header click still available).
- Empty / diff / multi-block content is measured correctly.
"""

from __future__ import annotations

from tui.widgets.tool_call import (
    _READ_AUTO_EXPAND_CHARS,
    _should_expand_read,
    _tool_content_chars,
)


def _tool_call(text: str, kind: str = "read") -> dict:
    return {
        "sessionUpdate": "tool_call",
        "toolCallId": "read-1",
        "title": "Read: foo.ts",
        "kind": kind,
        "status": "completed",
        "content": [
            {
                "type": "content",
                "content": {"type": "text", "text": text},
            }
        ] if text else [],
    }


class TestReadCardExpansion:
    def test_small_read_should_expand(self):
        assert _should_expand_read(_tool_call("const x = 1;")) is True

    def test_read_at_threshold_expands(self):
        assert _should_expand_read(_tool_call("x" * _READ_AUTO_EXPAND_CHARS)) is True

    def test_large_read_stays_collapsed(self):
        assert _should_expand_read(_tool_call("x" * (_READ_AUTO_EXPAND_CHARS + 1))) is False

    def test_chunked_read_expands(self):
        chunk = "\n".join(f"line {i}" for i in range(200))
        assert _should_expand_read(_tool_call(chunk)) is True

    def test_empty_read_expands(self):
        assert _should_expand_read(_tool_call("")) is True


class TestToolContentChars:
    def test_counts_text_blocks(self):
        content = [
            {"type": "content", "content": {"type": "text", "text": "abc"}},
            {"type": "content", "content": {"type": "text", "text": "def"}},
        ]
        assert _tool_content_chars(content) == 6

    def test_counts_diff_blocks(self):
        content = [
            {
                "type": "diff",
                "path": "a.ts",
                "oldText": "old",
                "newText": "newtext",
            }
        ]
        assert _tool_content_chars(content) == 10

    def test_ignores_non_content_blocks(self):
        content = [
            {"type": "terminal", "terminalId": "t1"},
            {"type": "content", "content": {"type": "text", "text": "x"}},
        ]
        assert _tool_content_chars(content) == 1

    def test_empty_content(self):
        assert _tool_content_chars([]) == 0
