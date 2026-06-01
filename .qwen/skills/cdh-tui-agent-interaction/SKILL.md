---
name: cdh-tui-agent-interaction
description: How TUI interacts with Agent via ACP protocol — architecture, plan flow, session management
source: auto-skill
extracted_at: '2026-06-01T09:05:00.000Z'
---

# CDH TUI-Agent Interaction Architecture

## Context

The TUI (Textual app in `tui/`) communicates with the CDH Agent running as a subprocess via JSON-RPC over stdin/stdout, using the **ACP (Agent Communication Protocol)**.

## Architecture Overview

```
cdh CLI (cdh/cli.py)
    └─> A2TUIApp (tui/app.py)
            └─> MainScreen (tui/screens/main.py)
                    └─> Conversation (tui/widgets/conversation.py)
                            └─> Agent (tui/acp/agent.py)
                                    └─> [subprocess: CDH ACP Adapter]
                                            └─> AgentEngine (cdha/agent/engine.py)
```

## ACP Session Flow

### 1. Initialization (tui/acp/agent.py)
```
TUI ── initialize() ───────────────────────────> Agent
TUI ── session/new() ──────────────────────────> Agent
TUI <─ protocolVersion, capabilities, sessionId  (response)
TUI <─ [READY]                                (AgentReady message)
```

### 2. Prompt/Response (tui/acp/agent.py:session_prompt → cdh_agent_acp.py:session_prompt)
```
TUI ── session/prompt(prompt, sessionId) ─────> Agent (JSON-RPC via stdin)
Agent processes in AgentEngine.chat_stream()
Agent ── session/update notifications ────────> TUI (JSON-RPC via stdout)
     ├─ agent_message_chunk (text deltas)
     ├─ agent_thought_chunk (thinking blocks)
     ├─ tool_call / tool_call_update
     ├─ plan (task entries)
     └─ ... more update types ...
TUI <─ {result: {stopReason: "stop"}}         (final response)
```

## Key Files

| Component | File | Purpose |
|-----------|------|---------|
| TUI ACP Agent | `tui/acp/agent.py` | TUI-side ACP protocol handler, runs Agent subprocess |
| CDH ACP Adapter | `cdha/agent/cdh_agent_acp.py` | Agent-side adapter, translates JSON-RPC ↔ AgentEngine |
| ACP Protocol | `tui/acp/protocol.py` | ACP type definitions (PlanEntry, SessionUpdate, etc.) |
| ACP Messages | `tui/acp/messages.py` | ACP message classes for Textual message bus |
| Stream Events | `cdha/models/messages.py` | StreamEvent types: TEXT_DELTA, TOOL_CALL_START, PLAN, etc. |

## Plan Flow (TUI ↔ Agent)

### TUI-Side: Receiving Plan Updates

**1. `tui/acp/agent.py`** — handles incoming `session/update` notifications:
```python
@jsonrpc.expose("session/update")
def rpc_session_update(self, sessionId, update, _meta=None):
    match update:
        case {"sessionUpdate": "plan", "entries": entries}:
            self.post_message(messages.Plan(entries))
```

**2. `tui/acp/messages.py`** — defines the ACP message type:
```python
@dataclass
class Plan(AgentMessage):
    entries: list[protocol.PlanEntry]
```

**3. `tui/screens/main.py`** — displays in sidebar:
```python
@on(acp_messages.Plan)
async def on_acp_plan(self, message: acp_messages.Plan):
    entries = [Plan.Entry(Content(e["content"]), e.get("priority", "medium"), e.get("status", "pending"))
               for e in message.entries]
    self.query_one("SideBar Plan", Plan).entries = entries
```

### Agent-Side: Emitting Plan Updates

**1. `cdha/models/messages.py`** — StreamEvent types:
```python
class StreamEventType(str, Enum):
    TEXT_DELTA = "text_delta"
    TOOL_CALL_START = "tool_call_start"
    TOOL_RESULT = "tool_result"
    PLAN = "plan"  # Added for plan support

@dataclass
class StreamEvent:
    plan_entries: list[dict] = field(default_factory=list)

    @classmethod
    def plan(cls, entries: list[dict]) -> "StreamEvent":
        return cls(type=StreamEventType.PLAN, plan_entries=entries)
```

