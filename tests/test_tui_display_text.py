"""Tests for the TUI display-text formatter.

The formatter converts internal tool-result JSON to a short user-facing
string.  Task / Todo tools (TaskCreate, TaskUpdate, …) return verbose
state objects that clutter the chat view; the formatter collapses them
to ``"✓ updated"`` instead of re-printing the full task JSON.
"""

from __future__ import annotations

import json

from cdha.agent.cdh_agent_acp import _format_tui_display_text


class TestFormatTuiDisplayText:
    def test_empty_returns_empty(self):
        assert _format_tui_display_text("") == ""

    def test_non_json_returns_as_is(self):
        assert _format_tui_display_text("plain text") == "plain text"

    def test_error_field_returns_error_message(self):
        result = json.dumps({"error": "file not found"})
        assert _format_tui_display_text(result) == "file not found"

    def test_success_with_path_shows_checkmark(self):
        result = json.dumps({"success": True, "path": "/tmp/foo.txt"})
        assert _format_tui_display_text(result) == "✓ /tmp/foo.txt"

    def test_success_with_only_success_returns_done(self):
        result = json.dumps({"success": True})
        assert _format_tui_display_text(result) == "✓ done"

    def test_success_with_extras_returns_compact_json(self):
        result = json.dumps({"success": True, "stdout": "hello"})
        out = _format_tui_display_text(result)
        parsed = json.loads(out)
        assert parsed == {"stdout": "hello"}

    def test_task_update_is_quiet_by_default(self):
        """TaskUpdate verbose result is collapsed to a single line."""
        result = json.dumps({
            "success": True,
            "taskId": "t3",
            "task": {
                "id": "t3",
                "subject": "更新 SPEC.md 文档",
                "status": "completed",
            },
        })
        assert _format_tui_display_text(result, "TaskUpdate") == "✓ updated"

    def test_task_create_is_quiet(self):
        result = json.dumps({
            "task": {"id": "t1", "subject": "Add login page"},
        })
        assert _format_tui_display_text(result, "TaskCreate") == "✓ updated"

    def test_task_list_is_quiet(self):
        result = json.dumps({"tasks": [{"id": "t1", "subject": "x", "status": "pending"}]})
        assert _format_tui_display_text(result, "TaskList") == "✓ updated"

    def test_todo_create_is_quiet(self):
        result = json.dumps({"id": "td-1", "text": "remember milk"})
        assert _format_tui_display_text(result, "TodoCreate") == "✓ updated"

    def test_todo_complete_is_quiet(self):
        result = json.dumps({"success": True, "todo_id": "td-1"})
        assert _format_tui_display_text(result, "TodoComplete") == "✓ updated"

    def test_task_update_error_still_shows_error(self):
        """Errors are not collapsed — the user needs to see them."""
        result = json.dumps({"error": "Task not found"})
        assert _format_tui_display_text(result, "TaskUpdate") == "Task not found"

    def test_non_task_tool_unaffected_by_tool_name(self):
        """Read/Write/Bash should not be affected even if tool_name is passed."""
        result = json.dumps({"success": True, "path": "/tmp/foo.txt"})
        # When a path is present, the success-with-path branch fires
        # before the task-tool check.
        assert _format_tui_display_text(result, "Read") == "✓ /tmp/foo.txt"
