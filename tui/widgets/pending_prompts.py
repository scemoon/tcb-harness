from __future__ import annotations

from textual.reactive import var
from textual.widgets import Static


class PendingPrompts(Static):
    """Shows queued prompts fixed at the bottom of the conversation
    when the agent is busy processing a previous turn."""

    DEFAULT_CSS = """
    PendingPrompts {
        height: auto;
        max-height: 6;
        margin: 0 0 1 0;
        background: $primary 5%;
        display: none;
        overflow-y: auto;
        overflow-x: hidden;
    }
    """

    _prompts: var[list[str]] = var([], init=False)

    def watch__prompts(self, prompts: list[str]) -> None:
        if not prompts:
            self.display = "none"
            return
        self.display = "block"
        lines = []
        for i, p in enumerate(prompts, 1):
            line = p.replace("\n", " ").strip()
            if len(line) > 100:
                line = line[:99] + "…"
            lines.append(f"⏳ {i}. {line}")
        self.update("\n".join(lines))
