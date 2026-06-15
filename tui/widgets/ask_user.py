from __future__ import annotations

import json

from textual.app import ComposeResult
from textual import on
from textual.containers import Horizontal, VerticalGroup
from textual.message import Message
from textual.widgets import Button, Checkbox, Input, Static


class AskUserSubmitted(Message):
    def __init__(self, value: str, tool_id: str) -> None:
        super().__init__()
        self.value = value
        self.tool_id = tool_id


class AskUserWidget(VerticalGroup):
    DEFAULT_CLASSES = "block"
    DEFAULT_CSS = """
    AskUserWidget {
        height: auto;
        padding: 1 2;
        margin: 1 0;
        border: round $primary;
        background: $boost;
    }
    AskUserWidget #ask-question {
        text-style: bold;
        margin-bottom: 1;
    }
    AskUserWidget #ask-options {
        height: auto;
        margin-bottom: 1;
    }
    AskUserWidget #ask-input-row {
        height: auto;
    }
    AskUserWidget #ask-input {
        margin-right: 1;
    }
    AskUserWidget #ask-answer-done {
        margin: 0 1;
    }
    AskUserWidget .ask-q-section {
        height: auto;
        margin-bottom: 1;
        padding: 0 0 0 1;
        border-left: solid $primary 30%;
    }
    AskUserWidget .ask-q-header {
        text-style: bold;
    }
    AskUserWidget .ask-q-text {
        margin-bottom: 1;
    }
    AskUserWidget .ask-q-options {
        height: auto;
        margin-bottom: 0;
    }
    AskUserWidget .ask-submit-row {
        height: auto;
        margin-top: 1;
    }
    AskUserWidget .ask-opt-btn {
        margin-right: 1;
    }
    AskUserWidget .ask-q-input {
        margin: 0 0 1 0;
    }
    """

    def __init__(
        self, tool_id: str, question: str = "",
        options: list[dict] | None = None,
        questions: list[dict] | None = None,
    ) -> None:
        super().__init__()
        self._tool_id = tool_id
        self._question = question
        self._options = options or []
        self._questions = questions or []
        self._is_multi = bool(self._questions)
        self._answer = ""
        self._done = False
        self._option_buttons: dict[str, str] = {}
        # multi-q state: btn_id → (question_index, value)
        self._q_btn_map: dict[str, tuple[int, str]] = {}
        # multi-q state: qid → set of selected option values (for "multiple" type)
        self._multi_selections: dict[str, set[str]] = {}
        # multi-q state: qid → single selected value (for "single"/"confirm" type)
        self._q_selections: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        if self._done:
            suffix = "multi" if self._is_multi else self._answer
            yield Static(f"✅ AskUser — {suffix}", id="ask-answer-done")
            return
        if self._is_multi:
            yield from self._compose_multi()
        else:
            yield from self._compose_single()

    def _compose_single(self) -> ComposeResult:
        yield Static(f"❓ {self._question}", id="ask-question")
        if self._options:
            with Horizontal(id="ask-options"):
                for i, opt in enumerate(self._options):
                    label = opt.get("label", "")
                    value = opt.get("value", "")
                    key = opt.get("key")
                    if key:
                        display = f"[{key.upper()}] {label}"
                    else:
                        display = label
                    btn_id = f"_ask_opt_{i}"
                    self._option_buttons[btn_id] = value
                    yield Button(display, id=btn_id)
        with Horizontal(id="ask-input-row"):
            yield Input(placeholder="Type your answer\u2026", id="ask-input")
            yield Button("Send", variant="primary", id="ask-send")
            yield Button("Cancel", id="ask-cancel")

    def _compose_multi(self) -> ComposeResult:
        for qi, q in enumerate(self._questions):
            qheader = q.get("header", "") or f"Question {qi + 1}"
            qtext = q.get("question", "")
            qtype = q.get("type", "single")
            qopts = q.get("options", [])
            qid = f"_ask_q_{qi}"

            with VerticalGroup(classes="ask-q-section"):
                yield Static(qheader, classes="ask-q-header")
                yield Static(qtext, classes="ask-q-text")

                if qtype == "multiple" and qopts:
                    with VerticalGroup(classes="ask-q-options"):
                        for oi, opt in enumerate(qopts):
                            opt_id = f"{qid}_chk_{oi}"
                            label = opt.get("label", "")
                            yield Checkbox(f" {label}", id=opt_id)
                            self._multi_selections.setdefault(qid, set())
                else:
                    # single, confirm, or multiple without options → buttons + custom input
                    with VerticalGroup(classes="ask-q-options"):
                        if qtype == "confirm":
                            yield Horizontal(
                                Button("Yes", id=f"{qid}_yes", variant="primary", classes="ask-opt-btn"),
                                Button("No", id=f"{qid}_no", classes="ask-opt-btn"),
                            )
                            self._q_btn_map[f"{qid}_yes"] = (qi, "yes")
                            self._q_btn_map[f"{qid}_no"] = (qi, "no")
                        elif qopts:
                            with Horizontal():
                                for oi, opt in enumerate(qopts):
                                    label = opt.get("label", "")
                                    value = opt.get("value", "")
                                    btn_id = f"{qid}_opt_{oi}"
                                    self._option_buttons[btn_id] = value
                                    self._q_btn_map[btn_id] = (qi, value)
                                    yield Button(label, id=btn_id, classes="ask-opt-btn")
                        yield Input(placeholder="Custom answer\u2026", id=f"{qid}_input", classes="ask-q-input")

        with Horizontal(classes="ask-submit-row"):
            yield Button("Submit All", variant="primary", id="ask-submit-all")
            yield Button("Cancel", id="ask-cancel")

    def on_mount(self) -> None:
        if not self._is_multi:
            try:
                self.query_one("#ask-input", Input).focus()
            except Exception:
                pass

    # ── Single question handlers (backward compat) ──

    @on(Button.Pressed, "#ask-cancel")
    def handle_cancel(self) -> None:
        self.post_message(AskUserSubmitted("__cancel__", self._tool_id))

    @on(Button.Pressed, "#ask-send")
    def handle_send(self) -> None:
        value = self.query_one("#ask-input", Input).value.strip()
        if value:
            self._finish(value)

    @on(Input.Submitted, "#ask-input")
    def handle_input_submitted(self) -> None:
        value = self.query_one("#ask-input", Input).value.strip()
        if value:
            self._finish(value)

    @on(Button.Pressed)
    def handle_option(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id and btn_id in self._option_buttons and not self._is_multi:
            self._finish(self._option_buttons[btn_id])

    # ── Multi-question handlers ──

    @on(Button.Pressed, "#ask-submit-all")
    def handle_submit_all(self) -> None:
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

        # Check all questions have answers
        unanswered = [str(i) for i, q in enumerate(self._questions) if not answers.get(str(i))]
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

    @on(Input.Submitted)
    def handle_q_input(self, event: Input.Submitted) -> None:
        inp_id = event.input.id or ""
        if inp_id.startswith("_ask_q_") and inp_id.endswith("_input"):
            qi = inp_id.replace("_ask_q_", "").replace("_input", "")
            qid = f"_ask_q_{qi}"
            val = event.value.strip()
            if val:
                self._q_selections[qid] = val

    # ── Finish ──

    def _finish(self, value: str) -> None:
        self._answer = value
        self._done = True
        self.refresh(recompose=True, layout=True)
        self.post_message(AskUserSubmitted(value, self._tool_id))
