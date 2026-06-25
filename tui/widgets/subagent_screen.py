from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Header, Markdown, Static

from tui.widgets.subagent import SubAgent


class SubAgentScreen(Screen):
    """Full-screen view of a SubAgent output.

    Displays the complete structured output (SUMMARY/CHANGES/EVIDENCE/RISKS/BLOCKERS)
    as Markdown.  Esc to close, Up/Down/PageUp/PageDown to scroll.
    Streams live while the SubAgent is running via a refresh timer.
    """

    BINDINGS: list[BindingType] = [
        Binding("escape", "app.pop_screen", "Back", priority=True),
        Binding("up", "scroll_up", "Up", priority=True),
        Binding("down", "scroll_down", "Down", priority=True),
        Binding("pageup", "scroll_page_up", "Page Up", priority=True),
        Binding("pagedown", "scroll_page_down", "Page Down", priority=True),
        Binding("home", "scroll_home", "Home", priority=True),
        Binding("end", "scroll_end", "End", priority=True),
    ]

    DEFAULT_CSS = """
    SubAgentScreen {
        align: center middle;

        #subagent-screen-frame {
            width: 95%;
            max-width: 160;
            height: 95%;
            border: thick $primary;
            background: $surface;
        }

        SubAgentScreenFooter {
            dock: bottom;
            height: 1;
            padding: 0 1;
            color: $text-muted;
            background: $boost;
        }

        #subagent-full-content {
            padding: 0 1;
            height: 1fr;
            overflow-y: auto;
            scrollbar-gutter: stable;
        }
    }
    """

    def __init__(self, subagent: SubAgent) -> None:
        super().__init__()
        self.subagent = subagent
        self._auto_follow = True
        self._refresh_timer = None
        self._last_content_hash: str = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="subagent-screen-frame"):
            yield Markdown(self._build_content(), id="subagent-full-content")
        yield Static(
            "[$text-muted]esc[/] 返回  "
            "[$text-muted]↑↓[/] 滚动  "
            "[$text-muted]pageup/pagedown[/] 翻页  "
            "[$text-muted]end[/] 跟随最新",
            id="subagent-screen-footer",
        )

    def on_mount(self) -> None:
        self.title = "subagent"
        self.sub_title = f"@{self.subagent.agent_type} [{self.subagent._status}]"
        self._last_content_hash = self._content_signature()
        self._refresh_content(scroll_to_end=True)
        self._refresh_timer = self.set_interval(0.2, self._poll_subagent)

    def on_unmount(self) -> None:
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
            self._refresh_timer = None

    def _content_signature(self) -> str:
        sa = self.subagent
        return f"{sa._status}|{sa.spinner_frame}|{len(sa._chunks)}|{len(sa._thinking_chunks)}|{sa._error}"

    def _poll_subagent(self) -> None:
        sig = self._content_signature()
        if sig != self._last_content_hash:
            self._last_content_hash = sig
            self._refresh_content(scroll_to_end=self._auto_follow)
            self.sub_title = f"@{self.subagent.agent_type} [{self.subagent._status}]"
            if self.subagent._status != "running" and self._refresh_timer is not None:
                self._refresh_timer.stop()
                self._refresh_timer = None

    def _refresh_content(self, scroll_to_end: bool = False) -> None:
        try:
            md = self.query_one("#subagent-full-content", Markdown)
            md.update(self._build_content())
            if scroll_to_end:
                self.call_after_refresh(md.scroll_end)
        except Exception:
            pass

    def action_scroll_up(self) -> None:
        self._auto_follow = False
        try:
            self.query_one("#subagent-full-content", Markdown).scroll_up()
        except Exception:
            pass

    def action_scroll_down(self) -> None:
        try:
            md = self.query_one("#subagent-full-content", Markdown)
            md.scroll_down()
        except Exception:
            pass

    def action_scroll_page_up(self) -> None:
        self._auto_follow = False
        try:
            self.query_one("#subagent-full-content", Markdown).scroll_page_up()
        except Exception:
            pass

    def action_scroll_page_down(self) -> None:
        try:
            md = self.query_one("#subagent-full-content", Markdown)
            md.scroll_page_down()
        except Exception:
            pass

    def action_scroll_home(self) -> None:
        self._auto_follow = False
        try:
            self.query_one("#subagent-full-content", Markdown).scroll_home()
        except Exception:
            pass

    def action_scroll_end(self) -> None:
        self._auto_follow = True
        try:
            self.query_one("#subagent-full-content", Markdown).scroll_end()
        except Exception:
            pass

    def _build_content(self) -> str:
        sa = self.subagent
        parts: list[str] = []
        parts.append(f"# @ {sa.agent_type}  [{sa._status}]\n")
        if sa.prompt:
            prompt_preview = sa.prompt if len(sa.prompt) <= 200 else sa.prompt[:200] + "..."
            parts.append(
                "\n## 任务\n\n"
                f"> {prompt_preview}\n\n"
                "---\n"
            )
        if sa._thinking_chunks:
            parts.append("## 思考\n")
            parts.append("".join(sa._thinking_chunks))
            parts.append("\n\n---\n\n")
        raw = "".join(sa._chunks)
        if sa._status == "failed":
            parts.append(
                f"## ❌ Failed\n\n"
                f"**Error:** {sa._error}\n\n"
                "---\n\n"
                "### Partial output\n\n"
                f"```\n{(raw or '(none)')[:4000]}\n```"
            )
        elif raw:
            parts.append("## 输出\n\n")
            parts.append(raw)
            if sa._status == "running":
                parts.append("\n\n*…streaming*")
        else:
            parts.append("## 输出\n\n_(streaming…)_")
        return "".join(parts)