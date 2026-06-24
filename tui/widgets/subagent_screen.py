from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import Screen
from textual.widgets import Footer, Header, Markdown


class SubAgentScreen(Screen):
    """Full-screen view of a SubAgent output.

    Displays the complete structured output (SUMMARY/CHANGES/EVIDENCE/RISKS/BLOCKERS)
    as Markdown.  Esc to close and return to the main conversation.
    """

    BINDINGS: list[BindingType] = [
        Binding("escape", "app.pop_screen", "Back", show=True),
    ]

    def __init__(
        self,
        agent_type: str,
        subagent_id: str,
        chunks: list[str],
        thinking_chunks: list[str],
        status: str,
        error: str,
    ) -> None:
        super().__init__()
        self.agent_type = agent_type
        self.subagent_id = subagent_id
        self.chunks = chunks
        self.thinking_chunks = thinking_chunks
        self.status = status
        self.error = error

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Markdown(self._build_content(), id="subagent-full-content")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#subagent-full-content", Markdown).scroll_end()

    def _build_content(self) -> str:
        raw = "".join(self.chunks)
        if self.status == "failed":
            return (
                f"# ❌ Subagent @{self.agent_type} Failed\n\n"
                f"**Error:** {self.error}\n\n"
                "---\n\n"
                "## Partial output\n\n"
                f"```\n{(raw or '(none)')[:4000]}\n```"
            )
        if not raw:
            return f"# @{self.agent_type}\n\n_(streaming…)_"
        return raw
