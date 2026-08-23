"""Shared plain-text question detection for auto-AskUser conversion.

Both the engine (intercepts mid-turn, before tool execution) and the ACP
adapter (end-of-turn fallback) must agree on what counts as a question, or
plain-text questions slip through and the user's input gets queued instead
of becoming an AskUser dialog.

Detection uses two layers:
- Layer 1 — Semantic (intent): explicit "need user input" signals
- Layer 2 — Syntax (punctuation): question marks as fallback

Self-talk patterns are excluded (the LLM is reasoning to itself, no input
needed).
"""

from __future__ import annotations

import re

# Patterns indicating the LLM explicitly needs human input
SEMANTIC_NEEDS_INPUT = [
    r"需要用户", r"需要您", r"需要您提供",
    r"请确认", r"请选择", r"询问您", r"问您",
    r"需要确认", r"需要知道", r"请告诉我",
    r"等待您的", r"需要.*信息", r"需要哪些参数",
    r"请提供", r"请问要", r"请问您", r"需要.*id",
    r"哪个用户", r"哪个文件", r"什么参数", r"如何处理",
    r"^请问",
    r"could you (tell me|confirm|provide|let me know)",
    r"i need to know",
    r"please (confirm|tell me|specify|provide|select|choose)",
    r"which .*(user|file|parameter|option|setting)",
    r"what .*(parameter|user|file|option|setting)",
    r"what should i",
    r"which (file|user|option|one)",
    r"should i (proceed|continue|upgrade|execute)",
    r"do you want (me to|to)",
    r"can you (tell me|confirm|specify)",
    r"let me know (which|what|if|whether)",
    r"i'?m not sure (which|what|who|how)",
    r"you('d| would) like (me to|to)",
    r"would you like (me to|to)",
    r"(could i|may i) get (the|your)",
    r"pick (a|an|the)",
    r"choose (a|an|the|which)",
    r"what'?s the (user|file|path|parameter)",
    r"which one",
    r"confirm the (user|file|path|parameter)",
    r"specify (the|which|what)",
    r"what .*(file|user|path|parameter)",
    r"which .*should i",
    r"(do you|would you|should i)",
]

# Patterns where SEMANTIC_NEEDS_INPUT matched but it's actually a polite
# instruction/statement rather than a genuine question. These are LLM
# self-talk statements of what it needs ("请告诉我错误信息" = "tell me the error"
# as a statement of need, not a question).
SEMANTIC_NEEDS_INPUT_EXCLUSIONS = [
    r"请尝试后告知结果", r"请尝试", r"请告知", r"请先",
    r"请试试", r"请按", r"请过一会儿", r"请执行",
    r"请查看", r"请参考", r"请注意", r"请检查",
    r"请运行", r"请输入", r"请提交", r"请刷新",
]

# Patterns indicating the LLM is just reasoning (self-talk, no input needed)
SEMANTIC_SELF_TALK = [
    r"^让我想想", r"^我需要先", r"^我可以先",
    r"^首先", r"^然后", r"^接下来", r"^好的",
    r"自言自语", r"我在想", r"我在考虑",
    r"让我先", r"我先来", r"先执行",
    r"^let me (think|check|read|look|find|see)",
    r"^i('ll| will| can| should)?( be)? (checking|reading|looking|finding|seeing|thinking)",
    r"^first(ly)?(,| )?(i('ll| will| can| should)?)?",
    r"^then(,| )?(i('ll| will| can| should)?)?",
    r"^next(,| )?(i('ll| will| can| should)?)?",
    r"^okay(|,| ) (so|let me|i('ll| will| can| should)?)",
    r"^alright(|,| ) (so|let me|i('ll| will| can| should)?)",
    r"^sure(|,| ) (so|let me|i('ll| will| can| should)?)",
    r"^sounds good(|,| )",
    r"^i('ll| will| can| should)?( go ahead| start| begin| proceed| execute)",
    r"^i('ll| will| can| should)?( need to| have to| want to) (check|read|look|find|see|think|consider|proceed|execute|verify|confirm|fix|update|change|add|remove)",
    r"^i('m| am)( going to| about to)?",
    r"^looks like",
    r"^it seems (like|that)",
    r"^based on",
    r"^let me just",
    r"^i('ll| will)? just (check|read|look|find|see|try)",
    r"^i think (that )?",
    r"^i believe (that )?",
    r"i('m| am) thinking (about|that)",
    r"i('m| am) considering",
    r"^here('s| is)",
    r"^so(,| )? i('ll| will| can| should)?",
    r"^okay so",
    r"i need to consider",
]


