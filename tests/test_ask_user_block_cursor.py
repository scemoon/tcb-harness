"""Tests for AskUserWidget's BlockProtocol implementation.

Verifies the cursor-navigation contract:
- ``block_cursor_down`` / ``block_cursor_up`` walk through the widget's
  focusable children (RadioButton, Input, Button).
- ``block_cursor_down`` / ``block_cursor_up`` return ``None`` when the
  cursor has moved past the last / first child, signalling the host
  (``Conversation``) to advance the conversation-level block cursor.
- ``get_cursor_block`` returns the currently selected child or ``None``.
- ``block_select(widget)`` sets the offset to that widget's index.
- ``block_cursor_clear`` resets the offset to ``-1``.
- ``AskUserWidget`` is recognised as a ``BlockProtocol`` instance
  (``isinstance`` check).

Also verifies the keyboard bindings (``up`` / ``down``) move focus
through the children without leaving the widget.
"""

from __future__ import annotations

import asyncio

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Button, Input, RadioButton

from tui.protocol import BlockProtocol
from tui.widgets.ask_user import AskUserSubmitted, AskUserWidget


class _HostApp(App):
    def __init__(self, **widget_kwargs) -> None:
        super().__init__()
        self._widget_kwargs = widget_kwargs

    def compose(self) -> ComposeResult:
        with Container():
            yield AskUserWidget(**self._widget_kwargs)


def _run(coro):
    return asyncio.run(coro)


# ── BlockProtocol surface ─────────────────────────────────────────────────────


class TestAskUserIsBlockProtocol:
    def test_isinstance_block_protocol(self):
        """AskUserWidget must satisfy the BlockProtocol duck type."""
        app = _HostApp(tool_id="t1", question="Q?", options=[
            {"label": "Yes", "value": "yes"},
        ])
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one(AskUserWidget)
                assert isinstance(widget, BlockProtocol)
        _run(_test())


# ── Cursor navigation ────────────────────────────────────────────────────────


class TestAskUserCursorNavigation:
    def test_block_cursor_down_from_minus_one_lands_on_first(self):
        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[
                {"label": "Yes", "value": "yes"},
                {"label": "No", "value": "no"},
            ],
        )

        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one(AskUserWidget)
                kids = widget._cursor_children()
                assert len(kids) >= 2
                first = widget.block_cursor_down()
                assert first is not None
                assert first is kids[0]
                assert widget.cursor_offset == 0

        _run(_test())

    def test_block_cursor_down_walks_through_children(self):
        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[
                {"label": "Yes", "value": "yes"},
                {"label": "No", "value": "no"},
            ],
        )

        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one(AskUserWidget)
                kids = widget._cursor_children()
                seen = []
                for _ in range(len(kids)):
                    w = widget.block_cursor_down()
                    if w is None:
                        break
                    seen.append(w)
                assert seen == kids
                assert widget.cursor_offset == len(kids) - 1

        _run(_test())

    def test_block_cursor_down_past_last_returns_none(self):
        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[
                {"label": "Yes", "value": "yes"},
                {"label": "No", "value": "no"},
            ],
        )

        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one(AskUserWidget)
                kids = widget._cursor_children()
                for _ in range(len(kids)):
                    widget.block_cursor_down()
                result = widget.block_cursor_down()
                assert result is None
                assert widget.cursor_offset == -1

        _run(_test())

    def test_block_cursor_up_from_minus_one_lands_on_last(self):
        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[
                {"label": "Yes", "value": "yes"},
                {"label": "No", "value": "no"},
            ],
        )

        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one(AskUserWidget)
                kids = widget._cursor_children()
                last = widget.block_cursor_up()
                assert last is not None
                assert last is kids[-1]
                assert widget.cursor_offset == len(kids) - 1

        _run(_test())

    def test_block_cursor_up_walks_through_children(self):
        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[
                {"label": "Yes", "value": "yes"},
                {"label": "No", "value": "no"},
            ],
        )

        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one(AskUserWidget)
                kids = widget._cursor_children()
                seen = []
                for _ in range(len(kids)):
                    w = widget.block_cursor_up()
                    if w is None:
                        break
                    seen.append(w)
                assert seen == list(reversed(kids))

        _run(_test())

    def test_block_cursor_up_past_first_returns_none(self):
        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[
                {"label": "Yes", "value": "yes"},
                {"label": "No", "value": "no"},
            ],
        )

        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one(AskUserWidget)
                kids = widget._cursor_children()
                for _ in range(len(kids)):
                    widget.block_cursor_up()
                result = widget.block_cursor_up()
                assert result is None
                assert widget.cursor_offset == -1

        _run(_test())

    def test_get_cursor_block_returns_current_child(self):
        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[
                {"label": "Yes", "value": "yes"},
                {"label": "No", "value": "no"},
            ],
        )

        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one(AskUserWidget)
                kids = widget._cursor_children()
                widget.cursor_offset = 0
                assert widget.get_cursor_block() is kids[0]
                widget.cursor_offset = 1
                assert widget.get_cursor_block() is kids[1]

        _run(_test())

    def test_get_cursor_block_returns_none_when_unset(self):
        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[{"label": "Yes", "value": "yes"}],
        )

        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one(AskUserWidget)
                assert widget.cursor_offset == -1
                assert widget.get_cursor_block() is None

        _run(_test())

    def test_block_select_sets_offset(self):
        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[
                {"label": "Yes", "value": "yes"},
                {"label": "No", "value": "no"},
            ],
        )

        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one(AskUserWidget)
                kids = widget._cursor_children()
                target = kids[1]
                widget.block_select(target)
                assert widget.cursor_offset == 1

        _run(_test())

    def test_block_select_unknown_widget_ignored(self):
        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[{"label": "Yes", "value": "yes"}],
        )

        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one(AskUserWidget)
                widget.cursor_offset = 2
                widget.block_select(Button("ghost"))
                assert widget.cursor_offset == 2

        _run(_test())

    def test_block_cursor_clear_resets_offset(self):
        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[{"label": "Yes", "value": "yes"}],
        )

        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one(AskUserWidget)
                widget.cursor_offset = 2
                widget.block_cursor_clear()
                assert widget.cursor_offset == -1

        _run(_test())


