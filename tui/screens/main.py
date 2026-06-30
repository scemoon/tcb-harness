import asyncio
from functools import partial
from pathlib import Path
import random

from textual import on
from textual.app import ComposeResult
from textual import getters
from textual.binding import Binding
from textual.command import Hit, Hits, Provider, DiscoveryHit
from textual.content import Content
from textual.events import ScreenResume
from textual.screen import Screen
from textual.reactive import var, reactive
from textual.widgets import Footer, OptionList, DirectoryTree, Tree
from textual import containers
from textual.widget import Widget


from tui.app import A2TUIApp
from tui import messages
from tui.agent_schema import Agent
from tui.acp import messages as acp_messages

from tui.widgets.context_stats import ContextStats
from tui.widgets.modified_files import ModifiedFiles
from tui.widgets.plan import Plan
from tui.widgets.throbber import Throbber
from tui.widgets.conversation import Conversation
from tui.widgets.project_directory_tree import ProjectDirectoryTree
from tui.widgets.side_bar import SideBar
from tui.widgets.session_tabs import SessionsTabs, SessionLabel


class ModeProvider(Provider):
    async def search(self, query: str) -> Hits:
        """Search for Python files."""
        matcher = self.matcher(query)

        screen = self.screen
        assert isinstance(screen, MainScreen)

        for mode in sorted(
            screen.conversation.modes.values(), key=lambda mode: mode.name
        ):
            command = mode.name
            score = matcher.match(command)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(command),
                    partial(screen.conversation.set_mode, mode.id),
                    help=mode.description,
                )

    async def discover(self) -> Hits:
        screen = self.screen
        assert isinstance(screen, MainScreen)

        for mode in sorted(
            screen.conversation.modes.values(), key=lambda mode: mode.name
        ):
            yield DiscoveryHit(
                mode.name,
                partial(screen.conversation.set_mode, mode.id),
                help=mode.description,
            )