**2. `cdha/agent/cdh_agent_acp.py`** — converts StreamEvent to ACP notification:
```python
async for event in self.agent.chat_stream(user_message):
    elif event.type == StreamEventType.PLAN:
        self.send_session_update({
            "sessionUpdate": "plan",
            "entries": event.plan_entries,
        })
```

**3. `cdha/agent/engine.py`** — emits plan after task tools:
```python
def _emit_plan_update(self) -> list[StreamEvent]:
    entries = []
    for task in self._task_manager.list_tasks():
        entries.append({"content": task["subject"], "status": task["status"], "priority": "medium"})
    for todo in self._task_manager.list_todos():
        entries.append({"content": todo["text"], "status": "pending", "priority": "low"})
    return [StreamEvent.plan(entries)]

# In tool execution loop, after TaskCreate/TaskUpdate/etc:
if tu["name"] in ("TaskCreate", "TaskUpdate", "TaskStop", "TodoCreate", "TodoComplete"):
    for event in self._emit_plan_update():
        yield event
```

### ACP Protocol Format (tui/acp/protocol.py)

```python
class PlanEntry(SchemaDict, total=False):
    content: Required[str]
    priority: Literal["high", "medium", "low"]
    status: Literal["pending", "in_progress", "completed"]

class Plan(SchemaDict, total=False):
    entries: Required[list[PlanEntry]]
    sessionUpdate: Required[Literal["plan"]]
```

## Session Management

- `session/new` — creates new session, returns `sessionId`
- `session/load` — restores existing session by ID
- `session/prompt` — sends user input, streams responses
- `session/cancel` — interrupts running agent
- `session/set_mode` — switches mode (agent/plan/solo)

## Adding New StreamEvent Types

1. Add to `cdha/models/messages.py`:
   - Add enum value to `StreamEventType`
   - Add fields to `StreamEvent` dataclass
   - Add factory classmethod

2. Add handling in `cdha/agent/cdh_agent_acp.py:session_prompt`:
   - Add `elif event.type == StreamEventType.NEW_TYPE:` branch
   - Send `send_session_update({"sessionUpdate": "new_update", ...})`

3. Add ACP message type in `tui/acp/messages.py` if needed

4. Add protocol definition in `tui/acp/protocol.py`

5. Add handler in `tui/acp/agent.py:rpc_session_update()` matching on `sessionUpdate` value

## Cloud-Spec-Skill Auto-Load

All agents (cdh + Claude Code via ACP) automatically load `cloud-spec-skill` on every prompt via `tui/acp/prompt.build()` — single injection point, universal for both cdh agent and Claude Code ACP agents.

**Do NOT add cloud-spec-skill in `cdha/agent/engine.py:_load_skills()`** — that method is only for user-defined skills loaded via `self._skill_loader.get_enabled()`. Keep it focused on user skills.

### Startup and Agent-Launch Verification

To ensure `~/.cdh/skills/cloud-spec-skill/` is populated for agents that query skills via `SkillLoader`, `ensure_cloud_spec_skill_installed()` is called at two points:

**1. TUI startup — `tui/app.py: on_mount()`:**
```python
async def on_mount(self) -> None:
    from tui.acp.prompt import ensure_cloud_spec_skill_installed
    if err := ensure_cloud_spec_skill_installed():
        self.notify(f"Failed to install cloud-spec-skill: {err}", ...)
    # ...
```

**2. Before agent launch — `tui/app.py: on_launch_agent()` (covers all store screen launches):**
```python
@on(messages.LaunchAgent)
def on_launch_agent(self, message: messages.LaunchAgent) -> None:
    from tui.acp.prompt import ensure_cloud_spec_skill_installed
    if err := ensure_cloud_spec_skill_installed():
        self.notify(f"Failed to install cloud-spec-skill: {err}", ...)
    self.launch_agent(...)
```

**Logic (`tui/acp/prompt.py: ensure_cloud_spec_skill_installed()`):**
1. If `~/.cdh/skills/cloud-spec-skill/` already exists → no-op, return `None`
2. If repo-level `cloud-spec-skill/SKILL.md` does NOT exist → no-op, return `None` (no source to copy)
3. Otherwise `shutil.copytree` the whole `cloud-spec-skill/` dir into `~/.cdh/skills/`

This ensures CloudSpec development standards are always applied regardless of agent mode.