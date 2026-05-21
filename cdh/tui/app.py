from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Label, ListView, ListItem
from textual.reactive import reactive
from textual.css.styles import Styles

from cdh.agent.engine import AgentEngine
from cdh.config import load_config, get_workspace_dir
from cdh.lifecycle.manager import LifecycleManager
from cdh.models.providers import *  # noqa: F401, F403
from cdh.models.registry import ModelRegistry
from cdh.storage.session import SessionStore
from cdh.storage.activity import ActivityRecorder
from cdh.trace.tracer import Tracer
from cdh.tui.theme import THEMES
from cdh.tui.widgets.header import HeaderBar
from cdh.tui.widgets.footer import FooterBar


class BlueCursorInput(Input):
    def get_component_rich_style(self, *names, partial=False, default=None):
        style = super().get_component_rich_style(*names, partial=partial, default=default)
        if "input--cursor" in names:
            cursor_color = self.app.tui_theme.primary if hasattr(self.app, '_tui_theme') else "#7aa2f7"
            style = Style(color=cursor_color, bold=True)
        return style


class ChatInput(BlueCursorInput):
    """Custom Input with blue cursor that intercepts Up/Down/Escape when slash/@ menu is active."""

    @property
    def _slash_has_matches(self) -> bool:
        app = self.app
        return bool(getattr(app, "_slash_active", False) and getattr(app, "_slash_matches", []))

    @property
    def _at_has_matches(self) -> bool:
        app = self.app
        return bool(getattr(app, "_at_active", False) and getattr(app, "_at_matches", []))

    async def _on_key(self, event: events.Key) -> None:
        # Config panel escape — highest priority
        if event.key == "escape" and self.app._config_panel_data:
            event.stop()
            self.app._dismiss_config_panel()
            return

        # Config panel up/down/enter navigation
        if self.app._config_panel_data:
            try:
                suggestions = self.app.query_one("#cmd-suggestions", ListView)
            except Exception:
                pass
            else:
                if event.key == "up":
                    event.stop()
                    if suggestions.index is not None and suggestions.index > 0:
                        suggestions.index -= 1
                    return
                elif event.key == "down":
                    event.stop()
                    if suggestions.index is not None and suggestions.index < len(suggestions.children) - 1:
                        suggestions.index += 1
                    return
                elif event.key == "enter":
                    event.stop()
                    data = self.app._config_panel_data
                    if data.get("info"):
                        self.app._dismiss_config_panel()
                    else:
                        idx = suggestions.index
                        if idx is not None and 0 <= idx < len(data.get("items", [])):
                            _, value = data["items"][idx]
                            cmd = f"/{data.get('prefix', '')}{value}"
                            self.app._dismiss_config_panel()
                            if data.get("execute", False):
                                from cdh.tui.commands.registry import CommandRegistry
                                result = CommandRegistry.dispatch(self.app, cmd)
                                if result:
                                    self.app.handle_command_result(cmd, result)
                        else:
                            self.app._dismiss_config_panel()
                    return

        if self._slash_has_matches:
            if event.key == "up":
                event.stop()
                self.app._navigate_slash_highlight(-1)
                return
            elif event.key == "down":
                event.stop()
                self.app._navigate_slash_highlight(1)
                return
            elif event.key == "enter":
                event.stop()
                idx = self.app._slash_index
                if idx >= 0 and idx < len(self.app._slash_matches):
                    pos = self.app._suggestion_pos
                    cmd = f"/{self.app._slash_matches[idx]}"
                    self.value = self.value[:pos] + cmd if pos > 0 else cmd
                    self.cursor_position = len(self.value)
                self.app._close_slash_menu()
                return
            elif event.key in ("space", " "):
                self.app._close_slash_menu()
            elif event.key == "escape":
                event.stop()
                self.app._dismiss_slash_menu()
                return
        elif self._at_has_matches:
            if event.key == "up":
                event.stop()
                self.app._navigate_at_highlight(-1)
                return
            elif event.key == "down":
                event.stop()
                self.app._navigate_at_highlight(1)
                return
            elif event.key == "enter":
                event.stop()
                idx = self.app._at_index
                if idx >= 0 and idx < len(self.app._at_matches):
                    pos = self.app._suggestion_pos
                    cmd = f"@{self.app._at_matches[idx]}"
                    self.value = self.value[:pos] + cmd if pos > 0 else cmd
                    self.cursor_position = len(self.value)
                if event.key == "enter":
                    self.app._close_at_menu()
                return
            elif event.key in ("space", " "):
                self.app._close_at_menu()
            elif event.key == "escape":
                event.stop()
                self.app._dismiss_at_menu()
                return
        elif event.key == "tab":
            event.stop()
            self.app.action_cycle_mode()
            return
        await super()._on_key(event)


