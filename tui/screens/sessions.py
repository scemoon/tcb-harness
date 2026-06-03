import json

from textual.app import ComposeResult
from textual.binding import Binding
from textual.events import ScreenResume
from textual.screen import ModalScreen
from textual import getters
from textual.widget import Widget
from textual import widgets
from textual import containers
from textual import on


from tui.app import A2TUIApp
from tui.db import DB
from tui.widgets.grid_select import GridSelect
from tui.widgets.session_grid_select import SessionGridSelect
from tui.widgets.session_summary import SessionSummary
from tui.session_tracker import SessionDetails


INSTRUCTIONS_NO_SESSIONS = "Your sessions will be shown here."


class SessionsScreen(ModalScreen[str]):
    CSS_PATH = "sessions.tcss"
    BINDINGS = [Binding("escape", "dismiss", "Dismiss")]

    app: getters.app[A2TUIApp] = getters.app(A2TUIApp)
    session_grid_select = getters.query_one(SessionGridSelect)

    def compose(self) -> ComposeResult:
        with containers.Center(id="title-container"):
            yield widgets.Label("Sessions")
        yield widgets.Static(INSTRUCTIONS_NO_SESSIONS, classes="instructions")
        yield SessionGridSelect(self.app.session_tracker)
        yield widgets.Footer()

    @property
    def focus_chain(self) -> list[Widget]:
        return [self.session_grid_select]

    async def _load_historical_sessions(self) -> None:
        db = DB()
        sessions = await db.session_get_recent(max_results=20)
        if not sessions:
            return
        for session in sessions:
            session_id = session["id"]
            mode_name = f"session-{session_id}"
            if self.app.session_tracker.get_session(mode_name):
                continue
            cwd = ""
            if meta_json := session.get("meta_json"):
                try:
                    cwd = json.loads(meta_json).get("cwd", "")
                except Exception:
                    pass
            session_details = SessionDetails(
                index=session_id,
                mode_name=mode_name,
                session_pk=session_id,
                title=session.get("title", "Untitled") or "Untitled",
                subtitle=session.get("agent", ""),
                path=cwd,
                state="idle",
            )
            await self.session_grid_select.mount(
                SessionSummary(session_details, id=mode_name)
            )

    def on_mount(self) -> None:
        self.run_worker(self._load_historical_sessions())

    async def _on_screen_resume(self, event: ScreenResume) -> None:
        current_mode = self.app.screen_stack[0].id
        for instructions in self.query(".instructions"):
            instructions.display = not self.session_grid_select.children
        if current_mode is not None:
            self.session_grid_select.update_current(current_mode)

    def _on_screen_suspend(self) -> None:
        current_mode = self.app.screen_stack[0].id
        if current_mode is not None:
            self.session_grid_select.update_current(current_mode)

    @on(GridSelect.Selected)
    def on_selected(self, event: GridSelect.Selected) -> None:
        if (
            isinstance(event.widget, SessionSummary)
            and event.widget.session_details is not None
        ):
            mode_name = event.widget.session_details.mode_name
            self.dismiss(mode_name)
