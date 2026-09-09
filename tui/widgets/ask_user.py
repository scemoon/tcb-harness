from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, NamedTuple

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalGroup
from textual.css.query import NoMatches
from textual.events import Key
from textual.message import Message
from textual.reactive import var
from textual.widget import Widget
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    RadioButton,
    RadioSet,
    Static,
    TabbedContent,
    TabPane,
)


class AskUserSubmitted(Message):
    def __init__(self, value: str, tool_id: str) -> None:
        super().__init__()
        self.value = value
        self.tool_id = tool_id


CUSTOM_VALUE = "__custom__"


class AskUserAnswer(NamedTuple):
    value: str
    label: str
    kind: str | None = None
    option_id: str = ""


def _to_answer(opt: dict) -> AskUserAnswer:
    return AskUserAnswer(
        value=str(opt.get("value", "")),
        label=str(opt.get("label", "")),
        kind=opt.get("kind"),
        option_id=str(opt.get("optionId", opt.get("value", ""))),
    )


@dataclass
class AskRequest:
    tool_id: str
    question: str
    options: list[AskUserAnswer]
    questions: list[dict]
    checkpoint_id: str
    callback: Callable[[str], Any] | None = None


class AskUserWidget(VerticalGroup):
    DEFAULT_CLASSES = "block"

    DEFAULT_CSS = """
    AskUserWidget {
        height: auto;
        padding: 1 1;
        margin: 1 1 1 0;
        background: $surface 80%;
        border: round $primary;
    }
    AskUserWidget RadioSet {
        height: auto;
        margin-bottom: 1;
    }
    AskUserWidget RadioButton {
        margin-bottom: 0;
    }
    AskUserWidget #ask-question {
        margin-bottom: 1;
        color: $text-primary;
    }
    AskUserWidget #ask-custom-input-row {
        height: auto;
        margin-bottom: 1;
    }
    AskUserWidget #ask-custom-input {
        margin-right: 1;
        width: 24;
    }
    AskUserWidget #ask-rollback-row {
        height: auto;
    }
    AskUserWidget .ask-q-options {
        height: auto;
        margin-bottom: 1;
    }
    AskUserWidget #ask-tab-content {
        height: auto;
    }
    AskUserWidget .ask-q-input {
        margin: 1 0 0 0;
        width: 24;
    }
    AskUserWidget #ask-send-custom,
    AskUserWidget #ask-submit-all,
    AskUserWidget #ask-rollback,
    AskUserWidget .ask-send-btn {
        width: auto;
    }
    AskUserWidget .-hidden {
        display: none;
    }
    """

    BINDINGS = [
        Binding("up", "cursor_up", "Up", show=False, priority=True),
        Binding("down", "cursor_down", "Down", show=False, priority=True),
    ]

    cursor_offset: var[int] = var(-1)

    def __init__(
        self,
        tool_id: str,
        question: str = "",
        options: list[dict] | None = None,
        questions: list[dict] | None = None,
        checkpoint_id: str = "",
    ) -> None:
        super().__init__()
        self._tool_id = tool_id
        self._question = question
        self._options = [_to_answer(o) for o in (options or [])]
        self._questions = questions or []
        self._is_multi = bool(self._questions)
        self._answer = ""
        self._done = False
        self._checkpoint_id = checkpoint_id
        self._option_values: dict[str, str] = {}
        self._q_btn_map: dict[str, tuple[int, str]] = {}
        self._multi_selections: dict[str, set[str]] = {}
        self._q_selections: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        if self._question:
            yield Static(self._question, id="ask-question", markup=False)
        if self._is_multi:
            yield from self._compose_multi()
        else:
            yield from self._compose_single()

    def _compose_single(self) -> ComposeResult:
        if self._options:
            yield RadioSet(id="ask-radio-set")

        with Horizontal(id="ask-custom-input-row", classes="-hidden"):
            yield Input(placeholder="✍ 输入自定义方案\u2026", id="ask-custom-input")
            yield Button("发送", variant="primary", id="ask-send-custom")

        with Horizontal(id="ask-rollback-row"):
            if self._checkpoint_id:
                yield Button("Rollback", id="ask-rollback", variant="warning")
            if not self._options:
                yield Button("Submit", variant="primary", id="ask-submit-all")

    async def _build_single_options(self) -> None:
        if not self._options:
            return
        rs = self.query_one("#ask-radio-set", RadioSet)
        for i, opt in enumerate(self._options):
            btn_id = f"_ask_opt_0_{i}"
            await rs.mount(RadioButton(opt.label, id=btn_id))
            self._option_values[btn_id] = opt.value
        custom_btn_id = "_ask_opt_0_custom"
        await rs.mount(RadioButton("其他", id=custom_btn_id))
        self._option_values[custom_btn_id] = CUSTOM_VALUE

    def _compose_multi(self) -> ComposeResult:
        yield TabbedContent(id="ask-tab-content")
        with Horizontal(id="ask-rollback-row"):
            if self._checkpoint_id:
                yield Button("Rollback", id="ask-rollback", variant="warning")
            yield Button("Submit All", variant="primary", id="ask-submit-all")

    async def _build_multi_panes(self) -> None:
        tc = self.query_one("#ask-tab-content", TabbedContent)
        for qi, q in enumerate(self._questions):
            pane_id = f"_ask_pane_{qi}"
            qid = f"_ask_q_{qi}"
            header = q.get("header", f"Q{qi + 1}")
            qtype = q.get("type", "single")
            qopts = q.get("options", [])

            pane = TabPane(header, id=pane_id)
            await tc.add_pane(pane)

            if qtype == "multiple" and qopts:
                for oi, opt in enumerate(qopts):
                    cb = Checkbox(
                        f" {opt.get('label', '')}", id=f"{qid}_chk_{oi}"
                    )
                    await pane.mount(cb)
                self._multi_selections.setdefault(qid, set())
            elif qtype == "confirm":
                await pane.mount(
                    Button(
                        "Yes",
                        id=f"{qid}_yes",
                        variant="primary",
                        classes="ask-opt-btn",
                    )
                )
                await pane.mount(
                    Button("No", id=f"{qid}_no", classes="ask-opt-btn")
                )
                self._q_btn_map[f"{qid}_yes"] = (qi, "yes")
                self._q_btn_map[f"{qid}_no"] = (qi, "no")
            elif qopts:
                rs = RadioSet(id=f"{qid}_radios")
                await pane.mount(rs)
                for oi, opt in enumerate(qopts):
                    btn_id = f"{qid}_opt_{oi}"
                    value = opt.get("value", "")
                    await rs.mount(
                        RadioButton(opt.get("label", ""), id=btn_id)
                    )
                    self._option_values[btn_id] = value
                    self._q_btn_map[btn_id] = (qi, value)
                custom_btn_id = f"{qid}_opt_custom"
                await rs.mount(
                    RadioButton("其他", id=custom_btn_id)
                )
                self._q_btn_map[custom_btn_id] = (qi, CUSTOM_VALUE)
                self._option_values[custom_btn_id] = CUSTOM_VALUE
                wrap = Horizontal(id=f"{qid}_custom-row", classes="-hidden")
                await pane.mount(wrap)
                await wrap.mount(
                    Input(
                        placeholder="✍ 输入自定义方案\u2026",
                        id=f"{qid}_input",
                        classes="ask-q-input",
                    )
                )
                await wrap.mount(
                    Button(
                        "发送",
                        variant="primary",
                        id=f"{qid}_send",
                        classes="ask-send-btn",
                    )
                )
            else:
                wrap = Horizontal(id=f"{qid}_custom-row")
                await pane.mount(wrap)
                await wrap.mount(
                    Input(
                        placeholder="✍ 输入自定义方案\u2026",
                        id=f"{qid}_input",
                        classes="ask-q-input",
                    )
                )
                await wrap.mount(
                    Button(
                        "发送",
                        variant="primary",
                        id=f"{qid}_send",
                        classes="ask-send-btn",
                    )
                )

        tc.active = "_ask_pane_0"

    async def on_mount(self) -> None:
        if self._is_multi:
            await self._build_multi_panes()
            try:
                self.query_one("RadioButton", RadioButton).focus()
                return
            except NoMatches:
                pass
            try:
                self.query_one(".ask-opt-btn", Button).focus()
                return
            except NoMatches:
                pass
            try:
                self.query_one(".ask-q-input", Input).focus()
                return
            except NoMatches:
                self.focus()
        else:
            if self._options:
                await self._build_single_options()
                try:
                    self.query_one("RadioButton", RadioButton).focus()
                except NoMatches:
                    self.focus()
            else:
                try:
                    self.query_one("#ask-custom-input", Input).focus()
                except NoMatches:
                    self.focus()

    def _cursor_children(self) -> list[Widget]:
        return list(self.query("RadioButton, Input, Button"))

    def block_cursor_clear(self) -> None:
        self.cursor_offset = -1

    def block_cursor_up(self) -> Widget | None:
        kids = self._cursor_children()
        if not kids:
            return None
        if self.cursor_offset == -1:
            self.cursor_offset = len(kids) - 1
        else:
            self.cursor_offset -= 1
        if self.cursor_offset < 0:
            self.cursor_offset = -1
            return None
        try:
            return kids[self.cursor_offset]
        except IndexError:
            return None

    def block_cursor_down(self) -> Widget | None:
        kids = self._cursor_children()
        if not kids:
            return None
        if self.cursor_offset == -1:
            self.cursor_offset = 0
        else:
            self.cursor_offset += 1
        if self.cursor_offset >= len(kids):
            self.cursor_offset = -1
            return None
        try:
            return kids[self.cursor_offset]
        except IndexError:
            return None

    def get_cursor_block(self) -> Widget | None:
        if self.cursor_offset == -1:
            return None
        try:
            return self._cursor_children()[self.cursor_offset]
        except IndexError:
            return None

    def block_select(self, widget: Widget) -> None:
        try:
            self.cursor_offset = self._cursor_children().index(widget)
        except ValueError:
            pass

    def action_cursor_up(self) -> None:
        """Internal keyboard handler — advances focus within the widget.

        Tracks an internal cursor (separate from ``cursor_offset``) so the
        ``BlockProtocol`` contract remains predictable when the host
        enters the block via ``block_cursor_down``.

        When the focus moves away from the "其他" RadioButton (e.g. user
        navigates UP to a regular option), the inline custom-input row is
        hidden and "其他" is deselected so the user can pick a normal
        option without first cancelling the inline input.
        """
        kids = self._cursor_children()
        if not kids:
            return
        focused = self.app.focused
        try:
            current = kids.index(focused) if focused in kids else -1
        except ValueError:
            current = -1
        if current < 0:
            new_idx = len(kids) - 1
        else:
            new_idx = max(0, current - 1)
        self._dismiss_custom_row_if_leaving_other(
            current_idx=current, new_idx=new_idx, kids=kids
        )
        kids[new_idx].focus()

    def action_cursor_down(self) -> None:
        """Internal keyboard handler — advances focus within the widget."""
        kids = self._cursor_children()
        if not kids:
            return
        focused = self.app.focused
        try:
            current = kids.index(focused) if focused in kids else -1
        except ValueError:
            current = -1
        if current < 0:
            new_idx = 0
        else:
            new_idx = min(len(kids) - 1, current + 1)
        self._dismiss_custom_row_if_leaving_other(
            current_idx=current, new_idx=new_idx, kids=kids
        )
        kids[new_idx].focus()

    def _dismiss_custom_row_if_leaving_other(
        self, current_idx: int, new_idx: int, kids: list[Widget]
    ) -> None:
        """If focus is leaving the '其他' RadioButton for a *different*
        option, hide the inline custom-input row and select the new option.

        RadioSet's contract is "exactly one button selected at any time".
        To deselect '其他' we must select the destination button — this
        also has the side effect of pre-selecting it, which matches the
        user's intent: they navigated to a regular option to pick it.

        Single-question mode only (multi-question tabs hide their own
        rows independently).
        """
        if self._is_multi:
            return
        if current_idx < 0:
            return
        if not (0 <= current_idx < len(kids)):
            return
        current_widget = kids[current_idx]
        if not (
            isinstance(current_widget, RadioButton)
            and current_widget.id == "_ask_opt_0_custom"
        ):
            return
        if new_idx == current_idx:
            return
        # Selecting a different RadioButton triggers RadioSet's
        # _on_radio_button_changed which deselects '其他' atomically.
        new_widget = kids[new_idx]
        if isinstance(new_widget, RadioButton):
            new_widget.value = True
        try:
            row = self.query_one("#ask-custom-input-row")
            row.display = False
        except NoMatches:
            pass

    def on_key(self, event: Key) -> None:
        """ESC dismisses the visible custom-input row before bubbling to the
        host's cancel handler.

        Without this, ``Conversation.action_cancel`` would tear down the
        entire AskUserWidget when the user merely wanted to back out of
        the inline "其他" custom input.
        """
        if event.key != "escape":
            return
        try:
            row = self.query_one("#ask-custom-input-row")
        except NoMatches:
            return
        if not row.display:
            return
        row.display = False
        event.stop()
        event.prevent_default()
        # Selecting any other radio would deselect "其他" via the
        # RadioSet contract, but if the user has no other radio to pick
        # the row stays open. Force-close by hiding and refocusing.
        try:
            custom_btn = self.query_one("#_ask_opt_0_custom", RadioButton)
            custom_btn.focus()
        except NoMatches:
            pass

    @on(RadioSet.Changed, "#ask-radio-set")
    async def handle_radio_changed(self, event: RadioSet.Changed) -> None:
        if self._is_multi:
            return
        btn_id = event.pressed.id or ""
        value = self._option_values.get(btn_id, "")
        if value == CUSTOM_VALUE:
            self.query_one("#ask-custom-input-row", Horizontal).display = True
            self.query_one("#ask-custom-input", Input).focus()
        elif value:
            await self._finish(value)

    @on(Button.Pressed, "#ask-rollback")
    def handle_rollback(self) -> None:
        self.post_message(AskUserSubmitted("__rollback__", self._tool_id))

    @on(Button.Pressed, "#ask-send-custom")
    async def handle_send_custom(self) -> None:
        value = self.query_one("#ask-custom-input", Input).value.strip()
        if value:
            await self._finish(value)

    @on(Input.Submitted, "#ask-custom-input")
    async def handle_custom_input_submitted(self) -> None:
        value = self.query_one("#ask-custom-input", Input).value.strip()
        if value:
            await self._finish(value)

    @on(Button.Pressed, "#ask-submit-all")
    async def handle_submit_all(self) -> None:
        if not self._is_multi:
            return
        answers: dict[str, Any] = {}
        for qi, q in enumerate(self._questions):
            qtype = q.get("type", "single")
            qid = f"_ask_q_{qi}"
            if qtype == "multiple":
                selected: list[str] = []
                for chk in self.query(f"#{qid}_chk_"):
                    if isinstance(chk, Checkbox) and chk.value:
                        label = chk.label.plain if hasattr(chk, "label") else ""
                        selected.append(label.strip())
                answers[str(qi)] = selected if selected else ""
            elif qtype == "confirm":
                val = self._q_selections.get(qid, "")
                if not val:
                    try:
                        inp = self.query_one(f"#{qid}_input", Input)
                        val = inp.value.strip()
                    except Exception:
                        pass
                answers[str(qi)] = val or ""
            else:
                val = self._q_selections.get(qid, "")
                if not val:
                    try:
                        inp = self.query_one(f"#{qid}_input", Input)
                        val = inp.value.strip()
                    except Exception:
                        pass
                answers[str(qi)] = val or ""

        unanswered = [
            str(i) for i, q in enumerate(self._questions)
            if not answers.get(str(i))
        ]
        if unanswered:
            return
        await self._finish(json.dumps(answers))

    @on(Button.Pressed, ".ask-opt-btn")
    def handle_q_option(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        entry = self._q_btn_map.get(btn_id)
        if entry:
            q_idx, value = entry
            qid = f"_ask_q_{q_idx}"
            self._q_selections[qid] = value

    @on(RadioSet.Changed)
    def handle_q_radio_changed(self, event: RadioSet.Changed) -> None:
        btn_id = event.pressed.id or ""
        if not btn_id.startswith("_ask_q_"):
            return
        entry = self._q_btn_map.get(btn_id)
        if not entry:
            return
        q_idx, value = entry
        qid = f"_ask_q_{q_idx}"
        if value == CUSTOM_VALUE:
            self.query_one(f"#{qid}_custom-row", Horizontal).display = True
            self.query_one(f"#{qid}_input", Input).focus()
        else:
            self._q_selections[qid] = value

    @on(Button.Pressed, ".ask-send-btn")
    def handle_q_send(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        qid = btn_id.rsplit("_send", 1)[0]
        try:
            inp = self.query_one(f"#{qid}_input", Input)
            val = inp.value.strip()
            if val:
                self._q_selections[qid] = val
        except NoMatches:
            pass

    @on(Input.Submitted, ".ask-q-input")
    def handle_q_input_submitted(self, event: Input.Submitted) -> None:
        inp_id = event.input.id or ""
        if inp_id.startswith("_ask_q_") and inp_id.endswith("_input"):
            qid = inp_id.rsplit("_input", 1)[0]
            val = event.value.strip()
            if val:
                self._q_selections[qid] = val

    async def _finish(self, value: str) -> None:
        self._answer = value
        self._done = True
        self.post_message(AskUserSubmitted(value, self._tool_id))
        await self.remove()


__all__ = [
    "AskUserSubmitted",
    "AskUserAnswer",
    "AskRequest",
    "AskUserWidget",
    "CUSTOM_VALUE",
]