def semantic_needs_input(text: str) -> bool:
    """True when the text carries an explicit "I need user input" signal.

    Self-talk patterns take precedence: an LLM reasoning to itself does not
    need the user, even if it happens to mention an input-like phrase.

    Polite instruction exclusions: phrases like "请尝试后告知结果" are
    statements of what the LLM needs, not genuine questions.
    """
    if not text:
        return False
    for pattern in SEMANTIC_SELF_TALK:
        if re.search(pattern, text, re.IGNORECASE):
            return False
    for pattern in SEMANTIC_NEEDS_INPUT:
        if re.search(pattern, text, re.IGNORECASE):
            for excl in SEMANTIC_NEEDS_INPUT_EXCLUSIONS:
                if re.search(excl, text, re.IGNORECASE):
                    return False
            return True
    return False


def has_trailing_question_mark(text: str) -> bool:
    """True when the text ends with a question marker (？/CJK+?)."""
    stripped = text.rstrip() if text else ""
    if not stripped:
        return False
    if stripped.endswith("\uff1f"):
        return True
    if stripped.endswith("?") and len(stripped) >= 2:
        prev = stripped[-2]
        return "\u4e00" <= prev <= "\u9fff" or "\u3000" <= prev <= "\u303f"
    return False


def has_question_mark_in_last_sentence(text: str) -> bool:
    """True when the FINAL sentence of the text contains a question mark.

    This is the loose fallback: unlike checking anywhere in the output, an
    aside or rhetorical ``?`` buried in the middle of the response does not
    count — only a question that closes the turn does. This keeps auto-ask
    from firing on every turn just because the LLM's prose happens to
    contain a question mark.
    """
    stripped = text.rstrip() if text else ""
    if not stripped:
        return False
    m = max(
        stripped.rfind("。"), stripped.rfind("！"), stripped.rfind("？"),
        stripped.rfind("."), stripped.rfind("!"), stripped.rfind("?"),
        stripped.rfind("\n"),
    )
    tail = stripped[m + 1:] if m >= 0 else stripped
    return "?" in tail or "？" in tail


def looks_like_question(text: str, *, strict: bool = False) -> bool:
    """True when the text asks the user for input.

    ``strict=True`` (used when the LLM made no tool calls): the question
    must be signalled by intent or by trailing question punctuation, so
    ordinary prose or code containing a stray ``?`` is not misread.

    ``strict=False`` (used when tool calls accompany the text): a question
    mark in the FINAL sentence also counts, so a question followed by tool
    execution is still intercepted — but an aside ``?`` in the middle of the
    output does not trigger auto-ask.
    """
    if not text or not text.strip():
        return False
    if semantic_needs_input(text):
        return True
    if has_trailing_question_mark(text):
        return True
    if not strict and has_question_mark_in_last_sentence(text):
        return True
    return False


# Common markdown block/emphasis markers that bloat the AskUser widget.
# We strip these from the auto-ask question so the dialog stays compact.
_MARKDOWN_STRIP = (
    r"\*\*", r"__", r"`", r"```", r"\*",
    r"^#+\s?", r"^>\s?", r"^\s*[-*+]\s+", r"^\s*\d+\.\s+",
    r"^---\s*$", r"^\|", r"\|\s*$",
)


def strip_markdown(text: str) -> str:
    """Strip common markdown syntax so question text renders cleanly."""
    if not text:
        return ""
    lines = []
    for raw in text.splitlines():
        line = raw
        for pat in _MARKDOWN_STRIP:
            line = re.sub(pat, "", line)
        lines.append(line.strip())
    return "\n".join(lines).strip()


def compact_question(text: str, *, max_chars: int = 240) -> str:
    """Condense a (possibly markdown-laden) question to a compact snippet.

    Used for auto-AskUser conversion so the dialog shows the trailing
    question sentence instead of the whole preamble/plan text.
    """
    if not text:
        return ""
    clean = strip_markdown(text)

    # Prefer the final sentence, anchored on CJK/Latin sentence terminators.
    tail = ""
    for marker in ("。", "！", "\uff1f", ". ", "! ", "? ", "\n"):
        idx = clean.rfind(marker)
        if idx >= 0:
            tail = clean[idx + 1:].strip()
            break
    if len(tail) < 12:
        tail = clean

    if len(tail) <= max_chars:
        return tail

    # Hard truncate at a sentence boundary near the limit.
    prefix = tail[:max_chars]
    cut = max(prefix.rfind("。"), prefix.rfind("，"), prefix.rfind(". "), prefix.rfind(", "))
    if cut >= max_chars * 3 // 4:
        prefix = prefix[:cut + 1]
    return prefix.rstrip() + "…"
