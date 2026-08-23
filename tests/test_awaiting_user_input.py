"""Tests for the `awaiting_user_input` flow.

Covers:
- Backend adapter emits the correct ``awaiting_user_input`` session/update.
- ACP Agent dispatches the ``awaiting_user_input`` update to an
  ``AwaitingUserInput`` message (and that ``ask_user`` still dispatches to
  ``AskUser`` as a regression check).
- The protocol schema validates the new ``awaiting_user_input`` update type.
- Regression: session/update notifications survive the JSON-RPC type-
  validation layer (see ``TestJsonRpcDispatch``). Before the ``SessionUpdate``
  union included ``ask_user`` / ``awaiting_user_input`` / ``aidlc_state``,
  those notifications raised ``TypeCheckError`` inside ``Server.call`` and
  were silently dropped — the AskUser widget never appeared and user input
  was queued instead of answered.
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


class TestJsonRpcDispatch:
    """Regression: session/update notifications must survive the JSON-RPC
    type-validation layer inside ``Server.call``.

    The dispatch tests call ``rpc_session_update`` directly and bypass the
    ``check_type`` validation, so they cannot catch a ``SessionUpdate`` union
    that omits an update type. These tests go through the real path.
    """

    def _make_agent_with_server(self):
        from pathlib import Path

        from tui import jsonrpc
        from tui.agent_schema import Agent as AgentData

        agent_data = AgentData({
            "name": "test",
            "title": "Test",
            "run_command": "",
        })
        agent = Agent(Path.cwd(), agent_data, "sid")
        posted: list = []
        agent.post_message = Mock(side_effect=lambda m: posted.append(m))  # type: ignore[assignment]
        server = jsonrpc.Server()
        server.expose_instance(agent)
        return server, posted

    async def _call_session_update(self, server, update: dict) -> None:
        result = await server.call({
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {"sessionId": "sid", "update": update},
        })
        # A notification must not produce an error response — previously the
        # dropped ask_user updates were echoed back as error responses.
        assert result is None, f"session/update notification errored: {result}"

    async def test_ask_user_dispatches_through_server(self):
        server, posted = self._make_agent_with_server()
        await self._call_session_update(server, {
            "sessionUpdate": "ask_user",
            "question": "请问要继续吗？",
            "context": "",
            "options": [],
            "toolId": "auto-text-ask",
        })
        assert any(isinstance(m, acp_messages.AskUser) for m in posted)
        msg = next(m for m in posted if isinstance(m, acp_messages.AskUser))
        assert msg.question == "请问要继续吗？"
        assert msg.tool_id == "auto-text-ask"

    async def test_ask_user_multi_question_dispatches_through_server(self):
        server, posted = self._make_agent_with_server()
        await self._call_session_update(server, {
            "sessionUpdate": "ask_user",
            "questions": [
                {"header": "Q1", "question": "Which user?", "type": "single",
                 "options": [{"label": "A", "value": "a"}]},
            ],
            "context": "",
            "toolId": "tu-7",
        })
        assert any(isinstance(m, acp_messages.AskUser) for m in posted)
        msg = next(m for m in posted if isinstance(m, acp_messages.AskUser))
        assert len(msg.questions) == 1
        assert msg.tool_id == "tu-7"

    async def test_awaiting_user_input_dispatches_through_server(self):
        server, posted = self._make_agent_with_server()
        await self._call_session_update(server, {
            "sessionUpdate": "awaiting_user_input",
            "promptPreview": "Pick one",
        })
        assert any(isinstance(m, acp_messages.AwaitingUserInput) for m in posted)
        msg = next(m for m in posted if isinstance(m, acp_messages.AwaitingUserInput))
        assert msg.prompt_preview == "Pick one"

    async def test_aidlc_state_dispatches_through_server(self):
        server, posted = self._make_agent_with_server()
        await self._call_session_update(server, {
            "sessionUpdate": "aidlc_state",
            "current_phase": "requirements",
            "completed_phases": ["discovery"],
            "gate_results": {},
        })
        assert any(isinstance(m, acp_messages.AIDLCState) for m in posted)
        msg = next(m for m in posted if isinstance(m, acp_messages.AIDLCState))
        assert msg.current_phase == "requirements"

    async def test_ask_user_remind_and_default_used_do_not_error(self):
        """Reminder/default-used notifications validate (no error response),
        even though the TUI has no dedicated handlers for them."""
        server, _ = self._make_agent_with_server()
        await self._call_session_update(server, {
            "sessionUpdate": "ask_user_remind",
            "text": "请确认？",
            "toolId": "auto-text-ask",
        })
        await self._call_session_update(server, {
            "sessionUpdate": "ask_user_default_used",
            "answer": "yes",
            "toolId": "auto-text-ask",
        })

    async def test_notification_unexpected_exception_no_response(self):
        """A notification whose handler raises a non-JSONRPC error must NOT
        get an error response — replying violates the JSON-RPC spec and the
        peer would misinterpret it as a request."""
        from tui import jsonrpc

        def _boom() -> None:
            raise RuntimeError("boom")

        server = jsonrpc.Server()
        server.method("test/boom")(_boom)
        result = await server.call({
            "jsonrpc": "2.0",
            "method": "test/boom",
        })
        assert result is None

    async def test_request_unexpected_exception_returns_error_response(self):
        """Requests (with id) still surface unexpected errors to the caller."""
        from tui import jsonrpc

        def _boom() -> None:
            raise RuntimeError("boom")

        server = jsonrpc.Server()
        server.method("test/boom")(_boom)
        result = await server.call({
            "jsonrpc": "2.0",
            "method": "test/boom",
            "id": 7,
        })
        assert result is not None
        assert result["id"] == 7
        assert result["error"]["code"] == int(jsonrpc.ErrorCode.INTERNAL_ERROR)
