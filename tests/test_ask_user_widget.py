"""Tests for the AskUserWidget: RadioSet options, 其他 as last option, and custom input.

Verifies:
- Options rendered as RadioSet + RadioButton (including 其他 as last option).
- Selecting 其他 shows custom input row.
- Selecting normal radio posts AskUserSubmitted with correct value.
- Typing in custom input and pressing Enter/发送 posts AskUserSubmitted.
- Multi-question: 其他 as last RadioButton per pane, custom input shown when selected.
- Submit All posts JSON of answers.
- Rollback button posts __rollback__.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Button, Checkbox, Input, RadioButton, RadioSet, Tabs, TabbedContent

from tui.widgets.ask_user import AskUserSubmitted, AskUserWidget, CUSTOM_VALUE


@dataclass
class _SubmissionCapture:
    values: list[str] = field(default_factory=list)
    tool_ids: list[str] = field(default_factory=list)


class _ProbeApp(App):
    """Minimal app to host AskUserWidget for testing (single question)."""

    def __init__(self, question: str = "", options: list[dict] | None = None,
                 checkpoint_id: str = "") -> None:
        super().__init__()
        self.question = question
        self.options = options or []
        self.checkpoint_id = checkpoint_id
        self.capture = _SubmissionCapture()

    def compose(self) -> ComposeResult:
        with Container():
            yield AskUserWidget(
                tool_id="test-tool-1",
                question=self.question,
                options=self.options,
                checkpoint_id=self.checkpoint_id,
            )

    @on(AskUserSubmitted)
    def on_ask_user_submitted(self, event: AskUserSubmitted) -> None:
        self.capture.values.append(event.value)
        self.capture.tool_ids.append(event.tool_id)


class _ProbeAppMulti(App):
    """Minimal app to host AskUserWidget in multi-question mode."""

    def __init__(self, questions: list[dict], checkpoint_id: str = "") -> None:
        super().__init__()
        self.questions = questions
        self.checkpoint_id = checkpoint_id
        self.capture = _SubmissionCapture()

    def compose(self) -> ComposeResult:
        with Container():
            yield AskUserWidget(
                tool_id="test-multi-1",
                questions=self.questions,
                checkpoint_id=self.checkpoint_id,
            )

    @on(AskUserSubmitted)
    def on_ask_user_submitted(self, event: AskUserSubmitted) -> None:
        self.capture.values.append(event.value)
        self.capture.tool_ids.append(event.tool_id)


def _run(coro):
    return asyncio.run(coro)


# ── Single question: rendering ────────────────────────────────────────────────


class TestAskUserSingleRendering:
    def test_options_rendered_as_radio_set(self):
        """Options must be rendered as a RadioSet with RadioButton children."""
        options = [
            {"label": "Yes", "value": "yes"},
            {"label": "No", "value": "no"},
        ]
        app = _ProbeApp("Proceed?", options)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                rs = app.query_one("#ask-radio-set", RadioSet)
                radios = list(rs.query(RadioButton))
                # 2 options + 其他 = 3
                assert len(radios) == 3
                ids = {r.id for r in radios}
                assert ids == {"_ask_opt_0_0", "_ask_opt_0_1", "_ask_opt_0_custom"}
                # wire values are stored in widget._option_values (button
                # ids → wire value), not on RadioButton.value itself.
                widget = app.query_one(AskUserWidget)
                assert widget._option_values["_ask_opt_0_0"] == "yes"
                assert widget._option_values["_ask_opt_0_1"] == "no"
                assert widget._option_values["_ask_opt_0_custom"] == CUSTOM_VALUE
        _run(_test())

    def test_no_options_skips_radio_set(self):
        """When options is empty, no RadioSet is rendered."""
        app = _ProbeApp("Type:", [])
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                radios = list(app.query(RadioSet))
                assert len(radios) == 0
        _run(_test())

    def test_other_option_is_last_radio(self):
        """其他 must be the last RadioButton in the set."""
        options = [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}]
        app = _ProbeApp("Pick?", options)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                rs = app.query_one("#ask-radio-set", RadioSet)
                radios = list(rs.query(RadioButton))
                assert radios[-1].label.plain == "其他"
                widget = app.query_one(AskUserWidget)
                assert widget._option_values[radios[-1].id] == CUSTOM_VALUE
        _run(_test())

    def test_custom_input_row_initially_hidden(self):
        """Custom input row must be hidden by default."""
        options = [{"label": "Yes", "value": "yes"}]
        app = _ProbeApp("Proceed?", options)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                row = app.query_one("#ask-custom-input-row")
                assert not row.display
        _run(_test())

    def test_rollback_button_present_when_checkpoint(self):
        """Rollback button must be present when checkpoint_id is set."""
        options = [{"label": "Yes", "value": "yes"}]
        app = _ProbeApp("Proceed?", options, checkpoint_id="cp-1")
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                rb = app.query_one("#ask-rollback", Button)
                assert rb is not None
        _run(_test())

    def test_no_submit_button_when_options_exist(self):
        """Single question with options must NOT show a Submit button."""
        options = [{"label": "Yes", "value": "yes"}]
        app = _ProbeApp("Proceed?", options)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                submit = [b for b in app.query(Button) if b.id == "ask-submit-all"]
                assert len(submit) == 0
        _run(_test())


# ── Single question: interaction ─────────────────────────────────────────────


class TestAskUserSingleSubmission:
    def test_selecting_radio_submits(self):
        """Selecting a normal radio button posts AskUserSubmitted with its value."""
        options = [{"label": "Option A", "value": "a"}]
        app = _ProbeApp("Choose:", options)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                rs = app.query_one("#ask-radio-set", RadioSet)
                radios = list(rs.query(RadioButton))
                # Select first (non-其他) option
                radios[0].value = True
                await pilot.pause()
                assert len(app.capture.values) == 1
                assert app.capture.values[0] == "a"
        _run(_test())

    def test_selecting_other_shows_input(self):
        """Selecting 其他 reveals the custom input row."""
        options = [{"label": "Yes", "value": "yes"}]
        app = _ProbeApp("Proceed?", options)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                rs = app.query_one("#ask-radio-set", RadioSet)
                radios = list(rs.query(RadioButton))
                # Select 其他 (last)
                radios[-1].value = True
                await pilot.pause()
                row = app.query_one("#ask-custom-input-row")
                assert row.display
                inp = app.query_one("#ask-custom-input", Input)
                assert inp.display
                assert inp.has_focus
        _run(_test())

    def test_typing_in_custom_input_submits(self):
        """Typing in the custom input and pressing 发送 posts the value."""
        options = [{"label": "Yes", "value": "yes"}]
        app = _ProbeApp("Proceed?", options)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                rs = app.query_one("#ask-radio-set", RadioSet)
                radios = list(rs.query(RadioButton))
                radios[-1].value = True
                await pilot.pause()
                inp = app.query_one("#ask-custom-input", Input)
                inp.value = "custom answer"
                send_btn = app.query_one("#ask-send-custom", Button)
                send_btn.press()
                await pilot.pause()
                assert len(app.capture.values) == 1
                assert app.capture.values[0] == "custom answer"
        _run(_test())

    def test_typing_and_pressing_enter_submits(self):
        """Enter on custom Input posts AskUserSubmitted with the typed value."""
        options = [{"label": "Yes", "value": "yes"}]
        app = _ProbeApp("Proceed?", options)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                rs = app.query_one("#ask-radio-set", RadioSet)
                radios = list(rs.query(RadioButton))
                radios[-1].value = True
                await pilot.pause()
                inp = app.query_one("#ask-custom-input", Input)
                inp.value = "Alice"
                await inp.action_submit()
                await pilot.pause()
                assert len(app.capture.values) == 1
                assert app.capture.values[0] == "Alice"
        _run(_test())

    def test_rollback_posts_rollback_marker(self):
        """Rollback button posts __rollback__."""
        options = [{"label": "Yes", "value": "yes"}]
        app = _ProbeApp("Proceed?", options, checkpoint_id="cp-1")
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                app.query_one("#ask-rollback", Button).press()
                await pilot.pause()
                assert len(app.capture.values) == 1
                assert app.capture.values[0] == "__rollback__"
        _run(_test())

    def test_enter_key_submits_first_option(self):
        """Pressing Enter on the focused RadioButton must submit that option
        (Regression: RadioButton's value being constructor-value made Enter
        a no-op because the button was already 'selected').
        """
        options = [{"label": "Yes", "value": "yes"}]
        app = _ProbeApp("Proceed?", options)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                assert len(app.capture.values) == 1
                assert app.capture.values[0] == "yes"
        _run(_test())

    def test_arrow_then_enter_submits_target_option(self):
        """Down arrow then Enter must submit the focused (target) option."""
        options = [
            {"label": "Yes", "value": "yes"},
            {"label": "No", "value": "no"},
        ]
        app = _ProbeApp("Proceed?", options)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("down")
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                assert len(app.capture.values) == 1
                assert app.capture.values[0] == "no"
        _run(_test())


# ── Multi question ────────────────────────────────────────────────────────────


class TestAskUserMultiQuestion:
    def test_multi_renders_tabs(self):
        """Multi-question must render Tabs with correct number of tabs."""
        questions = [
            {"header": "Q1", "question": "First?", "type": "single"},
            {"header": "Q2", "question": "Second?", "type": "single"},
        ]
        app = _ProbeAppMulti(questions)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                tabs = list(app.query(Tabs))
                assert len(tabs) == 1
                tab_children = list(tabs[0].query("Tab"))
                assert len(tab_children) == 2
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

    def test_multi_single_type_has_radio_set(self):
        """Single type questions must include a RadioSet."""
        questions = [{"question": "Name?", "type": "single", "options": [{"label": "A", "value": "a"}]}]
        app = _ProbeAppMulti(questions)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                radios = list(app.query(RadioSet))
                assert len(radios) == 1
        _run(_test())

    def test_multi_single_type_has_other_as_last_option(self):
        """Single type RadioSet must have 其他 as last RadioButton."""
        questions = [{"question": "Color?", "type": "single",
                     "options": [{"label": "Red", "value": "red"}, {"label": "Blue", "value": "blue"}]}]
        app = _ProbeAppMulti(questions)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                rs = app.query_one("#_ask_q_0_radios", RadioSet)
                radios = list(rs.query(RadioButton))
                assert radios[-1].label.plain == "其他"
                widget = app.query_one(AskUserWidget)
                assert widget._option_values[radios[-1].id] == CUSTOM_VALUE
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
                rs = app.query_one("#_ask_q_0_radios", RadioSet)
                radios = list(rs.query(RadioButton))
                radios[0].value = True
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
                assert len(app.capture.values) == 0
        _run(_test())

    def test_multi_submit_all_works(self):
        """Submit All must work when all questions have answers."""
        questions = [{"question": "Q?", "type": "single", "options": [{"label": "A", "value": "a"}]}]
        app = _ProbeAppMulti(questions)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                rs = app.query_one("#_ask_q_0_radios", RadioSet)
                radios = list(rs.query(RadioButton))
                radios[0].value = True
                await pilot.pause()
                submit = app.query_one("#ask-submit-all", Button)
                submit.press()
                await pilot.pause()
                assert len(app.capture.values) == 1
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
        _run(_test())

    def test_multi_other_option_shows_custom_row(self):
        """Selecting 其他 shows the custom input row for that pane."""
        questions = [
            {"question": "Color?", "type": "single",
             "options": [{"label": "Red", "value": "red"}]},
        ]
        app = _ProbeAppMulti(questions)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                rs = app.query_one("#_ask_q_0_radios", RadioSet)
                radios = list(rs.query(RadioButton))
                # Select 其他 (last)
                radios[-1].value = True
                await pilot.pause()
                row = app.query_one("#_ask_q_0_custom-row")
                assert row.display
        _run(_test())

    def test_multi_no_options_shows_input(self):
        """A question without options shows its input directly (always visible)."""
        questions = [{"question": "Name?", "type": "single"}]
        app = _ProbeAppMulti(questions)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                inp = app.query_one("#_ask_q_0_input", Input)
                assert inp.display
        _run(_test())

    def test_multi_custom_expands_input(self):
        """Selecting 其他 in a tab reveals its custom input row."""
        questions = [
            {"question": "Color?", "type": "single",
             "options": [{"label": "Red", "value": "red"}]},
        ]
        app = _ProbeAppMulti(questions)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                rs = app.query_one("#_ask_q_0_radios", RadioSet)
                radios = list(rs.query(RadioButton))
                radios[-1].value = True
                await pilot.pause()
                row = app.query_one("#_ask_q_0_custom-row")
                assert row.display
        _run(_test())

    def test_multi_input_submitted_via_submit_all(self):
        """Custom text in a question's input is picked up by Submit All."""
        questions = [
            {"question": "Color?", "type": "single",
             "options": [{"label": "Red", "value": "red"}]},
        ]
        app = _ProbeAppMulti(questions)
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                rs = app.query_one("#_ask_q_0_radios", RadioSet)
                radios = list(rs.query(RadioButton))
                radios[-1].value = True
                await pilot.pause()
                inp = app.query_one("#_ask_q_0_input", Input)
                inp.value = "green"
                app.query_one("#ask-submit-all", Button).press()
                await pilot.pause()
                assert len(app.capture.values) == 1
                import json
                parsed = json.loads(app.capture.values[0])
                assert parsed["0"] == "green"
        _run(_test())

    def test_multi_rollback_present(self):
        """Rollback button present when checkpoint_id is set."""
        questions = [{"question": "Q?", "type": "single"}]
        app = _ProbeAppMulti(questions, checkpoint_id="cp-1")
        async def _test():
            async with app.run_test() as pilot:
                await pilot.pause()
                rb = app.query_one("#ask-rollback", Button)
                assert rb is not None
        _run(_test())
