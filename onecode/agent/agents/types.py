from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
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
    permission_todoread: AgentPermission = AgentPermission.ALLOW
    tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    prompt_file: str = ""
    bash_permissions: dict[str, str] = field(default_factory=dict)
    permissions_locked: bool = False

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
            "todoread": self.permission_todoread,
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
                "Full development agent for direct requests: brief inline "
                "planning for complex work, then execution. Edits and shell "
                "commands require user approval. Verifies each change before "
                "reporting done."
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
                "Plan mode: read-only planning agent (research → plan → "
                "approval → handoff). Researches the codebase with read-only "
                "tools, clarifies requirements via AskUser, outputs a structured "
                "plan (saved to .cdh/plans/), builds the task list via "
                "TodoCreate, and submits the plan for user approval. NEVER "
                "edits files or runs shell commands. On approval the system "
                "automatically hands off execution to the execution agent."
            ),
            mode=AgentMode.PRIMARY,
            permission_edit=AgentPermission.DENY,
            permission_bash=AgentPermission.DENY,
            permission_read=AgentPermission.ALLOW,
            permission_webfetch=AgentPermission.ALLOW,
            permission_websearch=AgentPermission.ALLOW,
            permission_todowrite=AgentPermission.ALLOW,
            max_turns=20,
            temperature=0.2,
            disallowed_tools=["Write", "Edit", "Insert", "ApplyPatch", "UndoEdit"],
            permissions_locked=True,
        )


