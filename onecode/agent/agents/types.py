from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentMode(Enum):
    PRIMARY = "primary"
    SUBAGENT = "subagent"
    ALL = "all"


class AgentPermission(Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass
class ToolConfig:
    name: str
    permission: AgentPermission = AgentPermission.ALLOW
    patterns: list[str] = field(default_factory=list)


@dataclass
class AgentConfig:
    name: str
    description: str = ""
    mode: AgentMode = AgentMode.PRIMARY
    temperature: float = 0.3
    top_p: Optional[float] = None
    model: Optional[str] = None
    max_turns: int = 0
    steps: int = 0
    hidden: bool = False
    color: str = ""
    permission_edit: AgentPermission = AgentPermission.ALLOW
    permission_bash: AgentPermission = AgentPermission.ALLOW
    permission_read: AgentPermission = AgentPermission.ALLOW
    permission_webfetch: AgentPermission = AgentPermission.ALLOW
    permission_websearch: AgentPermission = AgentPermission.DENY
    permission_task: AgentPermission = AgentPermission.ALLOW
    permission_doom_loop: AgentPermission = AgentPermission.ASK
    permission_skill: AgentPermission = AgentPermission.ALLOW
    permission_lsp: AgentPermission = AgentPermission.ALLOW
    permission_question: AgentPermission = AgentPermission.ALLOW
    permission_external_directory: AgentPermission = AgentPermission.DENY
    permission_glob: AgentPermission = AgentPermission.ALLOW
    permission_grep: AgentPermission = AgentPermission.ALLOW
    permission_list: AgentPermission = AgentPermission.ALLOW
    permission_todowrite: AgentPermission = AgentPermission.ALLOW
    tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    prompt_file: str = ""
    bash_permissions: dict[str, str] = field(default_factory=dict)

    def get_tools_config(self) -> dict[str, AgentPermission]:
        return {
            "edit": self.permission_edit,
            "bash": self.permission_bash,
            "read": self.permission_read,
            "webfetch": self.permission_webfetch,
            "websearch": self.permission_websearch,
            "task": self.permission_task,
            "lsp": self.permission_lsp,
            "skill": self.permission_skill,
            "question": self.permission_question,
            "glob": self.permission_glob,
            "grep": self.permission_grep,
            "list": self.permission_list,
            "todowrite": self.permission_todowrite,
            "external_directory": self.permission_external_directory,
            "doom_loop": self.permission_doom_loop,
        }

    def should_ask_for_edit(self) -> bool:
        return self.permission_edit == AgentPermission.ASK

    def should_ask_for_bash(self) -> bool:
        return self.permission_bash == AgentPermission.ASK

    def tool_allowed(self, tool_name: str) -> bool:
        if self.tools:
            return tool_name in self.tools
        if self.disallowed_tools:
            return tool_name not in self.disallowed_tools
        return True

    def get_bash_permission(self, command: str) -> AgentPermission:
        for pattern, action in self.bash_permissions.items():
            if fnmatch.fnmatch(command, pattern) or fnmatch.fnmatch(command.split()[0] if command.split() else "", pattern):
                if action == "allow":
                    return AgentPermission.ALLOW
                elif action == "ask":
                    return AgentPermission.ASK
                elif action == "deny":
                    return AgentPermission.DENY
        return self.permission_bash

    def get_effective_max_turns(self) -> int:
        if self.steps > 0:
            return min(self.steps, self.max_turns) if self.max_turns > 0 else self.steps
        return self.max_turns

    def is_hidden(self) -> bool:
        return self.hidden


class BuildAgent(AgentConfig):
    def __init__(self):
        super().__init__(
            name="build",
            description=(
                "Full development agent with all tools enabled. Edits and shell "
                "commands require user approval. Uses CoT reasoning + ReAct loop "
                "with routing by complexity: simple work → TodoCreate, complex "
                "work → Spawn subagent."
            ),
            mode=AgentMode.PRIMARY,
            permission_edit=AgentPermission.ASK,
            permission_bash=AgentPermission.ASK,
            permission_read=AgentPermission.ALLOW,
            permission_webfetch=AgentPermission.ALLOW,
            permission_websearch=AgentPermission.ALLOW,
            max_turns=10,
            steps=0,
            tools=[],
        )


class PlanAgent(AgentConfig):
    def __init__(self):
        super().__init__(
            name="plan",
            description=(
                "Plan mode: CoT + ReAct (思考→行动→观察) agent with hard plan "
                "gate. Creates a todo plan first via TodoCreate, presents for "
                "user review, then routes execution by complexity: simple todos "
                "run directly, complex todos are delegated to Spawn subagents. "
                "Human-in-the-loop."
            ),
            mode=AgentMode.PRIMARY,
            permission_edit=AgentPermission.ASK,
            permission_bash=AgentPermission.ASK,
            permission_read=AgentPermission.ALLOW,
            permission_webfetch=AgentPermission.ALLOW,
            permission_websearch=AgentPermission.ALLOW,
            max_turns=20,
            temperature=0.2,
            tools=[],
        )


class SoloAgent(AgentConfig):
    def __init__(self):
        super().__init__(
            name="solo",
            description=(
                "Independent agent that plans first, then acts with full tool "
                "access. Uses CoT reasoning + ReAct loop with routing by "
                "complexity: simple work → TodoCreate, complex work → Spawn "
                "subagent. Shell commands require user approval."
            ),
            mode=AgentMode.PRIMARY,
            permission_edit=AgentPermission.ALLOW,
            permission_bash=AgentPermission.ASK,
            permission_read=AgentPermission.ALLOW,
            permission_webfetch=AgentPermission.ALLOW,
            permission_websearch=AgentPermission.ALLOW,
            max_turns=10,
            temperature=0.3,
            tools=[],
        )


class GeneralAgent(AgentConfig):
    def __init__(self):
        super().__init__(
            name="general",
            description=(
                "General-purpose subagent for complex multi-step tasks. Executes "
                "focused work delegated by parent agent via Spawn tool. Uses "
                "CoT + ReAct internally."
            ),
            mode=AgentMode.SUBAGENT,
            permission_edit=AgentPermission.ALLOW,
            permission_bash=AgentPermission.ALLOW,
            permission_read=AgentPermission.ALLOW,
            permission_task=AgentPermission.DENY,
            permission_question=AgentPermission.ALLOW,
            disallowed_tools=["Spawn", "Agent", "AskUser", "TodoCreate", "TodoGet", "TodoList", "TodoUpdate", "TodoOutput", "TodoStop", "TodoClear"],
        )


class ExploreAgent(AgentConfig):
    def __init__(self):
        super().__init__(
            name="explore",
            description="Fast read-only agent for exploring codebases",
            mode=AgentMode.SUBAGENT,
            permission_edit=AgentPermission.DENY,
            permission_bash=AgentPermission.DENY,
            permission_read=AgentPermission.ALLOW,
            permission_task=AgentPermission.DENY,
            permission_question=AgentPermission.DENY,
            disallowed_tools=["Spawn", "Agent", "AskUser", "TodoCreate", "TodoGet", "TodoList", "TodoUpdate", "TodoOutput", "TodoStop", "TodoClear"],
            hidden=True,
        )


class ScoutAgent(AgentConfig):
    def __init__(self):
        super().__init__(
            name="scout",
            description="Read-only agent for external docs and dependency research",
            mode=AgentMode.SUBAGENT,
            permission_edit=AgentPermission.DENY,
            permission_bash=AgentPermission.DENY,
            permission_read=AgentPermission.ALLOW,
            permission_webfetch=AgentPermission.ALLOW,
            permission_websearch=AgentPermission.ALLOW,
            permission_task=AgentPermission.DENY,
            permission_question=AgentPermission.DENY,
            disallowed_tools=["Spawn", "Agent", "AskUser", "TodoCreate", "TodoGet", "TodoList", "TodoUpdate", "TodoOutput", "TodoStop", "TodoClear"],
            hidden=True,
        )


class CompactionAgent(AgentConfig):
    def __init__(self):
        super().__init__(
            name="compaction",
            description="System agent that compacts long context into a smaller summary",
            mode=AgentMode.PRIMARY,
            permission_edit=AgentPermission.DENY,
            permission_bash=AgentPermission.DENY,
            permission_read=AgentPermission.ALLOW,
            permission_webfetch=AgentPermission.DENY,
            permission_websearch=AgentPermission.DENY,
            permission_task=AgentPermission.DENY,
            permission_skill=AgentPermission.DENY,
            hidden=True,
            temperature=0.1,
            tools=["read"],
        )


class TitleAgent(AgentConfig):
    def __init__(self):
        super().__init__(
            name="title",
            description="System agent that generates short session titles",
            mode=AgentMode.PRIMARY,
            permission_edit=AgentPermission.DENY,
            permission_bash=AgentPermission.DENY,
            permission_read=AgentPermission.ALLOW,
            permission_webfetch=AgentPermission.DENY,
            permission_websearch=AgentPermission.DENY,
            permission_task=AgentPermission.DENY,
            permission_skill=AgentPermission.DENY,
            hidden=True,
            temperature=0.1,
            max_turns=1,
            tools=["read"],
        )


class SummaryAgent(AgentConfig):
    def __init__(self):
        super().__init__(
            name="summary",
            description="System agent that creates session summaries",
            mode=AgentMode.PRIMARY,
            permission_edit=AgentPermission.DENY,
            permission_bash=AgentPermission.DENY,
            permission_read=AgentPermission.ALLOW,
            permission_webfetch=AgentPermission.DENY,
            permission_websearch=AgentPermission.DENY,
            permission_task=AgentPermission.DENY,
            permission_skill=AgentPermission.DENY,
            hidden=True,
            temperature=0.1,
            max_turns=2,
            tools=["read"],
        )


BUILT_IN_AGENTS = {
    "build": BuildAgent,
    "plan": PlanAgent,
    "solo": SoloAgent,
    "general": GeneralAgent,
    "explore": ExploreAgent,
    "scout": ScoutAgent,
    "compaction": CompactionAgent,
    "title": TitleAgent,
    "summary": SummaryAgent,
}


def create_agent(agent_type: str) -> AgentConfig:
    agent_cls = BUILT_IN_AGENTS.get(agent_type)
    if agent_cls:
        return agent_cls()
    return BuildAgent()


def get_agent_by_name(name: str) -> Optional[AgentConfig]:
    agent_cls = BUILT_IN_AGENTS.get(name)
    if agent_cls:
        return agent_cls()
    return None


SUBAGENT_CONSTRAINTS = """
### Constraints (subagent)
You are running as a subagent spawned by a parent agent via the Spawn tool.
- You CANNOT spawn subagents (Spawn tool is disabled).
- You CANNOT execute batched tool calls (Agent tool is disabled).
- You CANNOT manage todos (all Todo* tools are disabled). The parent owns the shared plan.
- You CANNOT interact with the user (AskUser is disabled).
- You are a leaf node in the agent hierarchy. Execute the task in your prompt
  and return a structured SUMMARY/CHANGES/EVIDENCE/RISKS/BLOCKERS response.
- Do not narrate "I will now..." in visible text; all reasoning in <thinking>.
"""


def get_system_prompt(agent_type: str) -> str:
    agent = create_agent(agent_type)
    lines = [
        f"You are {agent.name}.",
        agent.description,
    ]

    if agent.should_ask_for_edit():
        lines.append("- File edits require user approval")
    if agent.should_ask_for_bash():
        lines.append("- Shell commands require user approval")

    if agent.mode == AgentMode.SUBAGENT:
        lines.append(SUBAGENT_CONSTRAINTS)

    return "\n".join(lines)


TOOL_DESCRIPTIONS = """
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
"""

def filter_tool_descriptions(
    allowlist: list[str] | None = None,
    denylist: list[str] | None = None,
) -> str:
    """Return TOOL_DESCRIPTIONS filtered to only show the allowed tools.

    When *allowlist* is non-empty, only those tool names are shown.
    When *denylist* is non-empty, those tool names are hidden (their
    description lines are removed, but category headers are kept).
    If both are empty, the full tool list is returned.
    """
    if not allowlist and not denylist:
        return TOOL_DESCRIPTIONS

    _TOOL_LINE_RE = re.compile(r'^- \*\*([^*]+)\*\*:')

    lines = TOOL_DESCRIPTIONS.split("\n")
    result_lines: list[str] = []
    skip_this_line = False

    for line in lines:
        m = _TOOL_LINE_RE.match(line.lstrip())
        if m:
            tool_name = m.group(1).strip()
            if allowlist:
                skip_this_line = tool_name not in allowlist
            elif denylist:
                skip_this_line = tool_name in denylist
            else:
                skip_this_line = False
        else:
            skip_this_line = False

        if not skip_this_line:
            result_lines.append(line)

    return "\n".join(result_lines)


REACT_WORKFLOW = """
## Workflow: Thought → Action → Observation

Each cycle: `<thinking>` (plan) → `TodoCreate` → tool(s) → `TodoUpdate`.

### Routing
- **Todo = plan, Spawn = execution delegation.** Every task is `TodoCreate`.
- **Simple** (1 tool, 1 file) → execute directly → `TodoUpdate(status="completed")`
- **Complex** (multi-file/multi-step/research) → `Spawn(agent_type, prompt)` → `TodoUpdate(status="completed")`
- Spawn does NOT replace a Todo — it executes one.

### Thought Phase
Reason in `<thinking>`:
1. Current state? Goal? Route: simple (direct) or complex (Spawn)?
2. Todo exists? No → `TodoCreate`. Yes → advance it.
3. Execute → `TodoUpdate(status="completed")`.

### Observation
Tool result = observation. Success → update status. Error → diagnose & retry/ask user.
"""

PLAN_GATE_HARD = """
### plan mode: hard gate
Execution tools (Write/Edit/Insert/ApplyPatch/Bash) are BLOCKED until a todo plan exists.
Create ALL todos upfront with `TodoCreate`, present for user review, then execute.
"""

PLAN_GATE_SOFT = """
### build/solo mode: soft gate
Execution is allowed but planning is encouraged. Create todos first via `TodoCreate`.
"""

COMPACTION_INSTRUCTIONS = """
## Context Compaction

You are a compaction agent. Your job is to summarize the conversation history into a concise format that preserves key information while minimizing token usage.

Output a summary with these sections:
- **Summary**: Brief overview of what has been discussed/accomplished
- **Key Decisions**: Important choices made and their rationale
- **Remaining Tasks**: What still needs to be done
- **Context Needed**: Information required to continue the work

Keep each section concise. Use bullet points where possible.
"""

TITLE_INSTRUCTIONS = """
Generate a short, descriptive title (max 5 words) for this conversation. 
The title should capture the main topic or task being worked on.
Only output the title, nothing else.
"""

SUMMARY_INSTRUCTIONS = """
Create a summary of this conversation session. Include:
- What was the user trying to accomplish
- What was done
- What was the outcome
- Any important notes for future sessions

Keep it concise but informative.
"""