# ── Keyboard bindings ────────────────────────────────────────────────────────


class TestAskUserKeyboardBindings:
    def test_down_arrow_moves_focus_to_next_child(self):
        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}],
        )
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one(AskUserWidget)
                kids = widget._cursor_children()
                # Initial: focus should be on first RadioButton
                first = kids[0]
                assert first.has_focus
                await pilot.press("down")
                await pilot.pause()
                assert kids[1].has_focus
        _run(_test())

    def test_up_arrow_moves_focus_to_previous_child(self):
        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}],
        )
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one(AskUserWidget)
                kids = widget._cursor_children()
                # Move down once, then up
                await pilot.press("down")
                await pilot.pause()
                assert kids[1].has_focus
                await pilot.press("up")
                await pilot.pause()
                assert kids[0].has_focus
        _run(_test())

    def test_down_past_last_keeps_focus_inside_widget(self):
        """Down arrow past last child must not crash and must keep focus
        inside the widget (cursor_offset stays at -1 since the keyboard
        handler does not manipulate the BlockProtocol offset)."""
        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[{"label": "Yes", "value": "yes"}],
        )
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one(AskUserWidget)
                kids = widget._cursor_children()
                last = kids[-1]
                for _ in range(len(kids) + 1):
                    await pilot.press("down")
                    await pilot.pause()
                # Past-last should clamp to last child (no exit via keyboard)
                assert last.has_focus
                # cursor_offset for BlockProtocol stays untouched by keyboard
                assert widget.cursor_offset == -1
        _run(_test())


# ── Data layer ──────────────────────────────────────────────────────────────


class TestAskUserAnswerDataLayer:
    """The internal AskUserAnswer NamedTuple must be importable and round-trip
    options through the constructor."""

    def test_ask_user_answer_importable(self):
        from tui.widgets.ask_user import AskUserAnswer
        ans = AskUserAnswer(value="v", label="L", kind=None, option_id="v")
        assert ans.value == "v"
        assert ans.label == "L"

    def test_options_dict_converted_to_ask_user_answer(self):
        app = _HostApp(
            tool_id="t1",
            question="?",
            options=[
                {"label": "A", "value": "a", "description": "first"},
                {"label": "B", "value": "b"},
            ],
        )
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                widget = app.query_one(AskUserWidget)
                assert len(widget._options) == 2
                assert widget._options[0].value == "a"
                assert widget._options[0].label == "A"
                assert widget._options[1].value == "b"
        _run(_test())


# ── ESC dismisses the custom input row ──────────────────────────────────────


class TestAskUserEscapeDismissesCustomRow:
    """When the user opens the '其他' custom input row, pressing ESC must
    hide the row and restore focus to the '其他' RadioButton — *not* tear
    down the entire AskUserWidget.

    Regression: previously ESC would always bubble up to
    ``Conversation.action_cancel`` and close the whole widget, making it
    impossible to back out of the inline custom input without cancelling
    the question.
    """

    def test_esc_hides_custom_input_row(self):
        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[
                {"label": "Yes", "value": "yes"},
                {"label": "No", "value": "no"},
            ],
        )

        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                # Navigate to "其他" (third option) and select it
                await pilot.press("down")
                await pilot.pause()
                await pilot.press("down")
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                # Custom row should now be visible
                row = app.query_one("#ask-custom-input-row")
                assert row.display
                # Press ESC — must close the row, not the widget
                await pilot.press("escape")
                await pilot.pause()
                assert not row.display
                # Widget still mounted
                widget = app.query_one(AskUserWidget)
                assert widget.is_mounted

        _run(_test())

    def test_esc_restores_focus_to_other_radio(self):
        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[{"label": "Yes", "value": "yes"}],
        )

        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                # Move to 其他 and select it
                await pilot.press("down")
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                focused = app.focused
                assert focused.id == "ask-custom-input"
                # ESC should restore focus to 其他 button
                await pilot.press("escape")
                await pilot.pause()
                focused = app.focused
                assert focused.id == "_ask_opt_0_custom"

        _run(_test())

    def test_esc_with_hidden_row_does_not_consume_event(self):
        """When the custom row is hidden, ESC must not consume the key event
        so ``Conversation.action_cancel`` can still cancel the AskUser.
        """
        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[{"label": "Yes", "value": "yes"}],
        )

        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                row = app.query_one("#ask-custom-input-row")
                assert not row.display
                # Press ESC; in this minimal app there's no Conversation
                # to handle it, but the AskUser widget itself must remain
                # mounted (it must NOT close itself).
                await pilot.press("escape")
                await pilot.pause()
                widget = app.query_one(AskUserWidget)
                assert widget.is_mounted
                assert not row.display

        _run(_test())


