"""Tests for the request-hardening done in ``Provider.prepare_messages``
and ``Provider.classify_http_error`` after the upstream HTTP 400 series
that surfaced as ``Provider error (turn 1): upstream error 400``.

The fixes covered here:

1. ``prepare_messages`` strips ``tool`` messages that have neither
   content nor a ``tool_call_id`` (OpenAI-compatible APIs reject these).
2. ``prepare_messages`` coalesces runs of consecutive identical
   ``user`` messages.
3. ``prepare_messages`` caps the combined system-prompt length at
   32 KiB, preserving ``AGENT_CONFIG`` > ``REACT_PHASE`` > most recent
   skills and dropping older skill bodies first.
4. ``classify_http_error`` appends a body excerpt to the generic
   upstream-error message so the user sees the real reason.
5. ``MiniMaxiProvider._pick_default_model`` returns ``MiniMax-M3`` when
   the API key starts with the ``cn-cp-`` plan prefix, and falls back
   to ``MiniMax-M2.7`` otherwise.
"""
from __future__ import annotations

from typing import AsyncIterator

import pytest

from onecode.models.errors import (
    AuthError,
    ContextLengthError,
    ProviderError,
    RateLimitError,
    TransientProviderError,
)
from onecode.models.provider import Message, ModelResponse, Provider, ToolUse
from onecode.models.providers.minimaxi_provider import MiniMaxiProvider


class _ConcreteProvider(Provider):
    """Minimal concrete provider used only to call ``prepare_messages``."""

    name = "_test"

    async def chat(self, messages, model, **kwargs) -> ModelResponse:
        raise NotImplementedError

    async def chat_stream(self, messages, model, **kwargs) -> AsyncIterator[str]:
        raise NotImplementedError
        yield ""


# ── prepare_messages ──────────────────────────────────────────────────


def test_prepare_messages_strips_empty_tool_messages():
    """A tool message with no content and no tool_call_id must be dropped.

    Replays the symptom observed in the production log
    ``minimaxi_20260622_210940_054541.json``.
    """
    msgs = [
        Message("user", "hello"),
        Message("tool", "", name=""),
        Message("tool", "", name="missing"),
        Message("assistant", "ok"),
    ]
    out = _ConcreteProvider().prepare_messages(msgs)
    roles = [m["role"] for m in out]
    assert "tool" not in roles
    assert roles == ["user", "assistant"]


