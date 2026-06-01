from __future__ import annotations

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
    model: Optional[str] = None
    max_turns: int = 0
    hidden: bool = False
    permission_edit: AgentPermission = AgentPermission.ALLOW
    permission_bash: AgentPermission = AgentPermission.ALLOW
    permission_read: AgentPermission = AgentPermission.ALLOW
    permission_webfetch: AgentPermission = AgentPermission.ALLOW
    permission_websearch: AgentPermission = AgentPermission.DENY
    permission_task: AgentPermission = AgentPermission.ALLOW
    tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)

    def get_tools_config(self) -> dict[str, AgentPermission]:
        return {
            "edit": self.permission_edit,
            "bash": self.permission_bash,
            "read": self.permission_read,
            "webfetch": self.permission_webfetch,
            "websearch": self.permission_websearch,
            "task": self.permission_task,
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


class BuildAgent(AgentConfig):
    def __init__(self):
        super().__init__(
            name="build",
            description="Full development agent with all tools enabled",
            mode=AgentMode.PRIMARY,
            permission_edit=AgentPermission.ALLOW,
            permission_bash=AgentPermission.ALLOW,
            permission_read=AgentPermission.ALLOW,
            permission_webfetch=AgentPermission.ALLOW,
            permission_websearch=AgentPermission.ALLOW,
            max_turns=10,
            tools=[],
        )


class PlanAgent(AgentConfig):
    def __init__(self):
        super().__init__(
            name="plan",
            description="Read-only agent for planning and analysis. Denies all edits and bash unless explicitly asked.",
            mode=AgentMode.PRIMARY,
            permission_edit=AgentPermission.ASK,
            permission_bash=AgentPermission.ASK,
            permission_read=AgentPermission.ALLOW,
            permission_webfetch=AgentPermission.ALLOW,
            permission_websearch=AgentPermission.ALLOW,
            max_turns=5,
            temperature=0.1,
            tools=[],
        )


class SoloAgent(AgentConfig):
    def __init__(self):
        super().__init__(
            name="solo",
            description="Independent agent that plans first, then acts with full tool access. Shell commands require user approval.",
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
            description="General-purpose subagent for complex multi-step tasks",
            mode=AgentMode.SUBAGENT,
            permission_edit=AgentPermission.ALLOW,
            permission_bash=AgentPermission.ALLOW,
            permission_read=AgentPermission.ALLOW,
            tools=[],
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
            hidden=True,
            tools=[],
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
            hidden=True,
            tools=[],
        )


BUILT_IN_AGENTS = {
    "build": BuildAgent,
    "plan": PlanAgent,
    "solo": SoloAgent,
    "general": GeneralAgent,
    "explore": ExploreAgent,
    "scout": ScoutAgent,
}


def create_agent(agent_type: str) -> AgentConfig:
    agent_cls = BUILT_IN_AGENTS.get(agent_type)
    if agent_cls:
        return agent_cls()
    return BuildAgent()


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

    return "\n".join(lines)


TOOL_DESCRIPTIONS = """
## Available Tools

### File Operations
- **Read**: read(path, offset=0, limit=0) - Read file contents. Returns content with line numbers.
- **Write**: write(path, content) - Create or overwrite file with content.
- **Edit**: edit(path, old_string, new_string) - Replace exact string in file. **CRITICAL**: old_string must be UNIQUE in the file — provide enough context (surrounding lines) to guarantee a single match. The edit WILL FAIL if old_string appears multiple times.
- **Insert**: insert(path, line, text) - Insert text at a specific line. line=-1 for beginning, line=0 to insert after line 0, etc. Must read file first to verify target location.
- **UndoEdit**: undo_edit(path) - Undo the most recent Edit/Insert on a file. Restores previous content.
- **Glob**: glob(pattern) - Find files matching glob pattern (e.g., "**/*.py").
- **Grep**: grep(pattern, include=None) - Search for regex pattern in files.
- **List**: list(path=".") - List directory contents.

### Shell
- **Bash**: bash(command, timeout=60) - Execute shell command. Returns stdout/stderr.

### Web
- **WebFetch**: webfetch(url, prompt) - Fetch URL content and extract info.
- **WebSearch**: websearch(query) - Search the web and return results.

### Agent
- **Task**: task(agent_type, prompt) - Spawn subagent to handle subtask.
- **Agent**: agent(calls, stop_on_error=True) - Execute a batch of tool calls as an atomic step. Each call includes {name, input}. Halts on first error when stop_on_error is true.
- **ToolSearch**: tool_search(query) - Search for available tools by keyword.
- **Skill**: skill(name) - Load skill by name.

### Communication
- **SendMessage**: send_message(message, attachments=[]) - Send a user-visible message during execution. Use to communicate status updates, findings, or results.

### Human Interaction
- **AskUser**: ask_user(question, context="") - Ask the user a question. Use when you need:
  - Approval before modifying or creating files (when permission_edit is ASK)
  - Clarification on ambiguous requirements
  - Confirmation before destructive operations
  - Any time you need human input to continue

### Skills (Clawd-Code)
- **Skill**: skill(name, arguments=[]) - Run a registered skill by name. Skills are markdown-based instruction sets with YAML frontmatter.

### MCP (Clawd-Code)
- **MCPTool**: mcp_tool(server, tool, arguments) - Call a tool on a connected MCP server.
- **MCPResources**: mcp_resources(server, action, uri) - List or read resources on an MCP server.

### LSP (Clawd-Code)
- **LSP**: lsp(command, file_path, action) - Get code diagnostics from a Language Server server.

### Cron (Clawd-Code)
- **CronCreate**: cron_create(name, interval_seconds, command) - Create a scheduled cron job.
- **CronList**: cron_list() - List all cron jobs.
- **CronRemove**: cron_remove(name) - Remove a cron job.

### Git (Clawd-Code)
- **Worktree**: worktree(action, path, branch) - Manage git worktrees: create, list, prune.

### Config (Clawd-Code)
- **ConfigRead**: config_read(key) - Read configuration values.
- **ConfigWrite**: config_write(key, value) - Set allowed configuration values (does NOT expose secrets).

### Tasks & Planning (V2 with dependency tracking)
- **TaskCreate**: task_create(subject, description, activeForm="", metadata={}) - Create a task. Returns task id.
- **TaskGet**: task_get(taskId) - Retrieve a task by ID.
- **TaskList**: task_list() - List all tasks with status, owner, and blockers.
- **TaskUpdate**: task_update(taskId, subject, description, activeForm, status, owner, addBlocks, addBlockedBy, metadata, output) - Update task fields and dependencies.
- **TaskOutput**: task_output(task_id) - Get output from a task.
- **TaskStop**: task_stop(task_id) - Stop a running task.
- **TodoCreate**: todo_create(text) - Create a todo item. Returns todo id.
- **TodoList**: todo_list() - List all todos.
- **TodoComplete**: todo_complete(todo_id) - Mark a todo as done.
"""

PLAN_INSTRUCTIONS = """
## Planning & Task Management

When given a goal or task, ALWAYS follow this workflow:
1. **Analyze** the request and break it into steps
2. **Create tasks** using task_create() for each major step
3. **Create todos** using todo_create() for small items
4. **Execute** tasks one by one, updating status with task_update()
5. **Complete** todos as you finish them with todo_complete()

For plan/solo mode, always start by creating a plan with tasks before taking action.
"""