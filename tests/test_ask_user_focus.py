"""Regression: clicking inside AskUserWidget must not steal focus.

Root cause: ``Conversation.on_click`` treated clicks on the AskUserWidget
block as block-cursor selection and called ``refresh_block_cursor()``, which
calls ``self.window.focus()`` — stealing focus from the ask-user Input the
user had just clicked. After the first such click, the ask-user input could
never be refocused by mouse.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Input

from tui.widgets.ask_user import AskUserWidget
from tui.widgets.conversation import Conversation


class _HostApp(App):
    """Hosts a real AskUserWidget inside a container that stands in for
    ``Conversation.contents``."""

    def compose(self) -> ComposeResult:
        with Container(id="contents"):
            yield AskUserWidget(
                tool_id="t1",
                question="请问要升级哪个用户？",
                options=[],
            )


def _run_click(monkeypatch) -> tuple[MagicMock, MagicMock]:
    """Run the Conversation.on_click handler against a click on the real
    ask-user Input, while the widget tree is still mounted (exiting the
    run_test context unmounts it and empties the ancestor chain)."""
    app = _HostApp()
    result: dict = {}

    async def _run():
        async with app.run_test() as pilot:
            await pilot.pause()
            ask_input = app.query_one("#ask-custom-input", Input)
            contents = app.query_one("#contents", Container)

            screen = MagicMock()
            screen.get_selected_text.return_value = ""
            window = MagicMock()

            # Class-level properties so Conversation's getter attributes
            # (screen/contents/window) resolve to our stand-ins. monkeypatch
            # restores them after the test.
            monkeypatch.setattr(Conversation, "screen", property(lambda self: screen))
            monkeypatch.setattr(
                Conversation, "contents", property(lambda self: contents)
            )
            monkeypatch.setattr(Conversation, "window", property(lambda self: window))

            conv = Conversation(project_path=Path.cwd())
            conv.refresh_block_cursor = MagicMock()
            conv.prompt = MagicMock()
            conv.cursor_offset = -1

            click = events.Click(ask_input, 10, 10, 0, 0, 0, False, False, False)
            conv.on_click(click)

            result["refresh"] = conv.refresh_block_cursor
            result["window"] = window

    asyncio.run(_run())
    return result["refresh"], result["window"]


class TestAskUserClickDoesNotStealFocus:
    def test_on_click_ignores_ask_user_widget(self, monkeypatch):
        refresh_block_cursor, window = _run_click(monkeypatch)

        # The block-cursor path (which calls window.focus() and steals focus
        # from the ask-user input) must not run for clicks inside AskUserWidget.
        refresh_block_cursor.assert_not_called()
        window.focus.assert_not_called()

    def test_check_action_cancel_allowed_when_ask_user_pending(self, monkeypatch):
        """check_action('cancel') must allow ESC while AskUser is active.

        Regression: when AskUser is showing, ``turn`` is ``"client"`` so the
        ``check_action`` guard (``self.agent and self.turn == "agent"``) used
        to return ``None``, which prevented ``action_cancel`` from ever
        running — ESC couldn't close AskUser.
        """
        conv = Conversation(project_path=Path.cwd())
        conv.turn = "client"

        conv._pending_ask_user = True
        result_pending = conv.check_action("cancel", ())

        conv._pending_ask_user = False
        monkeypatch.setattr(Conversation, "watch_agent", lambda self, agent: None)
        conv.agent = MagicMock()
        conv.turn = "agent"
        result_no_ask = conv.check_action("cancel", ())

        conv.agent = None
        result_no_agent = conv.check_action("cancel", ())

        assert result_pending is True, "ESC must close AskUser (pending)"
        assert result_no_ask is True, "ESC must cancel agent turn (turn=agent)"
        assert result_no_agent is None