class SoloAgent(AgentConfig):
    def __init__(self):
        super().__init__(
            name="solo",
            description=(
                "Execution agent: executes approved plans (handoff from plan "
                "mode) or direct requests with brief inline planning. "
                "Todo-driven, verifies each change before marking it "
                "complete. File edits and shell commands require user "
                "approval."
            ),
            mode=AgentMode.PRIMARY,
            permission_edit=AgentPermission.ASK,
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


_AGENT_CACHE: dict[str, AgentConfig] = {}


def create_agent(agent_type: str) -> AgentConfig:
    if agent_type in _AGENT_CACHE:
        return _AGENT_CACHE[agent_type]
    agent_cls = BUILT_IN_AGENTS.get(agent_type)
    if agent_cls:
        agent = agent_cls()
        _AGENT_CACHE[agent_type] = agent
        return agent
    return BuildAgent()


def get_agent_by_name(name: str) -> Optional[AgentConfig]:
    agent_cls = BUILT_IN_AGENTS.get(name)
    if agent_cls:
        return agent_cls()
    return None


_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(name: str, fallback: str) -> str:
    path = _PROMPTS_DIR / f"{name}.md"
    try:
        return path.read_text("utf-8")
    except Exception:
        return fallback


PLAN_AGENT_INSTRUCTIONS = _load_prompt("plan-agent", """
# Plan Agent (Plan Mode)

You are the read-only planning agent. Your job is to research, clarify, and
produce a reviewable implementation plan. You NEVER modify files and NEVER
run shell commands — execution happens only after the user approves your plan
and the system hands off to the execution agent.

## Workflow (one pass — do not repeat stages)

1. **Research** — use read-only tools (Read/Glob/Grep/List/WebFetch/WebSearch/
   CodebaseSearch) to understand the current state. If requirements are
   ambiguous, use AskUser to clarify first.
2. **Plan** — output ONE structured plan (see "Plan format" below). The plan
   is saved to `.cdh/plans/` automatically when you submit it.
3. **Task list** — decompose the plan into actionable steps with TodoCreate
   (one todo per step, acceptance criteria in the description). Create the
   whole list once; do not recreate or duplicate todos.
4. **Approval** — call AskUser with `plan_submit: true` to submit the plan for
   user review. Options: approve (starts execution) / needs changes.
5. **Handoff** — on approval the system switches to the execution agent. You
   do not participate in execution.

## Plan format (must include all sections)

- **Scope**: what will be done / what will NOT be done
- **Files**: each file to change and what changes
- **Steps & order**: dependency order, safe intermediate states
- **Assumptions**: state them explicitly — the user can correct them for free
- **Risks & testing**: how each change will be verified

## Hard constraints

- Edit/Write/Insert/ApplyPatch/Bash are removed from your toolset — never try them.
- Work through the stages in order, one stage per round. Do NOT create the
  task list before the plan is drafted, and do not create it repeatedly.
- Do not execute anything before the plan is approved.

## Response style

- Every round starts with Chain of Thought reasoning inside `<thinking>`:
  review the last round's tool results, assess progress against the current
  stage, decide the next action.
- When you need user feedback, input, or approval — ALWAYS use the AskUser
  tool to pause and wait. Never output a question in visible text and
  continue executing.
""")


SOLO_AGENT_INSTRUCTIONS = _load_prompt("solo-agent", """
# Solo Agent (Execution)

You are the execution agent. If an approved plan is present (the
`<!-- APPROVED_PLAN -->` system section), execute it strictly. Otherwise,
plan briefly inline, then execute. File edits and shell commands require
user approval.

## Workflow

**Mode A — executing an approved plan (APPROVED_PLAN present):**
1. Read the approved plan and its task list (todos). Do NOT re-plan and do
   NOT change scope.
2. Work through the todos in order: mark `in_progress` → execute → verify →
   mark `completed` via TodoUpdate.
3. If a step fails: stop, fix within scope, or AskUser before deviating.

**Mode B — direct request (no approved plan):**
1. Research with read-only tools if the codebase is unfamiliar.
2. Output a brief inline plan as Markdown: what / which files / steps /
   how to verify.
3. Execute. For complex multi-step work, delegate via `Spawn` to keep the
   main context clean.

## Execution discipline

- **Todo-driven**: never end the turn while pending or in-progress todos
  remain. Mark each todo `completed` immediately after it is verified.
- **Scope discipline**: only touch files and steps in the approved plan (or
  the stated request). Anything beyond scope → AskUser first.
- **Approval**: file edits and shell commands require user approval — pause
  and wait; never assume approval.
- **Verification before done**: never mark a task complete without proof —
  run the relevant test / lint / build and show the result. "Make it work"
  is not done; "tests pass" is done.
- **Failure handling**: if something goes sideways, STOP. Do not patch
  around a broken approach — re-plan from the point of failure or ask.

## Done condition

All todos completed AND verification passed → output a visible final
summary: what changed, verification evidence, remaining risks.

## Response style

- Every round starts with Chain of Thought reasoning inside `<thinking>`:
  review the last round's tool results, assess progress against todos,
  decide the next action.
- **Intermediate rounds**: visible text is for progress updates only. Do
  NOT announce "done" or "complete" unless ALL work is actually finished.
- When you need user feedback, input, or approval — ALWAYS use the AskUser
  tool to pause and wait. Never output a question in visible text and
  continue executing.
""")


BUILD_AGENT_INSTRUCTIONS = _load_prompt("build-agent", """
# Build Agent (Development)

You are the full-development agent for direct user requests. Plan briefly
for complex work, then execute. File edits and shell commands require user
approval.

## Workflow

**Mode A — simple / single-step tasks:**
Execute directly with minimal preamble.

**Mode B — complex multi-step tasks:**
1. Research with read-only tools if the codebase is unfamiliar.
2. Output a brief inline plan as Markdown: what / which files / steps /
   how to verify.
3. Execute. For complex multi-step work, delegate via `Spawn` to keep the
   main context clean.

## Execution discipline

- **Todo-driven**: for multi-step work, break it into todos via TodoCreate;
  mark `in_progress` → execute → verify → `completed` via TodoUpdate. Never
  end the turn while pending or in-progress todos remain.
- **Approval**: file edits and shell commands require user approval — pause
  and wait; never assume approval.
- **Verification before done**: never mark a task complete without proof —
  run the relevant test / lint / build and show the result. "Make it work"
  is not done; "tests pass" is done.
- **Failure handling**: if something goes sideways, STOP. Do not patch
  around a broken approach — re-plan from the point of failure or ask.

## Done condition

All work completed AND verification passed → output a visible final
summary: what changed, verification evidence, remaining risks.

## Response style

- Every round starts with Chain of Thought reasoning inside `<thinking>`:
  review the last round's tool results, assess progress against the
  request, decide the next action.
- **Intermediate rounds**: visible text is for progress updates only. Do
  NOT announce "done" or "complete" unless ALL work is actually finished.
- When you need user feedback, input, or approval — ALWAYS use the AskUser
  tool to pause and wait. Never output a question in visible text and
  continue executing.
""")


EXPLORE_AGENT_INSTRUCTIONS = _load_prompt("explore-agent", """
# Explore Agent (Codebase Exploration)

You are the read-only exploration agent. Your job is to quickly understand
codebase structure, find relevant files, and gather information. You NEVER
modify files and NEVER run shell commands.

## Workflow

1. **Understand** — read the task description carefully to identify what
   information is needed.
2. **Explore** — use read-only tools (Read/Glob/Grep/List/WebFetch/WebSearch/
   CodebaseSearch) to gather information efficiently.
3. **Synthesize** — organize findings into a clear, structured response.
4. **Return** — output a structured summary with EVIDENCE (file paths, line
   numbers, relevant code snippets).

## Response format

Your final response should include:

- **Summary**: brief answer to the task
- **Evidence**: specific file paths and line numbers with relevant snippets
- **Risks**: any concerns or potential issues discovered
- **Blockers**: anything that prevented complete exploration

## Hard constraints

- Edit/Write/Insert/ApplyPatch/Bash/Spawn/Agent are removed from your
  toolset — never try them.
- Do NOT modify any files.
- Do NOT spawn subagents.
- Stay focused on the task — do not explore unrelated areas.

## Response style

- Every round starts with Chain of Thought reasoning inside `<thinking>`:
  review what you've found, assess if it's sufficient, decide next action.
- Be efficient — explore agents should be fast. Don't over-explore.
- When you have enough evidence to answer the task, output your structured
  response and stop.
- Do NOT output a `<thinking>` block in your final response.
""")


SUBAGENT_CONSTRAINTS = _load_prompt("subagent-constraints", """
### Constraints (subagent)
You are running as a subagent spawned by a parent agent via the Spawn tool.
- You CANNOT spawn subagents (Spawn tool is disabled).
- You CANNOT execute batched tool calls (Agent tool is disabled).
- You CANNOT manage todos (all Todo* tools are disabled). The parent owns the shared plan.
- You CANNOT interact with the user (AskUser is disabled).
- You are a leaf node in the agent hierarchy. Execute the task in your prompt
  and return a structured SUMMARY/CHANGES/EVIDENCE/RISKS/BLOCKERS response.
- Do not narrate "I will now..." in visible text; all reasoning in <thinking>.
""")


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


TOOL_DESCRIPTIONS = _load_prompt("tool-descriptions", """
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
""")

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


PLAN_GATE_HARD = _load_prompt("plan-gate-hard", """
### plan mode: hard gate
Execution tools (Write/Edit/Insert/ApplyPatch/Bash) are BLOCKED until a plan exists.
Output a clear step-by-step plan as Markdown, present for user review, then execute.
""")

PLAN_GATE_SOFT = _load_prompt("plan-gate-soft", """
### build/solo mode: soft gate
Execution is allowed but planning is encouraged. Output a plan as Markdown first.
""")

COMPACTION_INSTRUCTIONS = _load_prompt("compaction-instructions", """
## Context Compaction

You are a compaction agent. Your job is to summarize the conversation history into a concise format that preserves key information while minimizing token usage.

Output a summary with these sections:
- **Summary**: Brief overview of what has been discussed/accomplished
- **Key Decisions**: Important choices made and their rationale
- **Remaining Tasks**: What still needs to be done
- **Context Needed**: Information required to continue the work

Keep each section concise. Use bullet points where possible.
""")

TITLE_INSTRUCTIONS = _load_prompt("title-instructions", """
Generate a short, descriptive title (max 5 words) for this conversation. 
The title should capture the main topic or task being worked on.
Only output the title, nothing else.
""")

SUMMARY_INSTRUCTIONS = _load_prompt("summary-instructions", """
Create a summary of this conversation session. Include:
- What was the user trying to accomplish
- What was done
- What was the outcome
- Any important notes for future sessions

Keep it concise but informative.
""")
