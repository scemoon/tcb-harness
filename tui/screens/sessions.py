import json
from time import monotonic

from textual.app import ComposeResult
from textual.binding import Binding
from textual.events import ScreenResume
from textual.screen import ModalScreen
from textual import getters
from textual.widget import Widget
from textual import widgets
from textual import containers
from textual import on


from cdha.config import CLOUD_DEV_HARNESS_DIR

from tui.app import A2TUIApp
from tui.db import DB
from tui.widgets.grid_select import GridSelect
from tui.widgets.session_grid_select import (
    SessionGridSelect,
    PAGE_INDICATOR_ID,
)
from tui.widgets.session_summary import SessionSummary
from tui.session_tracker import SessionDetails


CONFIRM_TIMEOUT = 5.0
INSTRUCTIONS_NO_SESSIONS = "Your sessions will be shown here."


class SessionsScreen(ModalScreen[str]):
    CSS_PATH = "sessions.tcss"
    BINDINGS = [
        Binding("escape", "dismiss", "Dismiss"),
        Binding("d", "delete_session", "Delete"),
    ]

    app: getters.app[A2TUIApp] = getters.app(A2TUIApp)
    session_grid_select = getters.query_one(SessionGridSelect)
    _delete_confirm_time: float = 0.0

    def compose(self) -> ComposeResult:
        with containers.Center(id="title-container"):
            yield widgets.Label("Sessions")
        yield widgets.Static(INSTRUCTIONS_NO_SESSIONS, classes="instructions")
        yield widgets.Static("", id=PAGE_INDICATOR_ID)
        yield SessionGridSelect(self.app.session_tracker, id="session-grid")
        yield widgets.Footer()

    @property
    def focus_chain(self) -> list[Widget]:
        return [self.session_grid_select]

    async def action_delete_session(self) -> None:
        now = monotonic()
        if now - self._delete_confirm_time > CONFIRM_TIMEOUT:
            self._delete_confirm_time = now
            self.notify(
                "Press [b]d[/b] again to confirm deletion",
                title="Delete session",
                timeout=CONFIRM_TIMEOUT,
            )
            return

        self._delete_confirm_time = 0.0
        highlighted = self.session_grid_select.highlighted
        if highlighted is None:
            return
        try:
            widget = self.session_grid_select.children[highlighted]
        except IndexError:
            return
        if not isinstance(widget, SessionSummary):
            return
        session_details = widget.session_details
        if session_details is None:
            return
        session_pk = session_details.session_pk
        if session_pk is None:
            self.notify("Cannot delete unsaved session", severity="error")
            return

        db = DB()
        session = await db.session_get(session_pk)
        if session is None:
            return

        agent_session_id = session.get("agent_session_id", "")
        title = session.get("title", "Untitled") or "Untitled"

        await db.session_delete(session_pk)

        if agent_session_id:
            session_file = CLOUD_DEV_HARNESS_DIR / "sessions" / f"{agent_session_id}.json"
            if session_file.exists():
                session_file.unlink()

        mode_name = session_details.mode_name
        if self.app.session_tracker.get_session(mode_name):
            self.app.session_tracker.close_session(mode_name)

        await widget.remove()
        self.notify(f"Deleted session: {title}")

    async def _load_historical_sessions(self) -> None:
        seen_pks: set[int] = set()
        merged: list[SessionDetails] = []

        for session in self.app.session_tracker.ordered_sessions:
            if session.session_pk is not None and session.session_pk in seen_pks:
                continue
            if session.session_pk is not None:
                seen_pks.add(session.session_pk)
            merged.append(session)

        db = DB()
        sessions = await db.session_get_recent(max_results=20)
        for session in sessions or []:
            session_id = session["id"]
            if session_id in seen_pks:
                continue
            seen_pks.add(session_id)
            cwd = ""
            if meta_json := session.get("meta_json"):
                try:
                    cwd = json.loads(meta_json).get("cwd", "")
                except Exception:
                    pass
            merged.append(
                SessionDetails(
                    index=session_id,
                    mode_name=f"session-{session_id}",
                    session_pk=session_id,
                    title=session.get("title", "Untitled") or "Untitled",
                    subtitle=session.get("agent", ""),
                    path=cwd,
                    state="idle",
                )
            )

        self.session_grid_select.set_sessions(merged)

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
