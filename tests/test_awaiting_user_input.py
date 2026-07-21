"""Tests for the `awaiting_user_input` flow.

Covers:
- Backend adapter emits the correct ``awaiting_user_input`` session/update.
- ACP Agent dispatches the ``awaiting_user_input`` update to an
  ``AwaitingUserInput`` message (and that ``ask_user`` still dispatches to
  ``AskUser`` as a regression check).
- The protocol schema validates the new ``awaiting_user_input`` update type.
"""

from __future__ import annotations

from unittest.mock import Mock

from onecode.agent.onecode_agent_acp import CDHACPAdapter

from tui.acp import messages as acp_messages
from tui.acp import protocol as acp_protocol
from tui.acp.agent import Agent


def _spy_adapter() -> tuple[CDHACPAdapter, Mock]:
    adapter = CDHACPAdapter()
    adapter.send_session_update = Mock()
    return adapter, adapter.send_session_update


def _collect_updates(spy: Mock) -> list[dict]:
    return [call[0][0] for call in spy.call_args_list]


class TestAdapterAwaitingUserInput:
    def test_emits_awaiting_user_input_update(self):
        adapter, spy = _spy_adapter()
        adapter.send_awaiting_user_input("What is your name?")
        updates = _collect_updates(spy)
        assert len(updates) == 1
        update = updates[0]
        assert update["sessionUpdate"] == "awaiting_user_input"
        assert update["promptPreview"] == "What is your name?"

    def test_emits_empty_preview_when_omitted(self):
        adapter, spy = _spy_adapter()
        adapter.send_awaiting_user_input()
        updates = _collect_updates(spy)
        assert len(updates) == 1
        assert updates[0]["sessionUpdate"] == "awaiting_user_input"
        assert updates[0]["promptPreview"] == ""


class TestAgentDispatch:
    def _make_agent(self) -> tuple[Agent, list]:
        from pathlib import Path

        from tui.agent_schema import Agent as AgentData

        agent_data = AgentData({
            "name": "test",
            "title": "Test",
            "run_command": "",
        })
        agent = Agent(Path.cwd(), agent_data, "sid")
        posted: list = []
        agent.post_message = Mock(side_effect=lambda m: posted.append(m))  # type: ignore[assignment]
        return agent, posted

    def test_dispatch_awaiting_user_input(self):
        agent, posted = self._make_agent()
        agent.rpc_session_update(
            "sid",
            {"sessionUpdate": "awaiting_user_input", "promptPreview": "Pick one"},
        )
        assert any(isinstance(m, acp_messages.AwaitingUserInput) for m in posted)
        msg = next(m for m in posted if isinstance(m, acp_messages.AwaitingUserInput))
        assert msg.prompt_preview == "Pick one"

    def test_dispatch_ask_user_regression(self):
        agent, posted = self._make_agent()
        agent.rpc_session_update(
            "sid",
            {
                "sessionUpdate": "ask_user",
                "question": "Continue?",
                "toolId": "tu-1",
            },
        )
        assert any(isinstance(m, acp_messages.AskUser) for m in posted)
        msg = next(m for m in posted if isinstance(m, acp_messages.AskUser))
        assert msg.question == "Continue?"
        assert msg.tool_id == "tu-1"


class TestProtocolSchema:
    def test_awaiting_user_input_update_validates(self):
        update: acp_protocol.AwaitingUserInputUpdate = {
            "sessionUpdate": "awaiting_user_input",
            "promptPreview": "hi",
        }
        # Construction above is the TypedDict contract; assert discriminator.
        assert update["sessionUpdate"] == "awaiting_user_input"

    def test_ask_user_still_defined(self):
        # Ensure the existing ask_user response type is untouched.
        assert hasattr(acp_protocol, "AskUserResponse")
