# Cloud Dev Harness

AI-powered terminal-based development framework for cloud-native applications, featuring a Textual TUI, multi-provider LLM support, MCP integration, and sandboxed execution.

## Features

- **TUI Chat Interface** — Stream AI responses with rich markdown rendering, thinking blocks, tool use visualization, command autocomplete, and file attachment
- **8 LLM Providers** — MiniMaxi (default), OpenAI, Anthropic, DeepSeek, MiniMax, GLM (Zhipu), Ollama (local) with auto-model selection by task complexity
- **Sandboxed Execution** — Bubblewrap/Docker container isolation with resource limits (CPU, memory, processes, network)
- **MCP Client** — Connect to external Model Context Protocol servers (SSE and stdio transports)
- **Skill System** — Domain-specific knowledge injection with multi-path discovery (`.opencode/skills/`, `.claude/skills/`, `.agents/skills/`)
- **Session Management** — SQLite-backed persistence with create/load/resume/delete/export
- **Multi-Mode Agent** — Build (full tools), Plan (read-only), Solo (independent) modes with hidden system agents (compaction, title, summary)
- **Subagents** — General, Explore (read-only codebase), Scout (web research)
- **Observability** — Distributed tracing with local JSON export or OTLP
- **Task Management** — Task dependency tracking, cron scheduling
- **ACP Protocol** — Agent Communication Protocol for inter-agent messaging
- **HTTP/SSE Server** — Remote agent access via web interface
- **CloudSpec Framework** — Vendor-neutral specification with multi-cloud support (TCB, Aliyun, AWS)
- **Themes** — Dark and light UI themes with CSS customization

## Installation

Choose one of three install methods:

### install.sh (recommended)
```bash
curl -fsSL https://raw.githubusercontent.com/scemoon/cloud-dev-harness/main/install.sh | bash
```
Downloads and installs the latest GitHub release via pip. Adds `cdh` shim to `~/.local/bin/` — add that to your `PATH` if needed.

