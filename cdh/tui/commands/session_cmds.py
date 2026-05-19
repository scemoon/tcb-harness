from __future__ import annotations

from cdh.tui.commands.registry import command


@command("session list", "List all sessions", "")
def cmd_session_list(app, *args):
    sessions = app.session_store.list_all()
    if not sessions:
        return "No sessions found."
    items = []
    for s in sessions:
        updated = s.updated_at.strftime("%Y-%m-%d %H:%M") if s.updated_at else "N/A"
        sid = s.id[:8]
        items.append((f"{s.name:<24}  {sid}  {updated}  [{s.mode}]", s.id))
    app.show_config_panel("Sessions", items, "session load ", execute=True)
    return ""


@command("session new", "Create a new session", "[name...]")
def cmd_session_new(app, *args):
    name = " ".join(args) if args else f"Session {len(app.session_store.list_all()) + 1}"
    record = app.session_store.create(name=name, mode=app.current_mode)
    app._session = record
    return f"Created session: {record.id[:8]}... ({name})"


@command("session load", "Load a session by ID or name", "<id|name>")
def cmd_session_load(app, *args):
    if not args:
        return "Usage: /session load <id|name>"
    query = args[0]
    sessions = app.session_store.list_all()
    for s in sessions:
        if s.id.startswith(query) or query in s.name:
            app._session = s
            app.current_mode = s.mode or app.current_mode
            return f"Loaded session: {s.name} ({s.id[:8]}...)"
    return f"Session not found: {query}"
