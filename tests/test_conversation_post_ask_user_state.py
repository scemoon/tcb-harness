"""Regression: AskUser exit paths must not break the double-ESC cancel.

After AskUser is closed by ESC (or answered via the AskUserWidget, or
answered via the prompt while AskUser is pending), the next ESC press
must still trigger the normal double-ESC cancel flow. Previously, all
three exit paths left ``self.turn == "client"`` while the agent was
still processing, which made ``Conversation.check_action("cancel")``
return ``None`` and silently disabled the cancel action until the
agent's turn naturally ended.

Each test pins the specific exit path and verifies ``self.turn`` is
restored to ``"agent"`` so subsequent ESC presses reach ``action_cancel``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from tui.widgets.ask_user import AskUserSubmitted
from tui.widgets.conversation import Conversation


def _make_conv(monkeypatch) -> Conversation:
    """Build a Conversation with DOM-/event-loop-dependent attributes mocked.

    Textual vars (``turn``, ``busy_count``) still trigger their watchers
    when assigned, so we silence the watchers that query the DOM.
    """
    monkeypatch.setattr(Conversation, "watch_agent", lambda self, agent: None)
    monkeypatch.setattr(Conversation, "watch_turn", lambda self, turn: None)
    monkeypatch.setattr(Conversation, "watch_busy_count", lambda self, busy: None)
    conv = Conversation(project_path=Path.cwd())
    conv.contents = MagicMock()
    conv.contents.children = []
    conv.contents.get_child_by_id = MagicMock(return_value=None)
    conv.prompt = MagicMock()
    conv.cursor = MagicMock()
    conv.window = MagicMock()
    conv.flash = MagicMock()
    conv.focus_prompt = MagicMock()
    conv.post = AsyncMock()
    return conv


class TestTurnRestoredAfterAskUserExit:
    """All AskUser exit paths must restore turn='agent'."""

    async def test_turn_restored_after_ask_user_esc_cancel(self, monkeypatch):
        """ESC closing AskUser must restore turn='agent' so the second ESC
        reaches ``action_cancel`` (after the first post-close press flashes
        the "press esc again" hint, the third press terminates the session)."""
        conv = _make_conv(monkeypatch)
        conv.agent = MagicMock()
        conv.agent._process = MagicMock()
        conv._pending_ask_user = True
        conv.turn = "client"

        await conv.action_cancel()

        assert conv._pending_ask_user is False
        assert conv.turn == "agent", (
            "After ESC closes AskUser, turn must be 'agent' so the "
            "check_action('cancel') gate lets the next ESC through."
        )
        conv.agent.send_ask_user_answer.assert_called_once_with("", cancelled=True)

    async def test_turn_restored_after_ask_user_submit(self, monkeypatch):
        """Submitting an answer through AskUserWidget must restore turn='agent'."""
        conv = _make_conv(monkeypatch)
        conv.agent = MagicMock()
        conv._pending_ask_user = True
        conv.turn = "client"

        await conv.on_ask_user_submitted(AskUserSubmitted("my answer", "tool-1"))

        assert conv._pending_ask_user is False
        assert conv.turn == "agent"
        conv.agent.send_ask_user_answer.assert_called_once_with(
            "my answer", cancelled=False, rollback=False
        )

    async def test_turn_restored_after_prompt_text_reply(self, monkeypatch):
        """Replying via the prompt while AskUser is pending must restore
        turn='agent' (covers the third exit path at conversation.py:958)."""
        from tui.messages import UserInputSubmitted

        conv = _make_conv(monkeypatch)
        conv.agent = MagicMock()
        conv._pending_ask_user = True
        conv.turn = "client"

        # Stub out dependencies the handler touches before reaching the
        # _pending_ask_user branch.
        conv.prompt_history.append = AsyncMock()
        monkeypatch.setattr(
            Conversation,
            "slash_command",
            AsyncMock(return_value=False),
            raising=False,
        )

        event = UserInputSubmitted(body="free text", shell=False)
        await conv.on_user_input_submitted(event)

        assert conv._pending_ask_user is False
        assert conv.turn == "agent"
        conv.agent.send_ask_user_answer.assert_called_once_with(
            "free text", cancelled=False
        )


class TestDoubleEscAfterAskUserCancel:
    """End-to-end: ESC → ESC → ESC after AskUser cancel must terminate."""

    async def test_double_esc_terminates_session_after_ask_user_cancel(
        self, monkeypatch
    ):
        """Reproduces the user's scenario:

        1. AskUser showing
        2. ESC → AskUser closed, turn='agent', _last_escape_time=0.0
        3. ESC → check_action passes, falls into 'else' branch,
           flashes "press esc again", _last_escape_time=now
        4. ESC (within 3 s) → check_action passes, agent.cancel() called

        Without the fix, step 3 is silently dropped (check_action returns
        None) and the session keeps running until it finishes naturally.
        """
        fake_now = [1000.0]
        monkeypatch.setattr("tui.widgets.conversation.monotonic", lambda: fake_now[0])

        conv = _make_conv(monkeypatch)
        conv.agent = MagicMock()
        agent_cancel = AsyncMock(return_value=True)
        conv.agent.cancel = agent_cancel
        conv.agent._process = MagicMock()
        conv._pending_ask_user = True
        conv.turn = "client"

        # Press 1: ESC closes AskUser.
        await conv.action_cancel()
        assert conv._pending_ask_user is False
        assert conv.turn == "agent"
        assert conv._last_escape_time == 0.0
        agent_cancel.assert_not_called()

        # After close, check_action must report the cancel action enabled.
        assert conv.check_action("cancel", ()) is True

        # Press 2: ESC flashes hint (else branch), does NOT cancel yet.
        fake_now[0] = 1000.5
        await conv.action_cancel()
        assert conv._last_escape_time == 1000.5
        agent_cancel.assert_not_called()

        # Press 3: ESC within 3 s → agent.cancel() called.
        fake_now[0] = 1001.2
        await conv.action_cancel()
        agent_cancel.assert_awaited_once()
