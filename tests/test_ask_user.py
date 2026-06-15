"""Tests for the AskUser tool flow: detection, ASK_USER event, and resolve_approval."""

from __future__ import annotations

import json
from pathlib import Path

from cdha.agent.agents.types import BuildAgent
from cdha.agent.engine import AgentEngine


def _make_engine():
    """Create a minimal engine for testing resolve_approval."""

    class FakeApp:
        config = type(
            "cfg",
            (),
            {
                "default_provider": "minimaxi",
                "default_model": "minimax-m1-671b",
                "providers": {},
            },
        )()

    engine = AgentEngine(FakeApp(), project_dir=Path.cwd())
    engine.current_agent = BuildAgent()
    return engine


class TestResolveApprovalAskUser:
    """Verify resolve_approval handles AskUser with answer parameter."""

    async def test_approved_returns_answer_as_tool_result(self):
        engine = _make_engine()
        engine._pending_approval = {
            "tool_call": {"id": "tu-1", "name": "AskUser", "input": {"question": "Continue?"}},
            "category": "interaction",
            "ask_user": True,
        }
        result = await engine.resolve_approval(approved=True, answer="Yes")
        assert result is not None
        assert result["is_error"] is False
        parsed = json.loads(result["content"])
        assert parsed.get("answer") == "Yes"
        assert engine._pending_approval is None

    async def test_cancelled_returns_error(self):
        engine = _make_engine()
        engine._pending_approval = {
            "tool_call": {"id": "tu-2", "name": "AskUser", "input": {"question": "Continue?"}},
            "category": "interaction",
            "ask_user": True,
        }
        result = await engine.resolve_approval(approved=False, answer="")
        assert result is not None
        assert result["is_error"] is True
        parsed = json.loads(result["content"])
        assert "cancel" in parsed.get("error", "").lower()
        assert engine._pending_approval is None

    async def test_ask_user_does_not_re_execute_tool(self):
        """Verify that resolve_approval for AskUser does NOT call _execute_tool."""
        engine = _make_engine()
        executed = []

        async def fake_execute(tc):
            executed.append(tc)
            return {"tool_use_id": tc["id"], "content": "should not happen", "is_error": False}

        engine._execute_tool = fake_execute
        engine._pending_approval = {
            "tool_call": {"id": "tu-3", "name": "AskUser", "input": {}},
            "category": "interaction",
            "ask_user": True,
        }
        result = await engine.resolve_approval(approved=True, answer="my answer")
        assert executed == [], f"_execute_tool should not be called for AskUser, got {executed}"
        parsed = json.loads(result["content"])
        assert parsed["answer"] == "my answer"


class TestResolveApprovalBackwardCompat:
    """Verify existing permission flow still works (no ask_user flag)."""

    async def test_default_call_works(self):
        """resolve_approval without answer arg defaults to empty string."""
        engine = _make_engine()
        engine._pending_approval = {
            "tool_call": {"id": "tu-4", "name": "AskUser", "input": {}},
            "category": "interaction",
            "ask_user": True,
        }
        result = await engine.resolve_approval(approved=True)
        assert result is not None
        parsed = json.loads(result["content"])
        assert parsed["answer"] == ""

    async def test_no_pending_returns_none(self):
        engine = _make_engine()
        engine._pending_approval = None
        result = await engine.resolve_approval(approved=True, answer="x")
        assert result is None


