---
name: session-tabs-debugging
description: How to debug session tabs / multi-session UI bugs in this TUI project
source: auto-skill
extracted_at: '2026-06-06-02'
---

# Session Tabs / Multi-Session UI Debugging

## Architecture Overview

- **`SessionTracker`** (`tui/session_tracker.py`) — tracks all `SessionDetails` in memory, indexed by `mode_name`
- **`session_update_signal`** — `Signal[tuple[str, SessionDetails | None]]` published when sessions change
- **`SessionsTabs`** — renders tab labels in header; subscribes to `session_update_signal`
- **`SessionGridSelect`** — renders session list in sessions picker; subscribes to `session_update_signal`
- **`SessionDetails`** dataclass has `mode_name` (string like `"session-3"`), `session_pk` (DB primary key), `title`, `state`
- **Mode** — each session has a Textual mode (same as `mode_name`). Mode == Screen instance

## Common Patterns

### Adding a new session
1. `app.new_session_screen(get_screen, session_pk)` → `session_tracker.new_session(session_pk)` → create `SessionDetails` with auto-increment `mode_name`
2. `add_mode(mode_name, make_screen)` — registers screen factory
3. `switch_mode(mode_name)` — activates the screen
4. `session_update_signal.publish((mode_name, session_details))` — notifies `SessionsTabs` and `SessionGridSelect` to mount widgets

### Closing a session (Bug 2 pattern)
1. User closes → `Conversation` posts `SessionClose(screen.id)`
2. `MainScreen.on_session_close()` → `session_tracker.close_session(current_mode)` → `signal.publish((mode_name, None))`
3. `SessionsTabs.handle_session_update_signal()` — removes tab, updates `current_session` to remaining tab
4. `SessionGridSelect.handle_session_update_signal()` — removes `SessionSummary` widget

### Loading a historical session (Bug 1 pattern)
1. User selects from sessions list → `dismiss(mode_name)` where `mode_name = "session-{pk}"`
2. `action_sessions()` → parse `session_pk` from mode_name → `_load_session(pk)`
3. **`CRITICAL`: check if mode already exists** via `_find_mode_for_session_pk(pk)` — if yes, `switch_mode()` instead of creating new session
4. If new: `launch_agent()` → `new_session_screen(get_screen, session_pk)` → `agent.run()` → `acp_load_session()` or `acp_new_session()`
5. `acp_load_session()` reads DB title → sends `SessionUpdate(name=title)` → `on_session_update()` updates `_agent_session_title`

### Title update flow (Bug 3 pattern)
1. `Conversation._agent_session_title` var holds the session name
2. `update_title()` — if `_agent_session_title` is set, use it; else use agent name + project path
3. `update_title()` must be called when:
   - `ScreenResume` fires on `MainScreen` (`on_screen_resume()`)
   - `SessionUpdate(name=...)` is received by `MainScreen.on_session_update()`
4. **`MainScreen` and `Conversation` each have their own `_agent_session_title`** — update BOTH

### Agent initialization issues
- `ACP_INITIALIZE=false` (onecode agent default) means no `acp_initialize()` call
- In this case, `run()` gets `session_id` from constructor (already set)
- If `session_id is None` in this path → call `acp_new_session()` to create DB record
- Always send `AgentReady` at the end of `run()` regardless of `ACP_INITIALIZE`

## Known Gotchas

- **Mode name != session_pk**: `mode_name` is auto-increment (`session-1`, `session-2`...) but `session_pk` comes from DB. For historical sessions loaded from DB, `mode_name = f"session-{pk}"` happens to match, but for new sessions created in this run, they differ.
- **Never remove `signal.publish()` from `close_session()`** — that's what triggers UI removal
- **Textual `@on` decorator** requires explicit registration — `def _on_screen_resume` without `@on` won't fire