def test_prepare_messages_keeps_tool_with_id_and_content():
    """Tool messages that carry both id and content must NOT be dropped,
    provided they follow an assistant message that emitted a matching
    ``tool_calls.id``."""
    assistant = Message("assistant", "")
    assistant.add_tool_use(ToolUse(id="call_1", name="Bash", input={"command": "ls"}))
    msgs = [
        Message("user", "go"),
        assistant,
        Message("tool", "result text", name="call_1"),
    ]
    out = _ConcreteProvider().prepare_messages(msgs)
    tool_msgs = [m for m in out if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "call_1"
    assert tool_msgs[0]["content"] == "result text"


def test_prepare_messages_drops_tool_with_id_but_empty_content():
    """An id without content is also invalid for OpenAI-compatible APIs."""
    msgs = [Message("tool", "", name="call_orphan")]
    out = _ConcreteProvider().prepare_messages(msgs)
    assert all(m["role"] != "tool" for m in out)


def test_prepare_messages_drops_orphan_tool_after_prose_assistant():
    """A tool message whose ``tool_call_id`` has no preceding
    ``assistant.tool_calls`` must be dropped — the MiniMax gateway
    rejects it with ``(2013) tool call result does not follow tool call``.
    """
    msgs = [
        Message("user", "hi"),
        Message("assistant", "I'll think about it."),
        Message("tool", "some result", name="call_xyz"),
        Message("assistant", "still thinking"),
        Message("user", "ok"),
    ]
    out = _ConcreteProvider().prepare_messages(msgs)
    assert [m["role"] for m in out] == ["user", "assistant", "assistant", "user"]
    assert all(m["role"] != "tool" for m in out)


def test_prepare_messages_keeps_tool_after_tool_use_assistant():
    """Tool messages following an assistant that emitted ``tool_calls``
    with matching ``id`` are preserved."""
    assistant = Message("assistant", "")
    assistant.add_tool_use(ToolUse(id="call_abc", name="Read", input={"path": "foo.py"}))
    msgs = [
        Message("user", "read foo"),
        assistant,
        Message("tool", "file contents", name="call_abc"),
        Message("assistant", "done"),
    ]
    out = _ConcreteProvider().prepare_messages(msgs)
    roles = [m["role"] for m in out]
    assert roles == ["user", "assistant", "tool", "assistant"]
    tool_msg = next(m for m in out if m["role"] == "tool")
    assert tool_msg["tool_call_id"] == "call_abc"
    assert tool_msg["content"] == "file contents"


def test_prepare_messages_drops_only_unmatched_tools_in_mixed_run():
    """When two tool messages follow, only the one whose id matches the
    previous assistant's tool_calls is kept."""
    assistant = Message("assistant", "")
    assistant.add_tool_use(ToolUse(id="call_keep", name="Read", input={"path": "x"}))
    msgs = [
        Message("user", "go"),
        assistant,
        Message("tool", "ok", name="call_keep"),
        Message("tool", "ok", name="call_unknown"),
    ]
    out = _ConcreteProvider().prepare_messages(msgs)
    tool_msgs = [m for m in out if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "call_keep"


def test_prepare_messages_resets_tool_link_after_user_message():
    """A user message between assistant.tool_calls and a tool result
    invalidates the link (the model can no longer be sure which tool
    produced what). The orphan tool is dropped."""
    assistant = Message("assistant", "")
    assistant.add_tool_use(ToolUse(id="call_a", name="Bash", input={"command": "ls"}))
    msgs = [
        assistant,
        Message("user", "actually, never mind"),
        Message("tool", "forgotten result", name="call_a"),
    ]
    out = _ConcreteProvider().prepare_messages(msgs)
    assert all(m["role"] != "tool" for m in out)


def test_prepare_messages_coalesces_consecutive_duplicate_user():
    """Runs of identical user messages are collapsed."""
    msgs = [
        Message("user", "continue"),
        Message("user", "continue"),
        Message("user", "continue"),
        Message("assistant", "ok"),
        Message("user", "continue"),
    ]
    out = _ConcreteProvider().prepare_messages(msgs)
    user_msgs = [m for m in out if m["role"] == "user"]
    assert len(user_msgs) == 2
    assert user_msgs[0]["content"] == "continue"
    assert user_msgs[1]["content"] == "continue"


def test_prepare_messages_keeps_distinct_user_messages():
    """Distinct user content must not be coalesced."""
    msgs = [
        Message("user", "first"),
        Message("user", "second"),
    ]
    out = _ConcreteProvider().prepare_messages(msgs)
    assert [m["content"] for m in out if m["role"] == "user"] == ["first", "second"]


def test_prepare_messages_caps_system_at_32k_keeps_agent_config():
    """A huge system-prompt blob must be truncated to <= 32 KiB and the
    ``AGENT_CONFIG`` block must always be preserved."""
    huge_skill = "<!-- SKILL:x -->\n" + ("filler " * 5000)  # ~30 KiB
    msgs = [
        Message("system", "<!-- AGENT_CONFIG -->\n" + "core " * 10),
        Message("system", huge_skill),
        Message("system", "<!-- REACT_PHASE -->\nreact"),
        Message("user", "hi"),
    ]
    out = _ConcreteProvider().prepare_messages(msgs)
    sys_msgs = [m for m in out if m["role"] == "system"]
    assert len(sys_msgs) == 1
    sys_content = sys_msgs[0]["content"]
    assert "<!-- AGENT_CONFIG -->" in sys_content
    assert len(sys_content.encode("utf-8")) <= 32 * 1024


def test_prepare_messages_caps_system_drops_oldest_skill_first():
    """When total system > 32 KiB the oldest skill body should be dropped."""
    old_skill = "<!-- SKILL:old -->\n" + ("old " * 5000)
    new_skill = "<!-- SKILL:new -->\n" + ("new " * 5000)
    msgs = [
        Message("system", "<!-- AGENT_CONFIG -->\ncore"),
        Message("system", old_skill),
        Message("system", new_skill),
        Message("user", "hi"),
    ]
    out = _ConcreteProvider().prepare_messages(msgs)
    sys_content = out[0]["content"]
    assert "<!-- AGENT_CONFIG -->" in sys_content
    assert "<!-- SKILL:new -->" in sys_content
    assert "<!-- SKILL:old -->" not in sys_content


# ── hardening #5 — strip dangling tool_calls when their tool result is dropped ──


def test_prepare_messages_strips_tool_call_when_result_is_empty():
    """When an assistant's tool result has empty content (e.g. a tool that
    returned ``""``), the tool message gets dropped.  The matching
    ``tool_calls`` entry on the assistant message must also be removed —
    otherwise MiniMax returns ``(2013) tool call result does not follow
    tool call`` because the assistant claims it called a tool but no
    result follows.
    """
    assistant = Message("assistant", "")
    assistant.add_tool_use(ToolUse(id="call_empty", name="Read", input={"path": "x"}))
    msgs = [
        Message("user", "read x"),
        assistant,
        Message("tool", "", name="call_empty"),
    ]
    out = _ConcreteProvider().prepare_messages(msgs)
    assert [m["role"] for m in out] == ["user", "assistant"]
    assert "tool_calls" not in out[-1]


def test_prepare_messages_strips_only_dropped_tool_call_when_mixed():
    """If the assistant emitted two tool calls and only one of them has
    an empty/empty tool result, only the dropped one is removed from the
    assistant's ``tool_calls`` list.  The other call's result survives
    intact."""
    assistant = Message("assistant", "")
    assistant.add_tool_use(ToolUse(id="call_keep", name="Read", input={"path": "a"}))
    assistant.add_tool_use(ToolUse(id="call_drop", name="Read", input={"path": "b"}))
    msgs = [
        Message("user", "read both"),
        assistant,
        Message("tool", "file a contents", name="call_keep"),
        Message("tool", "", name="call_drop"),
    ]
    out = _ConcreteProvider().prepare_messages(msgs)
    assert [m["role"] for m in out] == ["user", "assistant", "tool"]
    assistant_msg = next(m for m in out if m["role"] == "assistant")
    tc_ids = [tc["id"] for tc in assistant_msg["tool_calls"]]
    assert tc_ids == ["call_keep"]
    tool_msg = next(m for m in out if m["role"] == "tool")
    assert tool_msg["tool_call_id"] == "call_keep"


def test_prepare_messages_strips_orphaned_tool_call_entry():
    """When a tool result is dropped as an orphan (its id isn't in the
    preceding assistant's tool_calls), the related dangling
    ``tool_calls`` entry must also be cleaned up — but only when one
    is present.  This pins the behaviour for sessions that interleave
    tool messages from different turns."""
    assistant = Message("assistant", "")
    assistant.add_tool_use(ToolUse(id="call_real", name="Bash", input={"command": "ls"}))
    msgs = [
        Message("user", "go"),
        assistant,
        Message("tool", "ok", name="call_real"),
        Message("tool", "ghost result", name="call_ghost"),
    ]
    out = _ConcreteProvider().prepare_messages(msgs)
    assistant_msg = next(m for m in out if m["role"] == "assistant")
    tc_ids = [tc["id"] for tc in assistant_msg["tool_calls"]]
    assert tc_ids == ["call_real"]
    tool_msgs = [m for m in out if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "call_real"


def test_prepare_messages_leaves_assistant_text_only_when_no_results_match():
    """When every tool result is dropped, the assistant message ends up
    with no ``tool_calls`` and the request no longer contains any tool
    reference — clean prose for MiniMax to continue from."""
    assistant = Message("assistant", "")
    assistant.add_tool_use(ToolUse(id="call_x", name="Bash", input={"command": "ls"}))
    msgs = [
        Message("user", "go"),
        assistant,
        Message("tool", "", name="call_x"),
        Message("tool", "ghost", name="call_unknown"),
    ]
    out = _ConcreteProvider().prepare_messages(msgs)
    assert [m["role"] for m in out] == ["user", "assistant"]
    assert "tool_calls" not in out[-1]


def test_prepare_messages_strips_dangling_tool_call_from_earlier_assistant():
    """Regression for the (2013) ``tool call and result not match`` error
    that fires at high turn numbers.

    The previous fix only stripped dangling ``tool_call`` entries from
    the *last* assistant message, missing cases where the dangling
    entry belongs to an *earlier* assistant.  This is exactly what
    happens when turn 1's tool returns empty content and turn 2 then
    runs a fresh tool — turn 1's empty result gets dropped, leaving
    turn 1's assistant with a dangling ``tool_call`` reference while
    turn 2's tools flow through cleanly.
    """
    assistant_a = Message("assistant", "")
    assistant_a.add_tool_use(ToolUse(id="call_a", name="Bash", input={"command": "ls"}))
    assistant_b = Message("assistant", "")
    assistant_b.add_tool_use(ToolUse(id="call_b", name="Read", input={"path": "x"}))
    msgs = [
        Message("user", "do A"),
        assistant_a,
        Message("tool", "", name="call_a"),                 # empty → dropped
        Message("user", "do B"),
        assistant_b,
        Message("tool", "file x contents", name="call_b"),
    ]
    out = _ConcreteProvider().prepare_messages(msgs)
    assert [m["role"] for m in out] == [
        "user", "assistant", "user", "assistant", "tool",
    ]
    # First assistant must have its dangling tool_call stripped — it was
    # the *only* tool it emitted and the matching result is gone.
    first_assistant = out[1]
    assert "tool_calls" not in first_assistant
    # Second assistant's tool_call must survive.
    second_assistant = next(m for m in out if m["role"] == "assistant" and m is not first_assistant)
    assert [tc["id"] for tc in second_assistant["tool_calls"]] == ["call_b"]
    # The legitimate tool result must remain.
    tool_msg = next(m for m in out if m["role"] == "tool")
    assert tool_msg["tool_call_id"] == "call_b"


def test_prepare_messages_strips_dangling_entries_in_both_assistants():
    """Both assistants emit tool_calls and both have at least one
    dangling entry.  Each assistant must have only its own dangling
    entries stripped — not the other assistant's."""
    assistant_a = Message("assistant", "")
    assistant_a.add_tool_use(ToolUse(id="call_a1", name="Read", input={"path": "a"}))
    assistant_a.add_tool_use(ToolUse(id="call_a2", name="Read", input={"path": "b"}))
    assistant_b = Message("assistant", "")
    assistant_b.add_tool_use(ToolUse(id="call_b1", name="Read", input={"path": "c"}))
    assistant_b.add_tool_use(ToolUse(id="call_b2", name="Read", input={"path": "d"}))
    msgs = [
        Message("user", "phase A"),
        assistant_a,
        Message("tool", "a contents", name="call_a1"),       # kept
        Message("tool", "", name="call_a2"),                  # dropped (empty)
        Message("user", "phase B"),
        assistant_b,
        Message("tool", "", name="call_b1"),                  # dropped (empty)
        Message("tool", "d contents", name="call_b2"),        # kept
    ]
    out = _ConcreteProvider().prepare_messages(msgs)
    assert [m["role"] for m in out] == [
        "user", "assistant", "tool", "user", "assistant", "tool",
    ]
    # First assistant keeps only call_a1.
    first_assistant = out[1]
    assert [tc["id"] for tc in first_assistant["tool_calls"]] == ["call_a1"]
    # Second assistant keeps only call_b2.
    second_assistant = out[4]
    assert [tc["id"] for tc in second_assistant["tool_calls"]] == ["call_b2"]
    # Both surviving tool messages must still be there.
    tool_msgs = [m for m in out if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["call_a1", "call_b2"]


def test_prepare_messages_handles_dangling_assistant_without_tool_calls():
    """The second pass must not crash when an assistant message has no
    ``tool_calls`` field at all (e.g. a plain-text assistant turn)."""
    assistant_a = Message("assistant", "")
    assistant_a.add_tool_use(ToolUse(id="call_a", name="Bash", input={"command": "ls"}))
    msgs = [
        Message("user", "do A"),
        assistant_a,
        Message("tool", "", name="call_a"),                 # dropped
        Message("user", "now just chat"),
        Message("assistant", "ok, here's my reply"),
    ]
    out = _ConcreteProvider().prepare_messages(msgs)
    # Final assistant has no tool_calls key, so the cleanup loop must
    # skip it gracefully.
    assert [m["role"] for m in out] == [
        "user", "assistant", "user", "assistant",
    ]
    assert "tool_calls" not in out[1]
    assert "tool_calls" not in out[3]


def test_prepare_messages_empty_tool_id_does_not_invalidate_others():
    """When an assistant emits a tool_call with an empty id (no id
    supplied by the model), and the corresponding tool message also has
    an empty tool_call_id, both should be dropped together — leaving
    other tool_calls on the same assistant intact."""
    assistant = Message("assistant", "")
    assistant.add_tool_use(ToolUse(id="", name="Read", input={"path": "x"}))
    assistant.add_tool_use(ToolUse(id="call_real", name="Bash", input={"command": "ls"}))
    msgs = [
        Message("user", "do both"),
        assistant,
        Message("tool", "", name=""),                       # empty id, empty content
        Message("tool", "ls output", name="call_real"),
    ]
    out = _ConcreteProvider().prepare_messages(msgs)
    # Both empty-content messages are dropped in the first pass.
    assert [m["role"] for m in out] == ["user", "assistant", "tool"]
    # The dangling empty-id entry is removed; the real entry survives.
    assistant_msg = next(m for m in out if m["role"] == "assistant")
    assert [tc["id"] for tc in assistant_msg["tool_calls"]] == ["call_real"]


# ── classify_http_error ───────────────────────────────────────────────


def test_classify_http_error_includes_body_for_generic_400():
    """The generic 400 path must embed the upstream body in the message."""
    err = Provider.classify_http_error(
        400,
        '{"error": {"message": "model not found"}}',
    )
    assert isinstance(err, ProviderError)
    assert "upstream error 400" in str(err)
    assert "model not found" in str(err)


def test_classify_http_error_429_keeps_specialized_message():
    """RateLimitError message stays unchanged."""
    err = Provider.classify_http_error(429, "rate limited")
    assert isinstance(err, RateLimitError)
    assert "rate limit exceeded" in str(err)


def test_classify_http_error_401_keeps_auth_message():
    err = Provider.classify_http_error(401, "no key")
    assert isinstance(err, AuthError)
    assert "authentication failed" in str(err)


def test_classify_http_error_400_context_length():
    err = Provider.classify_http_error(400, "context length exceeded")
    assert isinstance(err, ContextLengthError)


def test_classify_http_error_5xx_includes_body():
    err = Provider.classify_http_error(503, "service unavailable")
    assert isinstance(err, TransientProviderError)
    assert "503" in str(err)
    assert "service unavailable" in str(err)


def test_classify_http_error_empty_body_keeps_old_message():
    """No body → no spurious colon in the message."""
    err = Provider.classify_http_error(400, "")
    assert str(err).strip().endswith("400")


# ── MiniMaxiProvider model resolution ─────────────────────────────────


def test_minimaxi_picks_m3_for_cn_cp_key():
    p = MiniMaxiProvider(api_key="cn-cp-fake-key-xyz")
    assert p._pick_default_model("MiniMax-M2.7") == "MiniMax-M3"


def test_minimaxi_keeps_m27_for_other_keys():
    p = MiniMaxiProvider(api_key="eyJhbGciOiJIUzI1NiJ9.fake")
    assert p._pick_default_model("MiniMax-M2.7") == "MiniMax-M2.7"


def test_minimaxi_respects_explicit_non_default_request():
    """If the caller passes a non-default model, keep it even on a cn-cp- key."""
    p = MiniMaxiProvider(api_key="cn-cp-fake-key-xyz")
    assert p._pick_default_model("MiniMax-M2.5") == "MiniMax-M2.5"


def test_minimaxi_resolves_env_var_in_key():
    p = MiniMaxiProvider(api_key="${MINMAXI_API_KEY}")
    assert p._pick_default_model("MiniMax-M2.7") == "MiniMax-M2.7"


@pytest.mark.parametrize(
    "key,expected",
    [
        ("cn-cp-aaa", "MiniMax-M3"),
        ("CN-CP-aaa", "MiniMax-M2.7"),
        ("eyJ-cn-cp-x", "MiniMax-M2.7"),
        ("", "MiniMax-M2.7"),
    ],
)
def test_minimaxi_model_heuristic_table(key, expected):
    p = MiniMaxiProvider(api_key=key)
    assert p._pick_default_model("MiniMax-M2.7") == expected