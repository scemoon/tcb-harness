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