class MainScreen(Screen, can_focus=False):
    AUTO_FOCUS = "Conversation Prompt TextArea"

    CSS_PATH = "main.tcss"

    COMMANDS = {ModeProvider}

    SESSION_NAVIGATION_GROUP = Binding.Group(description="Sessions")
    BINDINGS = [
        Binding("ctrl+b,f20", "show_sidebar", "Sidebar", priority=True),
        Binding("ctrl+g", "go_home", "Home", priority=True),
        Binding(
            "ctrl+left_square_bracket",
            "session_previous",
            "Previous session",
            group=SESSION_NAVIGATION_GROUP,
        ),
        Binding(
            "ctrl+right_square_bracket",
            "session_next",
            "Next session",
            group=SESSION_NAVIGATION_GROUP,
        ),
    ]

    BINDING_GROUP_TITLE = "Screen"
    busy_count = var(0)
    throbber: getters.query_one[Throbber] = getters.query_one("#throbber")
    conversation = getters.query_one(Conversation)
    side_bar = getters.query_one(SideBar)
    project_directory_tree = getters.query_one("#project_directory_tree")

    column = reactive(False)
    column_width = reactive(80)
    scrollbar = reactive("")
    project_path: var[Path | None] = var(Path("./").expanduser().absolute())

    app = getters.app(A2TUIApp)

    def __init__(
        self,
        project_path: Path,
        agent: Agent | None = None,
        agent_session_id: str | None = None,
        agent_session_title: str | None = None,
        session_pk: int | None = None,
        initial_prompt: str | None = None,
    ) -> None:
        super().__init__()
        self._project_update_lock = asyncio.Lock()
        self.set_reactive(MainScreen.project_path, project_path)
        self._agent = agent
        self._agent_session_id = agent_session_id
        self._agent_session_title = agent_session_title
        self._session_pk = session_pk
        self._initial_prompt = initial_prompt

    def watch_title(self, title: str) -> None:
        self.app.update_terminal_title()

    def get_loading_widget(self) -> Widget:
        throbber = self.app.settings.get("ui.throbber", str)
        if throbber == "quotes":
            from tui.app import QUOTES
            from tui.widgets.future_text import FutureText

            quotes = QUOTES.copy()
            random.shuffle(quotes)
            return FutureText([Content(quote) for quote in quotes])
        return super().get_loading_widget()

    @on(ScreenResume)
    def on_screen_resume(self, event: ScreenResume) -> None:
        self.conversation.update_title()

    def compose(self) -> ComposeResult:
        panels: list[SideBar.Panel] = [
            SideBar.Panel(
                "Plan",
                Plan([], placeholder="no plan yet"),
            ),
            SideBar.Panel(
                "Context",
                ContextStats(id="context-stats"),
                collapsed=False,
                id="context-panel",
            ),
        ]
        # panels.append(
        #     SideBar.Panel(
        #         "Project",
        #         ProjectDirectoryTree(
        #             self.project_path,
        #             id="project_directory_tree",
        #         ),
        #         flex=True,
        #         id="project-panel",
        #     ),
        # )
        panels.append(
            SideBar.Panel(
                "Modified Files",
                ModifiedFiles(self.project_path, id="modified_files"),
                collapsed=False,
                id="modified-files-panel",
            ),
        )
        with containers.Center():
            yield SideBar(*panels)
            yield Conversation(
                self.project_path,
                self._agent,
                self._agent_session_id,
                self._session_pk,
                initial_prompt=self._initial_prompt,
            ).data_bind(
                project_path=MainScreen.project_path,
                column=MainScreen.column,
            )
        yield Footer()

    def run_prompt(self, prompt: str) -> None:
        self.conversation

    def update_node_styles(self, animate: bool = True) -> None:
        self.conversation.update_node_styles(animate=animate)
        self.query_one(Footer).update_node_styles(animate=animate)
        self.query_one(SideBar).update_node_styles(animate=animate)

    def action_session_previous(self) -> None:
        if self.screen.id is not None:
            self.post_message(messages.SessionNavigate(self.screen.id, -1))

    def action_session_next(self) -> None:
        if self.screen.id is not None:
            self.post_message(messages.SessionNavigate(self.screen.id, +1))

    @on(messages.ProjectDirectoryUpdated)
    async def on_project_directory_update(self, event: messages.ProjectDirectoryUpdated) -> None:
        async with self._project_update_lock:
            new_dir = event.project_dir
            sidebar = self.query_one(SideBar)
            if new_dir is None:
                self.project_path = None
                if mf := sidebar.query_one_optional("#modified_files", ModifiedFiles):
                    mf.refresh_files()
                self._swap_directory_watcher(None)
                return
            if self.project_path == new_dir:
                if mf := sidebar.query_one_optional("#modified_files", ModifiedFiles):
                    mf.refresh_files()
                return
            self.project_path = new_dir
            if mf := sidebar.query_one_optional("#modified_files", ModifiedFiles):
                mf.refresh_files()
            self._swap_directory_watcher(new_dir)

    def _swap_directory_watcher(self, project_path: Path | None) -> None:
        try:
            self.conversation.directory_watcher_swap(project_path)
        except Exception:
            pass


    @on(DirectoryTree.FileSelected, "ProjectDirectoryTree")
    def on_project_directory_tree_selected(self, event: Tree.NodeSelected):
        if (data := event.node.data) is not None:
            self.conversation.insert_path_into_prompt(data.path)

    @on(acp_messages.Plan)
    async def on_acp_plan(self, message: acp_messages.Plan):
        message.stop()
        from tui.widgets.plan import entries_from_dicts
        self.query_one("SideBar Plan", Plan).entries = entries_from_dicts(message.entries)

    @on(messages.SessionUpdate)
    async def on_session_update(self, event: messages.SessionUpdate) -> None:
        if event.name is not None:
            self._agent_session_title = event.name
            self.conversation._agent_session_title = event.name
        if self.id is not None:
            self.app.session_tracker.update_session(
                self.id,
                title=event.name,
                subtitle=event.subtitle,
                path=event.path,
                state=event.state,
                session_pk=event.session_pk,
            )
        if event.name is not None:
            self.conversation.update_title()

    @on(messages.SessionClose)
    async def on_session_close(self, event: messages.SessionClose) -> None:

        if self.id is None:
            return
        current_mode = self.id
        session_tracker = self.app.session_tracker

        if session_tracker.session_count <= 1:
            session_tracker.close_session(current_mode)
            self.app.exit()
            return

        next_mode = session_tracker.session_cursor_move(current_mode, +1)
        session_tracker.close_session(current_mode)
        if next_mode:
            self.app.switch_mode(next_mode)
            # Directly remove the closed tab from the visible screen's SessionsTabs
            if sessions_tabs := self.app.screen.query_one_optional(
                SessionsTabs
            ):
                if current_tab := sessions_tabs.query_one_optional(
                    f"#{current_mode}", SessionLabel
                ):
                    await current_tab.remove()
        self.app.call_later(self.app.remove_mode, current_mode)

    def on_mount(self) -> None:
        import gc

        gc.freeze()
        if self.query_one(SideBar).has_panel("project-panel"):
            for tree in self.query("#project_directory_tree").results(DirectoryTree):
                tree.data_bind(path=MainScreen.project_path)
            for tree in self.query(DirectoryTree):
                tree.guide_depth = 3
        mf = self.query_one("#modified_files", ModifiedFiles)
        mf.data_bind(path=MainScreen.project_path)

    @on(OptionList.OptionHighlighted)
    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if event.option.id is not None:
            self.conversation.prompt.suggest(event.option.id)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "show_sidebar" and self.side_bar.has_focus_within:
            return False
        return True

    def action_show_sidebar(self) -> None:
        self.side_bar.query_one("Collapsible CollapsibleTitle").focus()

    def action_focus_prompt(self) -> None:
        self.conversation.focus_prompt()

    async def action_go_home(self) -> None:
        self.app.push_screen("store")

    @on(SideBar.Dismiss)
    def on_side_bar_dismiss(self, message: SideBar.Dismiss):
        message.stop()
        self.conversation.focus_prompt()

    def watch_column(self, column: bool) -> None:
        self.conversation.styles.max_width = (
            f"{max(40, self.column_width)}%" if column else None
        )

    def watch_column_width(self, column_width: int) -> None:
        self.conversation.styles.max_width = (
            f"{max(40, column_width)}%" if self.column else None
        )

    def watch_scrollbar(self, old_scrollbar: str, scrollbar: str) -> None:
        if old_scrollbar:
            self.conversation.remove_class(f"-scrollbar-{old_scrollbar}")
        if scrollbar:
            self.conversation.add_class(f"-scrollbar-{scrollbar}")
