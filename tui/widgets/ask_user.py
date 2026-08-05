from __future__ import annotations

import json

from textual.app import ComposeResult
from textual import on
from textual.containers import Horizontal, VerticalGroup
from textual.message import Message
from textual.widgets import (
    Button, Checkbox, Input, RadioButton, RadioSet, TabbedContent, TabPane,
)
from textual.css.query import NoMatches


class AskUserSubmitted(Message):
    def __init__(self, value: str, tool_id: str) -> None:
        super().__init__()
        self.value = value
        self.tool_id = tool_id


CUSTOM_VALUE = "__custom__"


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
    AskUserWidget .ask-q-section {
        height: auto;
        margin-bottom: 1;
        padding: 0;
    }
    AskUserWidget .ask-q-options {
        height: auto;
        margin-bottom: 1;
    }
    AskUserWidget #ask-tabs {
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

    def __init__(
        self, tool_id: str, question: str = "",
        options: list[dict] | None = None,
        questions: list[dict] | None = None,
        checkpoint_id: str = "",
    ) -> None:
        super().__init__()
        self._tool_id = tool_id
        self._question = question
        self._options = options or []
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
        if self._is_multi:
            yield from self._compose_multi()
        else:
            yield from self._compose_single()

    # ── Single question (no Tab) ─────────────────────────────────────────────

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

    # ── Multi question (Tabbed) ─────────────────────────────────────────────

    def _compose_multi(self) -> ComposeResult:
        yield TabbedContent(id="ask-tab-content")

    async def _build_multi_panes(self) -> None:
        tc = self.query_one("#ask-tab-content", TabbedContent)
        for qi, q in enumerate(self._questions):
            pane_id = f"_ask_pane_{qi}"
            pane, to_mount = self._make_tab_pane(qi, q, pane_id)
            await tc.add_pane(pane)
            for item in to_mount:
                widget_or_wrap, children = item
                if children is not None:
                    await pane.mount(widget_or_wrap)
                    for child in children:
                        await widget_or_wrap.mount(child)
                else:
                    await pane.mount(widget_or_wrap)

        rollback_row = Horizontal(id="ask-rollback-row")
        await self.mount(rollback_row)
        if self._checkpoint_id:
            await rollback_row.mount(Button("Rollback", id="ask-rollback", variant="warning"))
        await rollback_row.mount(Button("Submit All", variant="primary", id="ask-submit-all"))

    def _make_tab_pane(self, qi: int, q: dict, pane_id: str) -> tuple[TabPane, list]:
        qtype = q.get("type", "single")
        qopts = q.get("options", [])
        qid = f"_ask_q_{qi}"
        header = q.get("header", f"Q{qi + 1}")

        pane = TabPane(header, id=pane_id)
        to_mount: list = []

        if qtype == "multiple" and qopts:
            for oi, opt in enumerate(qopts):
                to_mount.append((
                    Checkbox(f" {opt.get('label', '')}", id=f"{qid}_chk_{oi}"),
                    None,
                ))
                self._multi_selections.setdefault(qid, set())
        elif qtype == "confirm":
            to_mount.append((
                VerticalGroup(
                    Button("Yes", id=f"{qid}_yes", variant="primary", classes="ask-opt-btn"),
                    Button("No", id=f"{qid}_no", classes="ask-opt-btn"),
                ),
                None,
            ))
            self._q_btn_map[f"{qid}_yes"] = (qi, "yes")
            self._q_btn_map[f"{qid}_no"] = (qi, "no")
        elif qopts:
            rs = RadioSet(id=f"{qid}_radios")
            btns = []
            for oi, opt in enumerate(qopts):
                label = opt.get("label", "")
                value = opt.get("value", "")
                btn_id = f"{qid}_opt_{oi}"
                self._option_values[btn_id] = value
                self._q_btn_map[btn_id] = (qi, value)
                btns.append(RadioButton(label, id=btn_id, value=value))  # type: ignore[arg-type]
            # Add "其他" as last option
            custom_btn_id = f"{qid}_opt_custom"
            self._q_btn_map[custom_btn_id] = (qi, CUSTOM_VALUE)
            btns.append(RadioButton("其他", id=custom_btn_id, value=CUSTOM_VALUE))  # type: ignore[arg-type]
            to_mount.append((rs, btns))
            # Hidden custom input for this pane
            wrap = Horizontal(id=f"{qid}_custom-row", classes="-hidden")
            to_mount.append((wrap, [
                Input(placeholder="✍ 输入自定义方案\u2026", id=f"{qid}_input", classes="ask-q-input"),
                Button("发送", variant="primary", id=f"{qid}_send", classes="ask-send-btn"),
            ]))
        else:
            # No options: show input directly (not hidden)
            wrap = Horizontal(id=f"{qid}_custom-row")
            to_mount.append((wrap, [
                Input(placeholder="✍ 输入自定义方案\u2026", id=f"{qid}_input", classes="ask-q-input"),
                Button("发送", variant="primary", id=f"{qid}_send", classes="ask-send-btn"),
            ]))

        return pane, to_mount

    # ── Mount / Focus ───────────────────────────────────────────────────────

    async def on_mount(self) -> None:
        if self._is_multi:
            await self._build_multi_panes()
            self.query_one("#ask-tab-content", TabbedContent).active = "_ask_pane_0"
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
            except NoMatches:
                self.focus()
        else:
            if self._options:
                rs = self.query_one("#ask-radio-set", RadioSet)
                for i, opt in enumerate(self._options):
                    label = opt.get("label", "")
                    value = opt.get("value", "")
                    key = opt.get("key")
                    display = f"[{key.upper()}] {label}" if key else label
                    btn_id = f"_ask_opt_0_{i}"
                    self._option_values[btn_id] = value
                    await rs.mount(RadioButton(display, id=btn_id, value=value))  # type: ignore[arg-type]
                # Add "其他" as last option
                custom_btn_id = "_ask_opt_0_custom"
                self._option_values[custom_btn_id] = CUSTOM_VALUE
                await rs.mount(RadioButton("其他", id=custom_btn_id, value=CUSTOM_VALUE))  # type: ignore[arg-type]
                try:
                    self.query_one("RadioButton", RadioButton).focus()
                except NoMatches:
                    self.focus()
            else:
                try:
                    self.query_one("#ask-custom-input", Input).focus()
                except NoMatches:
                    self.focus()

    # ── Single question handlers ─────────────────────────────────────────────

    @on(RadioSet.Changed, "#ask-radio-set")
    def handle_radio_changed(self, event: RadioSet.Changed) -> None:
        if self._is_multi:
            return
        btn_id = event.pressed.id or ""
        value = self._option_values.get(btn_id, "")
        if value == CUSTOM_VALUE:
            self.query_one("#ask-custom-input-row", Horizontal).display = True
            self.query_one("#ask-custom-input", Input).focus()
        elif value:
            self._finish(value)

    @on(Button.Pressed, "#ask-rollback")
    def handle_rollback(self) -> None:
        self.post_message(AskUserSubmitted("__rollback__", self._tool_id))

    @on(Button.Pressed, "#ask-submit-all")
    def handle_submit(self) -> None:
        if self._is_multi:
            return

    @on(Button.Pressed, "#ask-send-custom")
    def handle_send_custom(self) -> None:
        value = self.query_one("#ask-custom-input", Input).value.strip()
        if value:
            self._finish(value)

    @on(Input.Submitted, "#ask-custom-input")
    def handle_custom_input_submitted(self) -> None:
        value = self.query_one("#ask-custom-input", Input).value.strip()
        if value:
            self._finish(value)

    # ── Multi-question handlers ─────────────────────────────────────────────

    @on(Button.Pressed, "#ask-submit-all")
    def handle_submit_all(self) -> None:
        if not self._is_multi:
            return
        answers = {}
        for qi, q in enumerate(self._questions):
            qtype = q.get("type", "single")
            qid = f"_ask_q_{qi}"
            if qtype == "multiple":
                selected = []
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
        self._finish(json.dumps(answers))

    @on(Button.Pressed, ".ask-opt-btn")
    def handle_q_option(self, event: Button.Pressed) -> None:
        entry = self._q_btn_map.get(event.button.id or "")
        if entry:
            q_idx, value = entry
            qid = f"_ask_q_{q_idx}"
            self._q_selections[qid] = value

    @on(RadioSet.Changed)
    def handle_q_radio_changed(self, event: RadioSet.Changed) -> None:
        btn_id = event.pressed.id or ""
        entry = self._q_btn_map.get(btn_id)
        if entry:
            q_idx, value = entry
            qid = f"_ask_q_{q_idx}"
            if value == CUSTOM_VALUE:
                self.query_one(f"#{qid}_custom-row", Horizontal).display = True
                self.query_one(f"#{qid}_input", Input).focus()
            else:
                self._q_selections[qid] = str(event.pressed.value) if event.pressed.value else ""

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

    # ── Finish ─────────────────────────────────────────────────────────────

    def _finish(self, value: str) -> None:
        self._answer = value
        self._done = True
        self.post_message(AskUserSubmitted(value, self._tool_id))
        self.remove()