### npm
```bash
npm install -g cdh
```
Installs via [npm registry](https://www.npmjs.com/npm.com/package/cdh). Requires Node.js >= 16.

Or install from a local `.tgz` built in this repo:
```bash
cd npm && ./build-package.sh build   # creates npm_pkg/cdh-*.tgz
npm install -g ./npm_pkg/cdh-*.tgz
```

### source
```bash
git clone https://github.com/scemoon/cloud-dev-harness.git
cd cloud-dev-harness
pip install -e .
```
Best for development or if you want to track HEAD.

### verify
After any install method, start the TUI:
```bash
cdh tui
```

## Requirements

- Python 3.10+
- LLM provider API key(s)

## Usage

### TUI

| Key | Action |
|-----|--------|
| `Ctrl+F` | Focus chat input |
| `Ctrl+R` | Resume previous session |
| `Tab` | Cycle modes (agent → plan → solo) |
| `Ctrl+P` | Command palette |
| `Ctrl+Q` | Quit |
| `Escape` | Close panels / menus |

### Chat Input

- `/command` — Slash commands with autocomplete
- `@filepath` — Attach file with path autocomplete
- `/help` — List all commands

### CLI

```bash
cdh                          # Launch TUI (agent store)
cdh tui                      # Launch TUI (agent store)
cdh tui --mode plan          # Start in plan mode
cdh tui --agent <identity>   # Launch specific agent directly
cdh config                   # Open configuration editor
cdh config set provider openai
cdh config list              # Show full config
cdh logs                     # View logs (last 20 lines)
cdh logs --tail 100         # View last 100 log lines
cdh logs --follow            # Follow log output
cdh project                  # List projects
cdh project show <name>      # Show project details
cdh version                  # Show version
```

### Key Commands

| Command | Purpose |
|---------|---------|
| `/model switch <name>` | Switch LLM model |
| `/provider switch <name>` | Switch provider |
| `/mode <plan\|agent\|solo>` | Change agent mode |
| `/skill list/add/remove` | Manage skills |
| `/mcp list/add/remove` | MCP server management |
| `/clear` | Clear chat log |
| `/theme` | Toggle dark/light theme |

## Configuration

Config file: `~/.cdh/cdh.config.yaml`

```yaml
default_provider: minimaxi
default_model: MiniMax-M2.7
default_mode: agent
log_level: info

providers:
  minimaxi:
    api_key: ${MINMAXI_API_KEY}
  openai:
    api_key: ${OPENAI_API_KEY}
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
  deepseek:
    api_key: ${DEEPSEEK_API_KEY}

observability:
  trace_enabled: true
  trace_exporter: file
  trace_dir: ~/.cdh/traces

tui:
  theme: auto
  show_right_panel: true

agent:
  max_iterations: 20
  timeout_seconds: 300

sandbox:
  mode: auto  # auto, bwrap, docker, none
  cpu_time: 30
  memory_mb: 512
  max_procs: 10
  network_enabled: false
```

Environment variables are interpolated with `${VAR}` syntax in config values.

## Project Structure

```
├── cdha/                  # Main Python package (CDH Agent)
│   ├── agent/             # Agent engine, tools, sessions
│   │   ├── agents/       # Agent types (build, plan, solo, explore, scout, etc.)
│   │   └── tools/        # Tools (file, bash, web, lsp, mcp, sandbox, etc.)
│   ├── models/           # LLM provider abstraction + 8 providers
│   ├── mcp/              # Model Context Protocol client
│   ├── skills/           # Skill system with multi-path discovery
│   ├── storage/           # SQLite session store
│   ├── trace/            # Distributed tracing (JSON + OTLP)
│   ├── tasks/            # Task management with dependencies
│   ├── memory/           # Memory systems (pyramid, recall, symbolic)
│   └── server/            # HTTP/SSE agent server
├── tui/                  # Textual TUI (A2TUI)
│   ├── screens/          # Main, store, settings, sessions screens
│   ├── widgets/          # TUI widgets
│   └── acp/              # ACP protocol implementation
├── cloud-spec-skill/     # CloudSpec specification framework
│   ├── rules/            # Development standards
│   ├── providers/        # Cloud abstractions (TCB, Aliyun, AWS)
│   └── templates/        # Project scaffolding
├── tests/                # pytest test suite
├── install.sh            # GitHub release installer
└── pyproject.toml
```

## Agents

CDH provides specialized agents with different capabilities:

| Agent | Type | Description |
|-------|------|-------------|
| `build` | primary | Full development agent with all tools enabled |
| `plan` | primary | Read-only planning agent, requires approval for edits/bash |
| `solo` | primary | Independent agent, plans first then executes |
| `general` | subagent | Multi-step tasks with full tool access |
| `explore` | subagent | Fast read-only codebase exploration (hidden) |
| `scout` | subagent | External docs research with web access (hidden) |
| `compaction` | system | Context compression for long conversations (hidden) |
| `title` | system | Session title generation (hidden) |
| `summary` | system | Session summary generation (hidden) |

### Agent Configuration

```yaml
agent:
  build:
    steps: 50              # Max iterations (0 = unlimited)
    temperature: 0.3
    top_p: 0.9             # Alternative to temperature
    color: "#4A90D9"       # UI color
    bash_permissions:       # Command-level bash permissions
      "git *": ask
      "git push": allow
      "rm *": deny
```

## Tools

### Built-in Tools

| Tool | Description |
|------|-------------|
| `read`, `write`, `edit`, `insert`, `undo_edit` | File operations |
| `glob`, `grep`, `list` | Search operations |
| `apply_patch` | Apply patch files (Add/Update/Move/Delete) |
| `bash` | Shell execution with sandbox isolation |
| `webfetch`, `websearch` | Web access |
| `task`, `agent` | Subagent spawning |
| `skill` | Load skills by name |
| `lsp` | Language server intelligence (gotoDefinition, findReferences, hover, etc.) |
| `mcp_tool`, `mcp_resources` | MCP server tools |
| `cron_create/list/remove` | Cron scheduling |
| `worktree` | Git worktree management |
| `config_read`, `config_write` | Configuration |
| `task_create/get/list/update/output/stop` | Task management |
| `todo_create/list/complete` | Todo management |
| `send_message`, `ask_user` | Communication |

### LSP Actions

The `lsp` tool supports:
- `diagnostics` — Get code diagnostics
- `gotoDefinition` — Jump to symbol definition
- `findReferences` — Find symbol references
- `hover` — Get hover information
- `documentSymbol` — List document symbols
- `workspaceSymbol` — Search workspace symbols
- `gotoImplementation` — Jump to implementation
- `callHierarchy` — Analyze call hierarchy
- `incomingCalls` / `outgoingCalls` — Call relationships

## Skills

Skills are markdown-based instruction sets with YAML frontmatter.

### Discovery Paths

CDH searches for skills in:
- `~/.cdh/skills/<name>/SKILL.md` — User skills
- `.opencode/skills/<name>/SKILL.md` — OpenCode compatible
- `.claude/skills/<name>/SKILL.md` — Claude compatible
- `.agents/skills/<name>/SKILL.md` — Agent compatible

### Skill Frontmatter

```yaml
---
name: git-release
description: Create consistent releases and changelogs
license: MIT
compatibility: opencode
metadata:
  audience: maintainers
  workflow: github
---
```

### Skill Name Validation

- 1-64 characters
- Lowercase alphanumeric with single hyphens
- Cannot start/end with hyphen or have consecutive hyphens

## Sandboxing

CDH provides three levels of execution isolation:

### Mode: `none` (default fallback)
Direct execution with resource limits via Python's `resource` module:
- CPU time limit
- Memory limit (RLIMIT_AS)
- Process count limit (RLIMIT_NPROC)
- File descriptor limit (RLIMIT_NOFILE)

### Mode: `bwrap` (recommended)
[Bubblewrap](https://github.com/containers/bubblewrap) Linux namespace isolation:
- `/dev` and `/proc` access
- Read-only bind mounts for system directories
- Writable `/workspace` mount
- Network isolation (`--unshare-net`)
- User/Group isolation
- `/tmp` as tmpfs

### Mode: `docker`
Docker container isolation:
- Memory limit
- CPU quota
- Network disabled by default
- Volume mounts for workspace
- User namespace isolation
- Auto-cleanup on exit

## Supported Providers

| Provider | Endpoint | Default Models | Env Var |
|----------|----------|----------------|---------|
| MiniMaxi | api.minimaxi.com | MiniMax-M2.7, MiniMax-M2.5 | `MINMAXI_API_KEY` |
| OpenAI | api.openai.com | gpt-4o, gpt-4-turbo | `OPENAI_API_KEY` |
| Anthropic | api.anthropic.com | claude-3-opus, claude-3-sonnet, claude-3-haiku | `ANTHROPIC_API_KEY` |
| DeepSeek | api.deepseek.com | deepseek-chat, deepseek-reasoner | `DEEPSEEK_API_KEY` |
| MiniMax | api.minimax.com | MiniMax-M2.7, MiniMax-M2.5 | `MINIMAX_API_KEY` |
| GLM | open.bigmodel.cn | glm-4-plus, glm-4-flash | `GLM_API_KEY` |
| Ollama | localhost:11434 | llama2, codellama (local) | — |

## CloudSpec Framework

Vendor-neutral specification system with multi-cloud support (TCB, Aliyun, AWS).
Rules: GEN-* (general), SEC-* (security), QLT-* (quality), SPC-* (spec).
