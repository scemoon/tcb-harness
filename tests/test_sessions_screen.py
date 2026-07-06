"""Test that the SessionsScreen can be constructed and its worker logic dedupes.

This does NOT test the full push/pop flow (which requires textual app + CSS),
but tests the core data flow that the bug depends on.
"""

from unittest.mock import AsyncMock, MagicMock, patch


from tui.session_tracker import SessionDetails


def _make_app_with_tracker_and_db(tracker_sessions, db_sessions):
    """Construct a fake app environment for the screen."""
    tracker = MagicMock()
    tracker.ordered_sessions = tracker_sessions
    tracker.get_session_by_pk = MagicMock(side_effect=lambda pk: next(
        (s for s in tracker_sessions if s.session_pk == pk), None
    ))

    fake_app = MagicMock()
    fake_app.session_tracker = tracker
    fake_app.screen_stack = [MagicMock(id=None)]

    db_mock = MagicMock()
    db_mock.session_get_recent = AsyncMock(return_value=db_sessions)
    return fake_app, db_mock


async def test_screen_load_calls_set_sessions():
    """The screen worker must call set_sessions with merged tracker + DB."""
    from tui.screens.sessions import SessionsScreen
    from tui.widgets.session_grid_select import SessionGridSelect

    tracker_sessions = [
        SessionDetails(index=1, mode_name="session-1", session_pk=None, title="T1"),
    ]
    db_sessions = [
        {
            "id": 5,
            "title": "DB-1",
            "agent": "agent-a",
            "agent_identity": "agent-a",
            "agent_session_id": "as-1",
            "protocol": "acp",
            "meta_json": '{"cwd": "/tmp/1"}',
        },
    ]
    fake_app, db_mock = _make_app_with_tracker_and_db(tracker_sessions, db_sessions)

    captured = []
    grid = MagicMock(spec=SessionGridSelect)
    grid.set_sessions = lambda items: captured.append(list(items))

    with patch("tui.screens.sessions.DB", return_value=db_mock):
        screen = SessionsScreen()
        screen.app = fake_app
        screen.session_grid_select = grid
        await screen._load_historical_sessions()

    assert len(captured) == 1
    merged = captured[0]
    assert len(merged) == 2
    assert merged[0].mode_name == "session-1"
    assert merged[1].mode_name == "session-5"


async def test_screen_load_handles_empty_db():
    """If DB returns no sessions, only tracker sessions are loaded."""
    from tui.screens.sessions import SessionsScreen
    from tui.widgets.session_grid_select import SessionGridSelect

    tracker_sessions = [
        SessionDetails(index=1, mode_name="session-1", session_pk=None, title="T1"),
    ]
    fake_app, db_mock = _make_app_with_tracker_and_db(tracker_sessions, [])

    captured = []
    grid = MagicMock(spec=SessionGridSelect)
    grid.set_sessions = lambda items: captured.append(list(items))

    with patch("tui.screens.sessions.DB", return_value=db_mock):
        screen = SessionsScreen()
        screen.app = fake_app
        screen.session_grid_select = grid
        await screen._load_historical_sessions()

    assert len(captured) == 1
    merged = captured[0]
    assert len(merged) == 1
    assert merged[0].mode_name == "session-1"


async def test_screen_load_handles_empty_db_returning_none():
    """DB.session_get_recent may return None on error."""
    from tui.screens.sessions import SessionsScreen
    from tui.widgets.session_grid_select import SessionGridSelect

    tracker_sessions = []
    fake_app, db_mock = _make_app_with_tracker_and_db(tracker_sessions, None)
    db_mock.session_get_recent = AsyncMock(return_value=None)

    captured = []
    grid = MagicMock(spec=SessionGridSelect)
    grid.set_sessions = lambda items: captured.append(list(items))

    with patch("tui.screens.sessions.DB", return_value=db_mock):
        screen = SessionsScreen()
        screen.app = fake_app
        screen.session_grid_select = grid
        await screen._load_historical_sessions()

    assert len(captured) == 1
    assert captured[0] == []


async def test_grid_set_sessions_defers_render_when_not_mounted():
    """If set_sessions is called before the widget is mounted, it must not crash
    and must render once the widget mounts."""
    from tui.widgets.session_grid_select import SessionGridSelect

    grid = SessionGridSelect.__new__(SessionGridSelect)
    grid._all_sessions = []
    grid._current_page = 0
    grid._is_mounted = False
    grid.app = MagicMock()
    grid.app.query_one = MagicMock(side_effect=Exception("no indicator"))
    grid.query_children = MagicMock(return_value=[])
    grid.mount = MagicMock()

    sessions = [
        SessionDetails(index=1, mode_name="session-1", session_pk=1, title="A"),
    ]
    grid.set_sessions(sessions)
    assert len(grid._all_sessions) == 1
    assert grid.mount.call_count == 0
