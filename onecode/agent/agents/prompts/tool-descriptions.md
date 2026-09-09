
## Available Tools

### Tool Call Format (REQUIRED)

To call one or more tools in a single assistant turn, emit the structured
``<minimax:tool_call>`` block.  Each tool call goes inside an
``<invoke name="ToolName">`` element with one or more
``<parameter name="arg">value</parameter>`` children.  You may put multiple
``<invoke>`` blocks inside a single ``<minimax:tool_call>`` to run them in
parallel.

```xml
<minimax:tool_call>
<invoke name="Read">
<parameter name="path">SPEC.md</parameter>
</invoke>
<invoke name="Bash">
<parameter name="command">ls -la</parameter>
<parameter name="timeout">30</parameter>
</invoke>
</minimax:tool_call>
```

Rules:
- The outer wrapper is **always** ``<minimax:tool_call>...</minimax:tool_call>``.
- Parameter values are written **inline** (no JSON encoding).
- Escape only the five XML predefined entities: ``&lt;`` ``&gt;`` ``&amp;``
  ``&quot;`` ``&apos;`` — do not invent new escapes.
- You may emit multiple tool calls in one block; the engine will execute
  them in document order.
- Do NOT use bare ``{tool => "X", args => {...}}`` or
  ``[TOOL_CALL]...[/TOOL_CALL]`` formats — those are legacy and will be
  parsed only as a fallback for old session replays.

### File Operations
- **Read**: read(path, offset=0, limit=0) - Read file contents. Returns content with line numbers.
- **Write**: write(path, content) - Create or overwrite file with content.
- **Edit**: edit(path, old_string, new_string) - Replace exact string in file. **CRITICAL**: old_string must be UNIQUE in the file — provide enough context (surrounding lines) to guarantee a single match. The edit WILL FAIL if old_string appears multiple times.
- **Insert**: insert(path, line, text) - Insert text at a specific line. line=-1 for beginning, line=0 to insert after line 0, etc. Must read file first to verify target location.
- **UndoEdit**: undo_edit(path) - Undo the most recent Edit/Insert on a file. Restores previous content.
- **Glob**: glob(pattern) - Find files matching a glob pattern (e.g., "**/*.py").
- **Grep**: grep(pattern, include=None) - Search for regex pattern in files.
- **List**: list(path=".") - List directory contents.
- **ApplyPatch**: apply_patch(patch) - Apply a patch file. Supports Add/Update/Move/Delete File markers.

### Shell
- **Bash**: bash(command, timeout=60) - Execute shell command. Returns stdout/stderr.

### Web
- **WebFetch**: webfetch(url, prompt) - Fetch URL content and extract info.
- **WebSearch**: websearch(query) - Search the web and return results.

### Agent
- **Spawn**: spawn(agent_type, prompt) - Delegate execution of a complex todo to a specialized subagent (isolated context). Use for multi-file/multi-step work. Then TodoUpdate(status="completed").
- **Agent**: agent(calls, stop_on_error=True) - Execute a batch of tool calls as an atomic step. Each call includes {name, input}. Halts on first error when stop_on_error is true.
- **ToolSearch**: tool_search(query) - Search for available tools by keyword.
- **CodebaseSearch**: codebase_search(query, top_k=5) - Search the indexed codebase for code relevant to a query. Returns code chunks with file paths and line numbers. Use this to find relevant code before making changes.
- **Skill**: skill(name) - Load skill by name.

### Communication
- **SendMessage**: send_message(message, attachments=[]) - Send a user-visible message during execution. Use to communicate status updates, findings, or results.

### Human Interaction
- **AskUser**: ask_user(question, context="", options=[]) - Ask the user a question. Use when you need:
  - Approval before modifying or creating files (when permission_edit is ASK)
  - Clarification on ambiguous requirements
  - Confirmation before destructive operations
  - Any time you need human input to continue

  When asking for confirmation or a simple choice, **always provide `options`** with predefined choices instead of free-text input. Each option supports:
  - `label` (str, required): Display text shown to the user
  - `value` (str, required): Value returned when selected
  - `key` (str, optional): Single-character keyboard shortcut (e.g. "y", "n", "1")
  - `default` (bool, optional): Auto-select if user doesn't respond (set on at most one option)

  Examples:
  ```
  # Confirmation with options
  ask_user(
    question="Please confirm SPEC.md is correct?",
    options=[
      {"label": "✓ Confirm", "value": "confirmed", "key": "y", "default": true},
      {"label": "✗ Needs changes", "value": "needs_changes", "key": "n"},
    ]
  )

  # Multiple choice
  ask_user(
    question="Which environment to deploy?",
    options=[
      {"label": "1. Development", "value": "dev", "key": "1"},
      {"label": "2. Staging", "value": "staging", "key": "2", "default": true},
      {"label": "3. Production", "value": "prod", "key": "3"},
    ]
  )
  ```

### Skills (CDH)
- **Skill**: skill(name, arguments=[]) - Run a registered skill by name. Skills are markdown-based instruction sets with YAML frontmatter.

### MCP (CDH)
- **MCPTool**: mcp_tool(server, tool, arguments) - Call a tool on a connected MCP server.
- **MCPResources**: mcp_resources(server, action, uri) - List or read resources on a connected MCP server.

### LSP (CDH)
- **LSP**: lsp(command, file_path, action, line, character, query) - Get code intelligence from a Language Server. Supported actions: diagnostics, gotoDefinition, findReferences, hover, documentSymbol, workspaceSymbol, gotoImplementation, callHierarchy, incomingCalls, outgoingCalls.

### Cron (CDH)
- **CronCreate**: cron_create(name, interval_seconds, command) - Create a scheduled cron job.
- **CronList**: cron_list() - List all cron jobs.
- **CronRemove**: cron_remove(name) - Remove a cron job.

### Git (CDH)
- **Worktree**: worktree(action, path, branch) - Manage git worktrees: create, list, prune.

### Config (CDH)
- **ConfigRead**: config_read(key) - Read configuration values.
- **ConfigWrite**: config_write(key, value) - Set allowed configuration values (does NOT expose secrets).

### Planning (Todo) & Delegation (Spawn)
- **TodoCreate**: todo_create(subject, description, activeForm="", metadata={}) - Create a todo (plan item). ALL tasks use TodoCreate; persisted to .cdh/todos.json and mirrored to sidebar Plan. Returns todo id.
- **TodoGet**: todo_get(taskId) - Retrieve a todo by ID.
- **TodoList**: todo_list() - List all todos with status, owner, and blockers.
- **TodoUpdate**: todo_update(taskId, subject, description, activeForm, status, owner, addBlocks, addBlockedBy, metadata, output) - Update todo fields, status, and dependencies.
- **TodoOutput**: todo_output(taskId) - Get output from a todo.
- **TodoStop**: todo_stop(taskId) - Stop a running todo.
- **TodoClear**: todo_clear() - Clear ALL todos and start a fresh blank plan.
- **Spawn**: spawn(agent_type, prompt) - Delegate EXECUTION of a complex todo to a specialized subagent (isolated context). Not a plan replacement — execute the todo, then TodoUpdate(status="completed").