class CloudDevHarnessApp(App):

    ENABLE_COMMAND_PALETTE = False

    CSS = """
    * { background: $background; }
    Screen { background: $background; padding: 0; margin: 0; }
    #app-container { height: 100%; width: 100%; overflow: hidden; padding: 0; margin: 0; }
    #main-content { height: 1fr; layout: horizontal;  }
    #chat-area { width: 1fr; padding: 1; margin: 0; }
    #right-sidebar { width: 25%; min-width: 20; background: transparent;  margin: 0; }
    #right-sidebar.-hidden { display: none; }
    #cmd-suggestions { display: none; height: auto; max-height: 10; padding: 0 2; background: $panel; scrollbar-size: 0 0; scrollbar-gutter: auto; }
    #cmd-suggestions.-visible { display: block; }
    #cmd-suggestions ListItem { padding: 0 1; color: $text_bright; }
    #cmd-suggestions ListItem.-highlight { background: $highlight_bg; color: $highlight_text; text-style: bold; }
    #input-area { height: 4; padding: 0; border-top: solid $primary; }
    #input-prompt { width: 3; color: $success; text-style: bold; content-align: center middle; }
    #chat-input { width: 1fr; height: 100%; border: none; padding: 0 ; color: $foreground; }
    #chat-input:focus { border: none;  }
    FooterBar { height: 2; border-top: solid $primary; padding: 0; }
    FooterBar Static { width: 100%; }
    HeaderBar { height: 2; border-bottom: solid $primary; padding: 0; }
    HeaderBar Static { width: 100%; }
    ChatPanel { height: 1fr; border-right: solid $primary; }

    ConfigScreen { align: center middle; background: $overlay; }
    ConfigScreen > #config-dialog { width: 66; max-height: 30; background: $surface; border: solid $primary; padding: 1 2; }
    #config-header { width: 100%; text-align: center; text-style: bold; color: $primary; padding: 1 0; }
    #config-list { height: 1fr; max-height: 16; overflow-y: auto; }
    #config-list ListItem { padding: 0 1; color: $text_bright; }
    #config-list ListItem.-highlight { background: $highlight_bg; color: $highlight_text; text-style: bold; }
    #config-text { height: auto; max-height: 16; overflow-y: auto; color: $text_bright; padding: 0 1; }
    #config-hint { width: 100%; text-align: center; color: $text_dim; margin-top: 1; }
    """
    BINDINGS = [
        Binding("ctrl+f", "focus_chat_input", "Focus input"),
        Binding("tab", "cycle_mode", "Cycle mode", priority=True),
        Binding("ctrl+p", "select_model", "Select model"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    current_mode:    reactive[str]            = reactive("agent")
    current_model:   reactive[str]            = reactive("MiniMax-M2.7")
    current_provider: reactive[str]           = reactive("minimal")
    current_cloud:   reactive[str]            = reactive("tcb")
    current_project: reactive[Optional[str]]  = reactive(None)
    turn_count:      reactive[int]            = reactive(0)
    token_count:     reactive[int]            = reactive(0)

    def watch_current_project(self, old_val: str, new_val: str) -> None:
        self.query_one(HeaderBar).sync(self)
        self._refresh_right_panel()

    @property
    def workspace(self) -> Path:
        return Path(self.config.default_workspace).expanduser().resolve()

    @property
    def projects_dir(self) -> Path:
        return self.workspace / "projects"

    def __init__(self) -> None:
        from cdh.tui.theme import THEMES
        super().__init__()
        cdh_dark = THEMES["cdh-dark"]
        cdh_light = THEMES["cdh-light"]
        self.register_theme(cdh_dark)
        self.register_theme(cdh_light)
        cfg = load_config()
        self.config = cfg
        self.session_store = SessionStore()
        self.activity_recorder = ActivityRecorder()
        self.lifecycle = LifecycleManager()
        self.tracer = Tracer()
        self.current_mode    = cfg.default_mode
        self.current_model   = cfg.default_model
        self.current_provider = cfg.default_provider
        self.current_cloud   = cfg.default_cloud
        theme_config = cfg.tui.theme if cfg.tui.theme and cfg.tui.theme != "auto" else "dark"
        self.theme = "cdh-light" if theme_config == "light" else "cdh-dark"
        self.agent = AgentEngine(self)
        ModelRegistry.initialize()

        # Slash command state
        self._slash_matches: list[str] = []
        self._slash_index: int = -1
        self._slash_active: bool = False

        # @ file suggestion state
        self._at_matches: list[str] = []
        self._at_index: int = -1
        self._at_active: bool = False

        # Position of / or @ trigger in input (-1 = start of input)
        self._suggestion_pos: int = -1

        # Config panel state (command results shown in suggestion list)
        self._config_panel_data: dict | None = None

        # Config flow flag — True when navigating via Ctrl+P (uses ConfigScreen overlay)
        self._config_flow: bool = False

        # Current session record (set by session commands or auto-created on mount)
        self._session = None

    @property
    def tui_theme(self):
        return self.current_theme

    def _apply_theme(self) -> None:
        from cdh.tui.widgets.header import HeaderBar
        from cdh.tui.widgets.footer import FooterBar
        self.query_one(HeaderBar).sync(self)
        self.query_one(FooterBar).sync(self)
        rp = self.query_one_optional("#right-sidebar")
        if rp:
            rp.refresh()
        inp = self.query_one_optional("#chat-input")
        if inp:
            inp.refresh()

    # ── compose ──

    def compose(self) -> ComposeResult:
        from cdh.tui.widgets.chat        import ChatPanel
        from cdh.tui.widgets.right_panel import RightPanel

        with Vertical(id="app-container"):
            yield HeaderBar()

            with Horizontal(id="main-content"):
                with Vertical(id="chat-area"):
                    yield ChatPanel()
                    yield ListView(id="cmd-suggestions")
                yield RightPanel(id="right-sidebar")

            with Horizontal(id="input-area"):
                yield Label("\u276f", id="input-prompt")
                yield ChatInput(placeholder="Ask anything or /command ...", id="chat-input")

            yield FooterBar()

    def on_mount(self) -> None:
        self._apply_theme()
        self.query_one(HeaderBar).sync(self)
        self.query_one(FooterBar).sync(self)
        self._init_session()
        self._focus_input()

    def _init_session(self) -> None:
        from cdh.tui.commands.harness_cmds import get_current_project
        if not self.current_project:
            self.current_project = get_current_project(self.workspace) or None
        if self.current_project:
            self.agent._inject_project_context(self.current_project)
        self._load_session_for_project(self.current_project or "")
        self._refresh_right_panel()

    def _load_session_for_project(self, project: str) -> None:
        if project:
            sessions = self.session_store.list_by_project(project)
        else:
            sessions = self.session_store.list_by_project("")
        if sessions:
            self._session = sessions[0]
            self.current_mode = self._session.mode or self.current_mode
            self._attach_agent_session()
            self._display_session_messages()
        else:
            record = self.session_store.create(name="Default", mode=self.current_mode, project=project)
            self._session = record
            self._attach_agent_session()
            self.activity_recorder.record(
                event_type="session_auto_create",
                project=project,
                session=record.id,
                details={"name": "Default", "mode": self.current_mode},
            )

    def _attach_agent_session(self) -> None:
        if not self._session:
            return
        from cdh.agent.session import AgentSession
        agent_s = AgentSession(self._session.id)
        if not agent_s.load():
            agent_s.save()
        self.agent.attach_session(agent_s)

    def _display_session_messages(self) -> None:
        if not self._session:
            return
        messages = self._session.messages or []
        if not messages:
            from cdh.agent.session import AgentSession
            agent_s = AgentSession(self._session.id)
            if agent_s.load():
                messages = agent_s.messages
        if not messages:
            return
        chat = self.query_one_optional("ChatPanel")
        if chat:
            chat.load_messages(messages)

    def _persist_session(self) -> None:
        if not self._session:
            return
        from cdh.agent.session import AgentSession
        agent_s = AgentSession(self._session.id)
        agent_s.load()
        agent_s._data.messages = self.agent.context.to_session_format()
        agent_s.save()
        self._session.messages = agent_s.messages
        self.session_store.update(self._session)

    def on_unmount(self) -> None:
        self._persist_session()

    # ── model select ──

    def action_select_model(self) -> None:
        self._config_flow = True
        items = [
            ("\u2500\u2500 MODEL & MODE \u2500\u2500" , ""),
            (f"Model    {self.current_model}"       , f"model switch"),
            (f"Mode     {self.current_mode}"         , f"mode"),
            (f"Provider {self.current_provider}"     , f"provider switch"),
            (f"Cloud    {self.current_cloud}"        , f"cloud switch"),
            ("", ""),
            ("\u2500\u2500 SESSION \u2500\u2500"        , ""),
            (f"Session List"                         , f"session list"),
            (f"Session New"                          , f"session new"),
            (f"Session Rename"                       , f"session rename"),
            (f"Session Delete"                       , f"session delete"),
            (f"Session Export"                       , f"session export"),
            ("", ""),
            ("\u2500\u2500 SKILL & MCP \u2500\u2500"    , ""),
            (f"Skill List"                           , f"skill list"),
            (f"Skill Install"                        , f"skill install"),
            (f"Skill Toggle"                         , f"skill toggle"),
            (f"MCP List"                             , f"mcp list"),
            (f"MCP Add"                              , f"mcp add"),
            (f"MCP Connect"                          , f"mcp connect"),
            ("", ""),
            ("\u2500\u2500 LIFECYCLE \u2500\u2500"     , ""),
            (f"Spec Generate"                        , f"spec generate"),
            (f"Spec Accept"                          , f"spec accept"),
            (f"Design Generate"                      , f"design generate"),
            (f"Design Accept"                        , f"design accept"),
            (f"Test Run"                             , f"test run"),
            (f"Test Accept"                          , f"test accept"),
            (f"Deploy"                               , f"deploy"),
            ("", ""),
            ("\u2500\u2500 HARNESS \u2500\u2500"       , ""),
            (f"Harness Init"                         , f"harness init"),
            (f"Harness Import"                       , f"harness import"),
            (f"Harness Switch"                       , f"harness switch"),
            (f"Harness Status"                       , f"harness status"),
            (f"Harness List"                         , f"harness list"),
            (f"Harness Run"                          , f"harness run"),
            (f"Harness Clone"                        , f"harness clone"),
            ("", ""),
            ("\u2500\u2500 AGENT \u2500\u2500"         , ""),
            (f"Agent Status"                         , f"agent status"),
            (f"Agent Config"                         , f"agent config"),
            (f"Agent Reset"                          , f"agent reset"),
            (f"Agent Interrupt"                      , f"agent interrupt"),
            (f"Restore"                              , f"restore"),
            ("", ""),
            ("\u2500\u2500 TRACE \u2500\u2500"         , ""),
            (f"Trace Start"                          , f"trace start"),
            (f"Trace Stop"                           , f"trace stop"),
            (f"Trace View"                           , f"trace view"),
            (f"Trace Export"                         , f"trace export"),
            ("", ""),
            ("\u2500\u2500 OTHER \u2500\u2500"         , ""),
            (f"Help"                                 , f"help"),
            (f"Status"                               , f"status"),
            (f"Workspace"                            , f"workspace"),
            (f"Theme (dark|light)"                   , f"theme"),
            (f"Vim Edit"                             , f"vim"),
            (f"Clear"                                , f"clear"),
            (f"Exit"                                 , f"exit"),
        ]
        from cdh.tui.screens.config_screen import ConfigScreen
        self.push_screen(ConfigScreen("Command Palette", items=items, execute=True))

    # ── config panel (suggestion list) ──

    def show_config_panel(self, title: str, items: list[tuple[str, str]], prefix: str = "", execute: bool = False) -> None:
        """Show a selectable list — ConfigScreen overlay when in config flow, suggestion panel otherwise."""
        if self._config_flow:
            from cdh.tui.screens.config_screen import ConfigScreen
            screen = ConfigScreen(title, items=items, prefix=prefix, execute=execute)
            self.call_after_refresh(self.push_screen, screen)
            return
        try:
            suggestions = self.query_one("#cmd-suggestions", ListView)
        except Exception:
            return
        self._close_slash_menu()
        self._close_at_menu()
        self._config_panel_data = {"items": items, "prefix": prefix, "execute": execute}

        suggestions.clear()
        t = self.tui_theme
        for i, (label, _) in enumerate(items):
            marker = "\u25b8 " if i == 0 else "  "
            item = ListItem(Label(Text(f"{marker}{label}", style=t.variables.get('text_bright', '#a9b1d6'))))
            if i == 0:
                item.add_class("-highlight")
            suggestions.append(item)
        if suggestions.children:
            suggestions.index = 0
        suggestions.add_class("-visible")

    def show_config_info(self, title: str, text: str) -> None:
        """Show static information in the suggestions panel."""
        try:
            suggestions = self.query_one("#cmd-suggestions", ListView)
        except Exception:
            return
        self._close_slash_menu()
        self._close_at_menu()
        self._config_panel_data = {"info": True}
        t = self.tui_theme

        suggestions.clear()
        if title:
            suggestions.append(ListItem(Label(Text(f" {title} ", style=f"bold {t.primary}"))))
            suggestions.append(ListItem(Label(Text(""))))
        for line in text.strip().split("\n"):
            suggestions.append(ListItem(Label(Text(f"  {line}", style=t.variables.get('text_bright', '#a9b1d6')))))
        suggestions.add_class("-visible")

    def _dismiss_config_panel(self) -> None:
        self._config_panel_data = None
        try:
            s = self.query_one("#cmd-suggestions", ListView)
            s.clear()
            s.remove_class("-visible")
        except Exception:
            pass

    # ── slash menu navigation (called from ChatInput._on_key) ──

    def _navigate_slash_highlight(self, direction: int) -> None:
        """Move the highlight in the suggestion list. Does NOT modify input value."""
        count = len(self._slash_matches)
        self._slash_index = (self._slash_index + direction) % count
        idx = self._slash_index

        def _apply() -> None:
            try:
                suggestions = self.query_one("#cmd-suggestions", ListView)
            except Exception:
                return
            for i, child in enumerate(suggestions.children):
                if i == idx:
                    child.add_class("-highlight")
                else:
                    child.remove_class("-highlight")
            suggestions.index = idx

        self.call_after_refresh(_apply)

    def _close_slash_menu(self) -> None:
        """Close slash suggestions without modifying input."""
        self._slash_active = False
        self._slash_matches = []
        self._slash_index = -1
        self._suggestion_pos = -1
        try:
            self.query_one("#cmd-suggestions", ListView).remove_class("-visible")
        except Exception:
            pass

    def _dismiss_slash_menu(self) -> None:
        """Hide the slash menu and clear input."""
        self._close_slash_menu()
        inp = self.query_one("#chat-input", ChatInput)
        inp.value = ""
        inp.focus()

    # ── @ file suggestion menu ──

    @staticmethod
    def _get_at_suggestions(prefix: str) -> list[str]:
        """Return file/folder names from user home matching prefix."""
        import os
        home = os.path.expanduser("~")
        search_dir = home
        file_prefix = prefix

        if "/" in prefix:
            dir_part, file_prefix = prefix.rsplit("/", 1)
            search_dir = os.path.join(home, dir_part) if not os.path.isabs(dir_part) else dir_part

        if not os.path.isdir(search_dir):
            return []

        try:
            entries = os.listdir(search_dir)
        except PermissionError:
            return []

        q = file_prefix.lower()
        matches = []
        for e in sorted(entries):
            if q and not e.lower().startswith(q):
                continue
            full = os.path.join(search_dir, e)
            display = e + "/" if os.path.isdir(full) else e
            if dir_part := locals().get("dir_part"):
                display = dir_part + "/" + display
            matches.append(display)
        return matches[:20]

    def _navigate_at_highlight(self, direction: int) -> None:
        """Move the highlight in the @ file suggestion list."""
        count = len(self._at_matches)
        self._at_index = (self._at_index + direction) % count
        idx = self._at_index

        def _apply() -> None:
            try:
                suggestions = self.query_one("#cmd-suggestions", ListView)
            except Exception:
                return
            for i, child in enumerate(suggestions.children):
                if i == idx:
                    child.add_class("-highlight")
                else:
                    child.remove_class("-highlight")
            suggestions.index = idx

        self.call_after_refresh(_apply)

    def _close_at_menu(self) -> None:
        """Close @ file suggestions without modifying input."""
        self._at_active = False
        self._at_matches = []
        self._at_index = -1
        self._suggestion_pos = -1
        try:
            self.query_one("#cmd-suggestions", ListView).remove_class("-visible")
        except Exception:
            pass

    def _dismiss_at_menu(self) -> None:
        """Hide the @ file suggestion menu and clear input."""
        self._close_at_menu()
        inp = self.query_one("#chat-input", ChatInput)
        inp.value = ""
        inp.focus()

    # ── input ──

    def _focus_input(self) -> None:
        inp = self.query_one_optional("#chat-input")
        if inp is not None:
            inp.focus()

    def _get_suggestion_context(self, raw: str) -> tuple[str | None, str, int]:
        """Return (type, query, trigger_pos). @ after space takes priority over / at start."""
        at_pos = raw.rfind(" @")
        if at_pos >= 0:
            suffix = raw[at_pos + 2:]
            return ("at", suffix, at_pos + 1)
        s = raw.strip()
        if s.startswith("/"):
            return ("slash", s[1:].lower(), 0)
        return (None, "", -1)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "chat-input":
            return
        from cdh.tui.commands.registry import CommandRegistry
        names = [k for k, _ in CommandRegistry.list_commands()]
        raw = event.value
        try:
            suggestions = self.query_one("#cmd-suggestions", ListView)
        except Exception:
            return

        # Clear config panel when user types
        if raw:
            self._config_panel_data = None

        ptype, q, tpos = self._get_suggestion_context(raw)
        self._suggestion_pos = tpos

        if ptype == "slash":
            cmd_q = q.strip().split()[0] if q.strip() else ""

            # Close suggestions when space follows /command
            content = raw[1:] if raw.startswith("/") else ""
            if " " in content:
                self._slash_active = False
                self._slash_matches = []
                self._slash_index = -1
                self._at_active = False
                self._at_matches = []
                self._at_index = -1
                self._suggestion_pos = -1
                suggestions.clear()
                suggestions.remove_class("-visible")
                return

            top_level = sorted(set(n.split()[0] for n in names))
            self._slash_matches = [p for p in top_level if p.startswith(cmd_q)]
            if not self._slash_matches and cmd_q:
                self._slash_matches = [p for p in top_level if cmd_q in p]

            # Auto-close when exact command match is typed
            if cmd_q and len(self._slash_matches) == 1 and self._slash_matches[0] == cmd_q:
                self._slash_active = False
                self._slash_matches = []
                self._slash_index = -1
                self._at_active = False
                self._at_matches = []
                self._at_index = -1
                self._suggestion_pos = -1
                suggestions.clear()
                suggestions.remove_class("-visible")
                return

            self._slash_active = True
            self._slash_index = 0 if self._slash_matches else -1
            self._at_active = False
            self._at_matches = []
            self._at_index = -1

            handlers = CommandRegistry._handlers
            suggestions.clear()
            t = self.tui_theme
            if self._slash_matches:
                for i, m in enumerate(self._slash_matches):
                    desc = ""
                    entry = handlers.get(m)
                    if entry:
                        desc = entry[1]
                    else:
                        sub = next((s for s in names if s.startswith(m + " ")), None)
                        if sub and sub in handlers:
                            desc = handlers[sub][1]
                    label = Text.assemble(
                        (f"/{m}", f"bold {t.secondary}"),
                        ("  ", ""),
                        (desc if len(desc) < 40 else desc[:37] + "...", t.variables.get('text_dim', '#565f89')),
                    )
                    item = ListItem(Label(label))
                    if i == 0:
                        item.add_class("-highlight")
                    suggestions.append(item)
                suggestions.index = 0
                suggestions.add_class("-visible")
            else:
                suggestions.remove_class("-visible")
        elif ptype == "at":
            self._slash_active = False
            self._slash_matches = []
            self._slash_index = -1

            # Close suggestions when space follows the @ query
            q_part = raw[tpos:] if tpos >= 0 else ""
            if " " in q_part:
                self._at_active = False
                self._at_matches = []
                self._at_index = -1
                self._suggestion_pos = -1
                suggestions.clear()
                suggestions.remove_class("-visible")
                return

            if not q:
                q = ""
            self._at_matches = self._get_at_suggestions(q)
            self._at_active = True
            self._at_index = 0 if self._at_matches else -1

            suggestions.clear()
            if self._at_matches:
                for i, m in enumerate(self._at_matches):
                    item = ListItem(Label(f"@{m}"))
                    if i == 0:
                        item.add_class("-highlight")
                    suggestions.append(item)
                suggestions.index = 0
                suggestions.add_class("-visible")
            else:
                suggestions.remove_class("-visible")
        else:
            self._slash_active = False
            self._slash_matches = []
            self._slash_index = -1
            self._at_active = False
            self._at_matches = []
            self._at_index = -1
            self._suggestion_pos = -1
            if not self._config_panel_data:
                suggestions.clear()
                suggestions.remove_class("-visible")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "chat-input":
            return
        from cdh.tui.commands.registry import CommandRegistry
        raw = event.value.strip()

        selected_slash = self._get_selected_slash_command()
        selected_at = self._get_selected_at_file()

        event.input.clear()
        if not raw:
            return
        try:
            suggestions = self.query_one("#cmd-suggestions", ListView)
            suggestions.remove_class("-visible")
        except Exception:
            pass
        self._slash_active = False
        self._slash_matches = []
        self._slash_index = -1
        self._at_active = False
        self._at_matches = []
        self._at_index = -1
        event.input.focus()

        if raw.startswith("@"):
            if selected_at and not raw.lower().startswith(selected_at.lower()):
                raw = selected_at
            result = self._handle_at_file(raw)
            if result:
                self.handle_command_result(raw, result)
        elif raw.startswith("/"):
            if selected_slash and not raw.lower().startswith(selected_slash.lower()):
                raw = selected_slash
            result = CommandRegistry.dispatch(self, raw)
            if result:
                self.handle_command_result(raw, result)
        else:
            await self._send_message(raw)

    async def _send_message(self, text: str) -> None:
        chat = self.query_one("ChatPanel")
        footer = self.query_one(FooterBar)
        chat.add_message("user", text)
        chat.start_stream()
        footer.start_loading()

        try:
            async for chunk in self.agent.chat_stream(text):
                chat.add_stream_chunk(chunk)

            chat.finish_stream()
            self.turn_count += 1
            self.token_count = self.agent.total_tokens
            self._persist_session()
            self._refresh_right_panel()

        except Exception as e:
            chat.finish_stream()
            chat.add_message("error", f"Error: {e}")
        finally:
            footer.stop_loading()
            self._refresh_right_panel()

    def _refresh_right_panel(self) -> None:
        from cdh.tui.widgets.right_panel import RightPanel
        rp = self.query_one_optional("#right-sidebar", RightPanel)
        if rp is None:
            return
        tm = self.agent._task_manager
        rp._refresh_plan()
        rp._refresh_tasks(tm.list_tasks())
        rp._refresh_todos(tm.list_todos())

    def _get_selected_slash_command(self) -> str | None:
        """Return the currently highlighted slash command, or None."""
        if self._slash_active and self._slash_matches and self._slash_index >= 0:
            idx = self._slash_index % len(self._slash_matches)
            return f"/{self._slash_matches[idx]}"
        return None

    def _get_selected_at_file(self) -> str | None:
        """Return the currently highlighted @ file path, or None."""
        if self._at_active and self._at_matches and self._at_index >= 0:
            idx = self._at_index % len(self._at_matches)
            return f"@{self._at_matches[idx]}"
        return None

    def _handle_at_file(self, cmd_line: str) -> str:
        """Handle @filepath command to read a local file."""
        import os
        path = cmd_line[1:].strip()
        if not path:
            return "Usage: @<filepath> - read a file"

        user_dir = os.path.expanduser("~")
        if not os.path.isabs(path):
            path = os.path.join(user_dir, path)

        if not os.path.exists(path):
            return f"File not found: {path}"

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            lines = content.split("\n")
            if len(lines) > 100:
                content = "\n".join(lines[:100]) + f"\n\n... [{len(lines) - 100} more lines]"
            return f"File: {path}\n\n{content}"
        except Exception as e:
            return f"Error reading file: {e}"

    # ── actions ──

    def action_focus_chat_input(self) -> None:
        inp = self.query_one_optional("#chat-input")
        if inp is not None:
            inp.focus()

    def action_cycle_mode(self) -> None:
        """Ctrl+X: cycle through agent/plan/solo modes."""
        modes = ["agent", "plan", "solo"]
        idx = modes.index(self.current_mode) if self.current_mode in modes else 0
        idx = (idx + 1) % len(modes)
        self.current_mode = modes[idx]
        self.query_one(HeaderBar).sync(self)

    def action_toggle_right_panel(self) -> None:
        from cdh.tui.widgets.right_panel import RightPanel
        rp = self.query_one("#right-sidebar", RightPanel)
        if rp is not None:
            rp.toggle_class("-hidden")

    def handle_command_result(self, cmd: str, result: str) -> None:
        if not result:
            return
        title = cmd.lstrip("/").split()[0].capitalize() if cmd else "Result"
        self.show_config_info(title, result.strip())

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle click/Enter on slash-command suggestion list or config panel."""
        if event.list_view.id != "cmd-suggestions":
            return
        if not event.item:
            return

        # Config panel selection
        if self._config_panel_data:
            event.stop()
            data = self._config_panel_data
            self._dismiss_config_panel()
            if not data.get("info") and data.get("items"):
                idx = event.list_view.index
                if idx is not None and 0 <= idx < len(data["items"]):
                    _, value = data["items"][idx]
                    cmd = f"/{data.get('prefix', '')}{value}"
                    if data.get("execute", False):
                        from cdh.tui.commands.registry import CommandRegistry
                        result = CommandRegistry.dispatch(self, cmd)
                        if result:
                            self.handle_command_result(cmd, result)
            self._focus_input()
            return

        # Slash suggestion selection
        label = event.item.query_one(Label)
        if label:
            t = label.renderable
            cmd = t.plain if isinstance(t, Text) else str(t)
            from cdh.tui.commands.registry import CommandRegistry
            result = CommandRegistry.dispatch(self, cmd)
            if result:
                self.handle_command_result(cmd, result)
            elif not self._config_panel_data:
                suggestions = self.query_one("#cmd-suggestions", ListView)
                suggestions.remove_class("-visible")
            inp = self.query_one("#chat-input", ChatInput)
            inp.value = ""
            self._slash_active = False
            self._slash_matches = []
            self._slash_index = -1
            inp.focus()
