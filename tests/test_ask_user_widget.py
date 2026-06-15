"""Tests for the AskUserWidget: rendering, options, input, and submission.

Verifies:
- Question text is displayed.
- Options are rendered as buttons.
- Input and Send/Cancel buttons are present.
- Clicking an option posts AskUserSubmitted with correct value.
- Typing in Input and pressing Enter posts AskUserSubmitted.
- After submission, widget shows ✅ done state.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Button, Checkbox, Input, Static

from tui.widgets.ask_user import AskUserSubmitted, AskUserWidget


@dataclass
class _SubmissionCapture:
    values: list[str] = field(default_factory=list)
    tool_ids: list[str] = field(default_factory=list)


class _ProbeApp(App):
    """Minimal app to host AskUserWidget for testing."""

    def __init__(self, question: str, options: list[dict]) -> None:
        super().__init__()
        self.question = question
        self.options = options
        self.capture = _SubmissionCapture()

    def compose(self) -> ComposeResult:
        with Container():
            yield AskUserWidget(
                tool_id="test-tool-1",
                question=self.question,
                options=self.options,
            )

    @on(AskUserSubmitted)
    def on_ask_user_submitted(self, event: AskUserSubmitted) -> None:
        self.capture.values.append(event.value)
        self.capture.tool_ids.append(event.tool_id)


def _run(coro):
    return asyncio.run(coro)


class TestAskUserWidgetRendering:
    def test_question_displayed(self):
        """The question text must appear as a Static widget."""
        app = _ProbeApp("Continue?", [])
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                statics = app.query(Static)
                texts = [str(s.render()).strip() for s in statics]
                assert any("Continue?" in t for t in texts)
        _run(_test())

    def test_input_and_buttons_present(self):
        """Input, Send and Cancel widgets must exist."""
        app = _ProbeApp("Continue?", [])
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                assert app.query(Input)
                buttons = {b.id for b in app.query(Button)}
                assert "ask-send" in buttons
                assert "ask-cancel" in buttons
        _run(_test())

    def test_options_rendered_as_buttons(self):
        """Options must be rendered as Buttons with safe ids."""
        options = [
            {"label": "Yes", "value": "yes", "key": "y"},
            {"label": "No", "value": "no"},
        ]
        app = _ProbeApp("Proceed?", options)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                buttons = app.query(Button)
                btn_ids = [b.id for b in buttons if b.id and b.id.startswith("_ask_opt_")]
                assert len(btn_ids) == 2
        _run(_test())

    def test_no_options_skips_option_buttons(self):
        """When options is empty, no option buttons are rendered."""
        app = _ProbeApp("Type:", [])
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                opt_buttons = [b for b in app.query(Button) if b.id and b.id.startswith("_ask_opt_")]
                assert len(opt_buttons) == 0
        _run(_test())


class TestAskUserWidgetSubmission:
    def test_typing_and_pressing_enter_submits(self):
        """Enter on Input posts AskUserSubmitted with the typed value."""
        app = _ProbeApp("Your name?", [])
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                inp = app.query(Input).first()
                inp.value = "Alice"
                await inp.action_submit()
                await pilot.pause()
                assert len(app.capture.values) == 1
                assert app.capture.values[0] == "Alice"
                assert app.capture.tool_ids[0] == "test-tool-1"
        _run(_test())

    def test_clicking_option_submits(self):
        """Clicking an option button posts AskUserSubmitted with its value."""
        options = [{"label": "Option A", "value": "a"}]
        app = _ProbeApp("Choose:", options)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                btn = app.query_one("#_ask_opt_0", Button)
                btn.press()
                await pilot.pause()
                assert len(app.capture.values) == 1
                assert app.capture.values[0] == "a"
        _run(_test())

    def test_clicking_cancel_submits_cancel(self):
        """Cancel button posts AskUserSubmitted with __cancel__."""
        app = _ProbeApp("Go?", [])
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                cancel_btn = app.query_one("#ask-cancel", Button)
                cancel_btn.press()
                await pilot.pause()
                assert len(app.capture.values) == 1
                assert app.capture.values[0] == "__cancel__"
        _run(_test())

    def test_after_submit_shows_done_state(self):
        """After submission, widget shows ✅ prefix and hides input/options."""
        app = _ProbeApp("Done?", [])
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                inp = app.query(Input).first()
                inp.value = "yes"
                await inp.action_submit()
                await pilot.pause()
                await pilot.pause()
                static_texts = [str(s.render()) for s in app.query(Static) if s.id == "ask-answer-done"]
                assert any("✅" in t for t in static_texts)
        _run(_test())


class _ProbeAppMulti(App):
    """Minimal app to host AskUserWidget in multi-question mode."""

    def __init__(self, questions: list[dict]) -> None:
        super().__init__()
        self.questions = questions
        self.capture = _SubmissionCapture()

    def compose(self) -> ComposeResult:
        with Container():
            yield AskUserWidget(
                tool_id="test-multi-1",
                questions=self.questions,
            )

    @on(AskUserSubmitted)
    def on_ask_user_submitted(self, event: AskUserSubmitted) -> None:
        self.capture.values.append(event.value)
        self.capture.tool_ids.append(event.tool_id)


class TestAskUserMultiQuestion:
    """Tests for multi-question mode."""

    def test_multi_renders_sections(self):
        """Each question must be rendered in a section with header."""
        questions = [
            {"header": "Q1", "question": "First?", "type": "single"},
            {"header": "Q2", "question": "Second?", "type": "confirm"},
        ]
        app = _ProbeAppMulti(questions)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                statics = app.query(Static)
                texts = [str(s.render()) for s in statics]
                assert any("Q1" in t for t in texts)
                assert any("Q2" in t for t in texts)
                assert any("First?" in t for t in texts)
                assert any("Second?" in t for t in texts)
        _run(_test())

    def test_multi_has_submit_all_button(self):
        """Submit All button must be present in multi-question mode."""
        questions = [{"question": "Only?", "type": "single"}]
        app = _ProbeAppMulti(questions)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                btn_ids = {b.id for b in app.query(Button)}
                assert "ask-submit-all" in btn_ids
        _run(_test())

    def test_multi_confirm_type_has_yes_no(self):
        """Confirm type questions must show Yes/No buttons."""
        questions = [{"question": "Proceed?", "type": "confirm"}]
        app = _ProbeAppMulti(questions)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                btn_ids = {b.id for b in app.query(Button)}
                assert any("_yes" in (bid or "") for bid in btn_ids)
                assert any("_no" in (bid or "") for bid in btn_ids)
        _run(_test())

    def test_multi_single_type_has_custom_input(self):
        """Single type questions must include a custom answer Input."""
        questions = [{"question": "Name?", "type": "single"}]
        app = _ProbeAppMulti(questions)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                inputs = app.query(Input)
                assert len(inputs) >= 1
        _run(_test())

    def test_multi_submit_all_returns_json(self):
        """Submit All must return a JSON-encoded dict of answers."""
        questions = [
            {"question": "Color?", "type": "single",
             "options": [{"label": "Red", "value": "red"}, {"label": "Blue", "value": "blue"}]},
            {"question": "Confirm?", "type": "confirm"},
        ]
        app = _ProbeAppMulti(questions)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                # Select option for Q0
                opt_btns = [b for b in app.query(Button) if b.id and b.id.endswith("_opt_0")]
                if opt_btns:
                    opt_btns[0].press()
                    await pilot.pause()
                # Click Yes for Q1
                yes_btns = [b for b in app.query(Button) if b.id and b.id.endswith("_yes")]
                if yes_btns:
                    yes_btns[0].press()
                    await pilot.pause()
                # Submit
                submit = app.query_one("#ask-submit-all", Button)
                submit.press()
                await pilot.pause()
                assert len(app.capture.values) == 1
                import json
                parsed = json.loads(app.capture.values[0])
                assert isinstance(parsed, dict)
        _run(_test())

    def test_multi_submit_requires_all_answered(self):
        """Submit All must not fire when some questions are unanswered."""
        questions = [
            {"question": "Q1?", "type": "single"},
            {"question": "Q2?", "type": "single"},
        ]
        app = _ProbeAppMulti(questions)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                submit = app.query_one("#ask-submit-all", Button)
                submit.press()
                await pilot.pause()
                # Should NOT submit because Q0 and Q1 are unanswered
                assert len(app.capture.values) == 0
        _run(_test())

    def test_multi_cancel_still_works(self):
        """Cancel must work in multi-question mode."""
        questions = [{"question": "Q?", "type": "single"}]
        app = _ProbeAppMulti(questions)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                cancel = app.query_one("#ask-cancel", Button)
                cancel.press()
                await pilot.pause()
                assert len(app.capture.values) == 1
                assert app.capture.values[0] == "__cancel__"
        _run(_test())

    def test_multi_multiple_type_with_checkboxes(self):
        """Multiple type questions must render Checkboxes."""
        questions = [
            {"question": "Pick?", "type": "multiple",
             "options": [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}]},
        ]
        app = _ProbeAppMulti(questions)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                checkboxes = app.query(Checkbox)
                assert len(checkboxes) == 2
                texts = [str(c.label).strip() for c in checkboxes]
                assert any("A" in t for t in texts)
                assert any("B" in t for t in texts)
        _run(_test())
