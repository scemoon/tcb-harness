from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import var
from textual import containers
from textual.widgets import Static, Markdown

from tui.pill import pill


class SubAgentHeader(Static):
    ALLOW_SELECT = False
    DEFAULT_CSS = """
    SubAgentHeader {
        width: auto;
        max-width: 1fr;
    }
    """


class SubAgentContent(Markdown):
    DEFAULT_CSS = """
    SubAgentContent {
        margin: 0 1 0 2;
    }
    """


class SubAgent(containers.VerticalGroup):
    DEFAULT_CLASSES = "block"
    DEFAULT_CSS = """
    SubAgent {
        margin: 0 0 0 1;
        height: auto;
        SubAgentHeader {
            color: $text-secondary;
        }
        &.-status-running SubAgentHeader {
            color: $text-warning;
            text-style: italic;
        }
        &.-status-completed SubAgentHeader {
            color: $text-success;
        }
    }
    """

    agent_type: var[str] = var("")
    status: var[str] = var("running")

    def __init__(
        self,
        agent_type: str,
        tool_id: str | None = None,
    ) -> None:
        super().__init__(id=tool_id)
        self.agent_type = agent_type
        self.status = "running"
        self._chunks: list[str] = []

    def compose(self) -> ComposeResult:
        self.set_class(True, f"-status-{self.status}")
        label = pill(self.agent_type, "$warning-muted", "$text-warning")
        yield SubAgentHeader(
            f"🧠 Sub‑agent: {self.agent_type} {label}",
            markup=False,
        )
        yield SubAgentContent("")

    def append_chunk(self, text: str) -> None:
        self._chunks.append(text)
        try:
            content = self.query_one(SubAgentContent)
            content.load("".join(self._chunks))
        except Exception:
            pass

    def complete(self) -> None:
        self.status = "completed"
        self.set_class(True, "-status-completed")
        self.set_class(False, "-status-running")
        try:
            self.query_one(SubAgentHeader).update(
                f"🧠 Sub‑agent: {self.agent_type} — completed ✅"
            )
        except Exception:
            pass
