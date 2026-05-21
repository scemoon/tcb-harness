# Message Handling Improvement Plan

## Current Problems

| Area | Issue |
|------|-------|
| **Message Model** | No separation between system/display/tool messages. System prompts (skill content) leak into display. |
| **Session Persistence** | Persists ALL messages including system + tool internals → restores and displays them on startup |
| **Think/Reasoning** | Basic Panel with "⏳ Thinking". No collapsible UI, no animation, no toggle |
| **Tool Calls/Results** | Rendered as Rich Panels. No status progression (submitted→running→done), no expand/collapse |
| **Sub-agent** | Just another tool result string. No visual distinction, no progress, no collapsible tree |
| **Stream Parser** | Regex-based XML parsing. Fragile with edge cases, no structured event model |

## Proposed Architecture (inspired by opencode)

```
┌─────────────────────────────────────────────────────┐
│                   Message Model                      │
├──────────────┬──────────────┬───────────────────────┤
│  Context      │  Session     │  Display              │
│  (Agent)      │  (Persist)   │  (ChatPanel)          │
├──────────────┼──────────────┼───────────────────────┤
│ system_config│ ✗ NOT saved  │ ✗ NOT rendered        │
│ user         │ ✓ saved      │ ✓ rendered            │
│ assistant    │ ✓ saved      │ ✓ rendered            │
│ tool_call    │ metadata     │ collapsible inline     │
│ tool_result  │ metadata     │ collapsible inline     │
│ reasoning    │ ✗ NOT saved  │ toggleable section    │
│ subagent_*   │ metadata     │ nested collapsible    │
└──────────────┴──────────────┴───────────────────────┘
```

## Implementation Phases

### Phase 1 — Foundation: Message Model Cleanup

**`cdh/agent/context.py`**:
- Add `MessageType` enum: `SYSTEM`, `USER`, `ASSISTANT`, `TOOL_CALL`, `TOOL_RESULT`, `REASONING`, `SUBAGENT`
- `to_session_format()` filters out `SYSTEM` and `REASONING`
- Add `display_role` and `metadata` fields to `Message`

**`cdh/agent/session.py`**:
- Add `to_display_messages()` method that:
  - Filters out system/reasoning messages
  - Collapses tool call+result into single expandable entry

**`cdh/tui/app.py`**:
- `_display_session_messages()` → use `session.to_display_messages()` instead of raw `messages`

### Phase 2 — Think/Reasoning Display

**`cdh/tui/widgets/chat.py`** — Reasoning rendering:
- Replace current `"⏳ Thinking"` Panel with toggleable `▶ Reasoning` / `▼ Reasoning` collapsible section
- Streaming: show animated indicator (e.g., `⠋ Thinking...`)
- After completion: collapsed by default with token count
- Use Rich `Panel` with click handler for toggle

### Phase 3 — Tool Call/Result Display

**`cdh/tui/widgets/chat.py`** — Tool rendering:
- Tool call: compact inline `🔧 tool_name(...)` with expand/collapse for params
- Tool result: collapsed by default, expand on click
- Show status progression: `⏳ → ✅/❌`
- Remove duplicate Panel nesting

### Phase 4 — Sub-agent Display

**`cdh/tui/widgets/chat.py`** — Sub-agent UI:
- Show `🤖 Sub-agent: <type>` header with distinct border color
- Display sub-agent conversation as nested collapsible
- Show progress indicator during execution

### Phase 5 — Streaming & Parser

**`cdh/tui/widgets/chat.py`** — `StreamParser`:
- Replace XML regex with proper state machine (tokenizer)
- Add `tool_call_id` tracking for pairing results with calls
- Emit typed events: `TextChunk`, `ThinkingChunk`, `ToolCallChunk`, `ToolResultChunk`

## Files to Modify

| File | Key Changes |
|------|-------------|
| `cdh/agent/context.py` | Add `MessageType` enum, filter system/reasoning from persistence |
| `cdh/agent/session.py` | Add `to_display_messages()` filter method |
| `cdh/agent/engine.py` | Tag messages with proper types, add sub-agent message tracking |
| `cdh/tui/app.py` | Use filtered display messages, update `_display_session_messages()` |
| `cdh/tui/widgets/chat.py` | Rewrite rendering: collapsible think, tool, sub-agent; improve StreamParser |
| `cdh/tui/widgets/right_panel.py` | Already fixed (tasks/todos/plan at bottom) |
