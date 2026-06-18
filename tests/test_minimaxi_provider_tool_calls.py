"""Tests for minimaxi provider's OpenAI-compatible tool-call streaming parser.

The minimaxi provider exposes a chat-completions-compatible streaming
endpoint but its prior implementation only consumed ``delta.content``
and silently dropped any ``delta.tool_calls`` the model emitted.  This
test pins down the accumulation and finalization helpers so that a
Write/Edit/Read tool call surfaced through the OpenAI tool-calls
channel is reconstructed into the ``{id, name, input}`` shape the
engine expects.
"""
from __future__ import annotations

from onecode.models.providers.minimaxi_provider import (
    _accumulate_tool_call_delta,
    _finalize_stream_tool_calls,
)


def _accumulate_all(per_index: list[dict]) -> dict[int, dict]:
    """Replay a sequence of OpenAI tool-call deltas through the accumulator.

    The OpenAI streaming protocol sends successive deltas with the
    same ``index`` for a single tool call, so the dict key here is
    each delta's own ``index`` field — not a synthetic one.
    """
    slots: dict[int, dict] = {}
    for tcd in per_index:
        idx = tcd.get("index", 0)
        slot = slots.setdefault(idx, {"id": "", "name": "", "arguments": ""})
        _accumulate_tool_call_delta(slot, tcd)
    return slots


def test_write_tool_call_across_deltas():
    """A Write call streamed as multiple deltas should be reconstructed."""
    deltas = [
        {"index": 0, "id": "call_abc", "function": {"name": "Write", "arguments": ""}},
        {"index": 0, "function": {"arguments": '{"path":'}},
        {"index": 0, "function": {"arguments": ' "foo.py",'}},
        {"index": 0, "function": {"arguments": ' "content": "print(\\"hi\\")"}'}},
    ]
    slots = _accumulate_all(deltas)
    tool_uses = _finalize_stream_tool_calls(slots)
    assert len(tool_uses) == 1
    assert tool_uses[0]["name"] == "Write"
    assert tool_uses[0]["id"] == "call_abc"
    assert tool_uses[0]["input"] == {
        "path": "foo.py",
        "content": 'print("hi")',
    }


def test_multiple_tool_calls_in_one_turn():
    """Two parallel tool calls keyed by different index slots."""
    deltas = [
        {"index": 0, "id": "call_1", "function": {"name": "Read", "arguments": '{"path": "a.py"}'}},
        {"index": 1, "id": "call_2", "function": {"name": "Bash", "arguments": '{"command": "ls"}'}},
    ]
    slots = _accumulate_all(deltas)
    tool_uses = _finalize_stream_tool_calls(slots)
    assert [tu["name"] for tu in tool_uses] == ["Read", "Bash"]
    assert tool_uses[0]["input"] == {"path": "a.py"}
    assert tool_uses[1]["input"] == {"command": "ls"}


def test_incomplete_delta_without_name_is_dropped():
    """Deltas with no name (truncated stream) must not produce a tool_use."""
    deltas = [
        {"index": 0, "function": {"arguments": '{"path":'}},  # no id, no name
    ]
    slots = _accumulate_all(deltas)
    assert _finalize_stream_tool_calls(slots) == []


def test_malformed_arguments_fall_back_to_raw():
    """Non-JSON arguments are preserved as ``{"raw": ...}``."""
    deltas = [
        {"index": 0, "id": "call_x", "function": {"name": "Bash", "arguments": "this is not json"}},
    ]
    slots = _accumulate_all(deltas)
    [tool_use] = _finalize_stream_tool_calls(slots)
    assert tool_use["input"] == {"raw": "this is not json"}


def test_arguments_parsed_to_dict_only_when_object():
    """A JSON array (not an object) should also be wrapped in ``{"raw": ...}``."""
    deltas = [
        {"index": 0, "id": "call_y", "function": {"name": "Bash", "arguments": '["a", "b"]'}},
    ]
    slots = _accumulate_all(deltas)
    [tool_use] = _finalize_stream_tool_calls(slots)
    assert tool_use["input"] == {"raw": ["a", "b"]}


def test_empty_stream_yields_no_tool_calls():
    assert _finalize_stream_tool_calls({}) == []
