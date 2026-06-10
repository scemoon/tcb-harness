from textual.app import ComposeResult
from textual import getters
from textual.binding import Binding

from tui.app import A2TUIApp
from tui.constants import SESSION_GRID_PAGE_SIZE
from tui.widgets.grid_select import GridSelect
from tui.widgets.session_summary import SessionSummary
from tui.session_tracker import SessionTracker, SessionDetails


PAGE_INDICATOR_ID = "session-grid-page-indicator"


class SessionGridSelect(GridSelect):
    FOCUS_ON_CLICK = True
    CURSOR_GROUP = Binding.Group("Select")
    BINDINGS = [
        Binding("]", "next_page", "Next page"),
        Binding("[", "prev_page", "Prev page"),
    ]
    app: getters.app[A2TUIApp] = getters.app(A2TUIApp)

    def __init__(
        self,
        session_tracker: SessionTracker,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self.session_tracker = session_tracker
        self._all_sessions: list[SessionDetails] = []
        self._current_page: int = 0
        super().__init__(
            id=id,
            classes=classes,
            min_column_width=36,
        )

    @property
    def page_size(self) -> int:
        return SESSION_GRID_PAGE_SIZE

    @property
    def page_count(self) -> int:
        total = len(self._all_sessions)
        if total == 0:
            return 0
        return (total + self.page_size - 1) // self.page_size

    @property
    def current_page(self) -> int:
        return self._current_page

    def allow_focus(self) -> bool:
        return True

    def on_mount(self) -> None:
        self.app.session_update_signal.subscribe(
            self, self.handle_session_update_signal
        )
        if self._all_sessions:
            self._render_page()
        self.call_after_refresh(self._ensure_focus)

    def _ensure_focus(self) -> None:
        if (
            self.is_mounted
            and not self._closing
            and self.focusable
            and self.screen is not None
            and self.screen.is_mounted
        ):
            self.focus()

    def update_current(self, current_mode: str) -> None:
        for index, child in enumerate(self.query_children(SessionSummary)):
            if child.session_details is None:
                continue
            is_current = child.session_details.mode_name == current_mode
            child.current = is_current
            if is_current:
                self.highlighted = index

    async def handle_session_update_signal(
        self, update: tuple[str, SessionDetails | None]
    ) -> None:
        mode_name, details = update
        if details is None:
            if session_summary := self.query_one_optional(
                f"#{mode_name}", SessionSummary
            ):
                await session_summary.remove()
            for i, existing in enumerate(self._all_sessions):
                if existing.mode_name == mode_name:
                    self._all_sessions.pop(i)
                    break
            self._clamp_page()
            self._render_page()
            return

        if session_summary := self.query_one_optional(
            f"#{mode_name}", SessionSummary
        ):
            session_summary.session_details = details
            for existing in self._all_sessions:
                if existing.mode_name == mode_name:
                    existing.title = details.title
                    existing.subtitle = details.subtitle
                    existing.path = details.path
                    existing.state = details.state
                    break
            return

        if details.session_pk is not None:
            for i, existing in enumerate(self._all_sessions):
                if existing.session_pk == details.session_pk:
                    self._all_sessions[i] = details
                    self._render_page()
                    return

        self._all_sessions.append(details)
        self._render_page()

    def compose(self) -> ComposeResult:
        yield from ()

    def set_sessions(self, sessions: list[SessionDetails]) -> None:
        deduped: list[SessionDetails] = []
        seen: set[int] = set()
        for session in sessions:
            if session.session_pk is not None:
                if session.session_pk in seen:
                    continue
                seen.add(session.session_pk)
            deduped.append(session)
        self._all_sessions = deduped
        self._current_page = 0
        if self.is_mounted:
            self._render_page()

    def _current_page_items(self) -> list[SessionDetails]:
        if not self._all_sessions:
            return []
        start = self._current_page * self.page_size
        end = start + self.page_size
        return self._all_sessions[start:end]

    def _clamp_page(self) -> None:
        if self._current_page >= self.page_count and self.page_count > 0:
            self._current_page = self.page_count - 1

    def _render_page(self) -> None:
        if not self.is_mounted or self._closing or self._closed:
            return
        if self.screen is None or not self.screen.is_mounted:
            return

        current_items = self._current_page_items()
        seen: dict[str, SessionDetails] = {}
        for session in current_items:
            seen[session.mode_name] = session
        unique_items = list(seen.values())

        for child in list(self.query_children(SessionSummary)):
            if child.id not in seen:
                try:
                    child.remove()
                except Exception:
                    pass

        existing_ids = {c.id for c in self.query_children(SessionSummary)}
        for session in unique_items:
            if session.mode_name not in existing_ids:
                try:
                    self.mount(SessionSummary(session, id=session.mode_name))
                except Exception:
                    pass

        self._apply_current()
        self._update_page_indicator()
        self.highlighted = 0 if unique_items else None

        if unique_items:
            self.call_later(self._ensure_focus)

    def _apply_current(self) -> None:
        current_mode = self._current_screen_mode_name()
        for index, child in enumerate(self.query_children(SessionSummary)):
            if child.session_details is None:
                continue
            is_current = child.session_details.mode_name == current_mode
            child.current = is_current
            if is_current:
                self.highlighted = index

    def _current_screen_mode_name(self) -> str | None:
        try:
            screen = self.app.screen_stack[0]
        except (IndexError, AttributeError):
            return None
        return getattr(screen, "id", None)

    def _update_page_indicator(self) -> None:
        try:
            indicator = self.app.query_one(f"#{PAGE_INDICATOR_ID}")
        except Exception:
            return
        total = len(self._all_sessions)
        if total == 0:
            indicator.update("")
            return
        indicator.update(
            f"Page {self._current_page + 1} / {self.page_count} · 共 {total} 项"
        )

    def action_next_page(self) -> None:
        if self._current_page + 1 < self.page_count:
            self._current_page += 1
            self._render_page()

    def action_prev_page(self) -> None:
        if self._current_page > 0:
            self._current_page -= 1
            self._render_page()