class TestAskUserReask:
    """Verify the AskUser re-ask flow: 1st ask (60s) → 2nd brief ask (60s) → cancel.

    The constants and loop live in the CDHACPAdapter. We assert the values
    without spinning up a real adapter, since the re-ask logic is just a
    timing/repetition policy.
    """

    def test_ask_user_reask_timeout_constant_is_60_seconds(self):
        """The re-ask interval should be 1 minute as the user requested."""
        from cdha.agent.cdh_agent_acp import CDHACPAdapter
        # Verify the source contains the right constant
        import inspect
        src = inspect.getsource(CDHACPAdapter.session_prompt)
        assert "_ASK_USER_REASK_TIMEOUT = 60" in src, (
            "Expected 1-minute (60s) timeout in AskUser re-ask"
        )

    def test_ask_user_sends_brief_remind_on_first_timeout(self):
        """On first timeout, send '请确认' reminder, not the full question."""
        from cdha.agent.cdh_agent_acp import CDHACPAdapter
        import inspect
        src = inspect.getsource(CDHACPAdapter.session_prompt)
        # The reminder should be brief ("请确认") and not include the full question
        assert "ask_user_remind" in src
        assert "请确认" in src
        # Should NOT re-send the full ask_user event with question/questions
        assert "range(2)" in src, "Expected exactly 2 attempts (initial + 1 re-ask)"

    def test_ask_user_uses_default_on_second_timeout(self):
        """On second timeout (after 2 minutes total), use the default option
        rather than cancelling, so the agent can continue with a sensible
        choice."""
        from cdha.agent.cdh_agent_acp import CDHACPAdapter
        import inspect
        src = inspect.getsource(CDHACPAdapter.session_prompt)
        # On second timeout, the adapter must call the default-picker and
        # NOT set cancelled = True.
        assert "_pick_default_ask_user_answer" in src, (
            "Expected _pick_default_ask_user_answer helper for 3rd-attempt default"
        )

    def test_pick_default_uses_marked_default(self):
        """When an option has default=True, it wins over the first option."""
        from cdha.agent.cdh_agent_acp import CDHACPAdapter
        from dataclasses import dataclass
        # Build a minimal stand-in for the StreamEvent carrying ask fields
        @dataclass
        class FakeEvent:
            ask_options: list = None
            ask_questions: list = None
        adapter = CDHACPAdapter()
        e = FakeEvent(ask_options=[
            {"value": "first", "label": "First"},
            {"value": "best", "label": "Best", "default": True},
        ])
        result = adapter._pick_default_ask_user_answer(e)
        assert result == "best"

    def test_pick_default_falls_back_to_first(self):
        """When no option is marked default, fall back to the first one."""
        from cdha.agent.cdh_agent_acp import CDHACPAdapter
        from dataclasses import dataclass
        @dataclass
        class FakeEvent:
            ask_options: list = None
            ask_questions: list = None
        adapter = CDHACPAdapter()
        e = FakeEvent(ask_options=[
            {"value": "alpha", "label": "Alpha"},
            {"value": "beta", "label": "Beta"},
        ])
        result = adapter._pick_default_ask_user_answer(e)
        assert result == "alpha"

    def test_pick_default_handles_multi_question(self):
        """Multi-question prompts return a JSON dict of {idx: default_value}."""
        from cdha.agent.cdh_agent_acp import CDHACPAdapter
        from dataclasses import dataclass
        import json as _json
        @dataclass
        class FakeEvent:
            ask_options: list = None
            ask_questions: list = None
        adapter = CDHACPAdapter()
        e = FakeEvent(ask_questions=[
            {"question": "Q1", "options": [{"value": "a"}, {"value": "b", "default": True}]},
            {"question": "Q2", "options": [{"value": "x"}]},
        ])
        result = adapter._pick_default_ask_user_answer(e)
        parsed = _json.loads(result)
        assert parsed == {"0": "b", "1": "x"}

    def test_pick_default_handles_no_options(self):
        """Free-text questions (no options) return empty string."""
        from cdha.agent.cdh_agent_acp import CDHACPAdapter
        from dataclasses import dataclass
        @dataclass
        class FakeEvent:
            ask_options: list = None
            ask_questions: list = None
        adapter = CDHACPAdapter()
        e = FakeEvent()  # neither set
        result = adapter._pick_default_ask_user_answer(e)
        assert result == ""