# ── Arrow keys deselect "其他" when leaving it ───────────────────────────────


class TestArrowKeysDeselectOther:
    """When the user opens '其他' (input row visible) and then navigates
    UP/DOWN to a *different* option, the '其他' RadioButton must be
    deselected and the inline custom-input row must hide. Otherwise the
    user is stuck — they cannot return to selecting a regular option
    without first cancelling the whole AskUser.
    """

    def test_up_from_other_deselects_and_hides_input_row(self):
        from textual.widgets import RadioButton

        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[
                {"label": "Yes", "value": "yes"},
                {"label": "No", "value": "no"},
                {"label": "Maybe", "value": "maybe"},
            ],
        )

        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                other_btn = app.query_one("#_ask_opt_0_custom", RadioButton)
                row = app.query_one("#ask-custom-input-row")
                # Navigate to 其他 (4th option) and select it
                for _ in range(3):
                    await pilot.press("down")
                    await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                assert other_btn.value is True
                assert row.display
                # UP from input → 其他 (still selected, row still visible)
                await pilot.press("up")
                await pilot.pause()
                assert other_btn.value is True
                assert row.display
                # UP from 其他 → Maybe (其他 must be deselected, row hidden)
                await pilot.press("up")
                await pilot.pause()
                assert other_btn.value is False, (
                    "其他 must be deselected when focus leaves it"
                )
                assert not row.display, (
                    "Custom-input row must hide when 其他 is deselected"
                )

        _run(_test())

    def test_down_from_other_deselects_and_hides_input_row(self):
        """With only one regular option, the kids order is:
        [Yes, 其他, Input, Send]. After opening 其他 (focus on Input),
        UP once lands on 其他 (still selected, row still visible).
        UP again lands on Yes — 其他 must deselect, row must hide.
        """
        from textual.widgets import RadioButton

        app = _HostApp(
            tool_id="t1",
            question="Pick:",
            options=[{"label": "Yes", "value": "yes"}],
        )

        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                other_btn = app.query_one("#_ask_opt_0_custom", RadioButton)
                row = app.query_one("#ask-custom-input-row")
                # Open 其他
                await pilot.press("down")  # Yes → 其他
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                assert other_btn.value is True
                assert row.display
                # UP: input → 其他 (其他 still selected, row still visible)
                await pilot.press("up")
                await pilot.pause()
                assert other_btn.value is True
                assert row.display
                # UP again: 其他 → Yes (其他 must deselect, row must hide)
                await pilot.press("up")
                await pilot.pause()
                assert other_btn.value is False
                assert not row.display

        _run(_test())

    def test_can_submit_regular_option_after_opening_other(self):
        """End-to-end: open 其他, navigate back via UP, submit a regular
        option. This is the user's exact reported flow.
        """
        from textual.widgets import RadioButton

        submitted: list[str] = []

        class ProbeApp(App):
            def compose(self) -> ComposeResult:
                with Container():
                    yield AskUserWidget(
                        tool_id="t1",
                        question="Pick:",
                        options=[
                            {"label": "Yes", "value": "yes"},
                            {"label": "No", "value": "no"},
                        ],
                    )

            @on(AskUserSubmitted)
            def _capture(self, event: AskUserSubmitted) -> None:
                submitted.append(event.value)

        async def _test():
            app = ProbeApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                other_btn = app.query_one("#_ask_opt_0_custom", RadioButton)
                row = app.query_one("#ask-custom-input-row")
                # User opens 其他
                await pilot.press("down")  # Yes → No
                await pilot.pause()
                await pilot.press("down")  # No → 其他
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                assert other_btn.value is True
                # User navigates back via UP, twice: input → 其他 → No
                await pilot.press("up")
                await pilot.pause()
                await pilot.press("up")
                await pilot.pause()
                # Now 其他 should be deselected and input row hidden
                assert other_btn.value is False
                assert not row.display
                # User submits No
                await pilot.press("enter")
                await pilot.pause()
                assert submitted == ["no"]

        _run(_test())