# Cloud Dev Harness

AI-powered terminal-based development framework for cloud-native applications, featuring a Textual TUI, multi-provider LLM support, MCP integration, and sandboxed execution.

**Version 1.0.0**

## Features

- **TUI Chat Interface** — Stream AI responses with rich markdown rendering, thinking blocks, tool use visualization, command autocomplete, and file attachment
- **8 LLM Providers** — MiniMaxi (default), OpenAI, Anthropic, DeepSeek, MiniMax, GLM (Zhipu), Ollama (local) with auto-model selection by task complexity
- **Sandboxed Execution** — Bubblewrap/Docker container isolation with resource limits (CPU, memory, processes, network)
- **MCP Client** — Connect to external Model Context Protocol servers (SSE and stdio transports)
- **Skill System** — Domain-specific knowledge injection with multi-path discovery (`.opencode/skills/`, `.claude/skills/`, `.agents/skills/`) and opencode plugin bridge for all CLIs
- **Session Management** — SQLite-backed persistence with create/load/resume/delete/export
- **Multi-Mode Agent** — Build (full tools), Plan (read-only), Solo (independent) modes with hidden system agents (compaction, title, summary)
- **Subagents** — General, Explore (read-only codebase), Scout (web research)
- **Observability** — Distributed tracing with local JSON export or OTLP
- **Task Management** — Task dependency tracking, cron scheduling
- **ACP Protocol** — Agent Communication Protocol for inter-agent messaging
- **HTTP/SSE Server** — Remote agent access via web interface
- **Codebase Indexing** — BM25-based code search, chunking, and retrieval
- **Memory Systems** — Pyramid, recall, and symbolic memory for long-term context
- **Multi-Cloud Abstraction** — Vendor-neutral cloud resource management (TCB, Aliyun, AWS)
- **Themes** — Dark and light UI themes with CSS customization

## Installation

Choose one of three install methods:

### install.sh (recommended)
```bash
curl -fsSL https://raw.githubusercontent.com/scemoon/cloud-dev-harness/main/install.sh | bash
```
Downloads and installs the latest GitHub release via pip. The `cdh` shim is installed to `~/.local/bin/cdh`. Add this to your PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Add this line to your `~/.bashrc` or `~/.zshrc` to make it permanent.

### npm
```bash
npm install -g cdh
```
Installs via [npm registry](https://www.npmjs.com/package/cdh). Requires Node.js >= 18.

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

- Python 3.14+
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
cdh config                   # Open configuration editor (TUI)
cdh config set provider openai
cdh config list              # Show full config
cdh logs                     # View logs (last 20 lines)
cdh logs --tail 100          # View last 100 log lines
cdh logs --follow            # Follow log output
cdh project                  # List projects
cdh project show <name>      # Show project details
cdh session list             # List sessions
cdh session load <id>        # Load session
cdh help                     # Show help
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

Config file: `~/.onecode/onecode.config.yaml`

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
  trace_dir: ~/.onecode/traces

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
├── cdh/                  # Top-level CLI entry point
│   ├── cli.py           # Click CLI (config, logs, projects, sessions, tui)
│   ├── __init__.py
│   └── __main__.py
├── onecode/              # Core agent framework (onecode Agent)
│   ├── agent/           # Agent engine, tools, sessions, permissions
│   │   ├── agents/     # Agent type definitions (build, plan, solo, explore, scout, ...)
│   │   └── tools/      # 23 tools (file, bash, web, lsp, mcp, sandbox, git, cron, task, ...)
│   ├── models/          # LLM provider abstraction + 7 providers
│   │   └── providers/  # MiniMaxi, OpenAI, Anthropic, DeepSeek, MiniMax, GLM, Ollama
│   ├── mcp/             # Model Context Protocol client (SSE + stdio)
│   ├── skills/          # Skill system (loader, manager, frontmatter parsing)
│   ├── builtin_skills/  # Bundled skills (ai-dlc, git, shell)
│   ├── storage/         # SQLite-backed storage (sessions, projects)
│   ├── trace/           # Distributed tracing (JSON + OTLP)
│   ├── tasks/           # Task management with dependencies
│   ├── memory/          # Memory systems (pyramid, recall, symbolic)
│   ├── codebase/        # Codebase indexing & search (BM25)
│   ├── server/          # HTTP/SSE agent server
│   ├── cloud/           # Multi-cloud abstraction layer
│   ├── cron/            # Cron scheduling
│   ├── lsp/             # LSP integration
│   └── utils/           # Helpers and utilities
├── tui/                  # Textual TUI (A2TUI)
│   ├── screens/        # 22 TUI screens (main, store, settings, sessions, projects, ...)
│   ├── widgets/        # 46 TUI widgets (chat, tool calls, terminal, agent response, ...)
│   ├── acp/            # Agent Communication Protocol
│   ├── ansi/           # ANSI escape sequence parser
│   ├── prompt/         # Prompt extraction & resources
│   ├── visuals/        # Visual helpers
│   ├── data/           # Static assets (agents, images, sounds)
│   └── cli.py          # TUI CLI (run, acp, settings, replay, serve, about)
├── ai-dlc-skill/         # AI-DLC lifecycle skill (v4.0.0)
│   ├── SKILL.md         # Master orchestrator entry point
│   ├── skill.yaml       # Skill metadata + component definitions
│   ├── core/            # Core framework
│   │   ├── adaptive-flow.md  # L1-L5 complexity matrix
│   │   └── security.md       # SEC-001..007 rules
│   ├── phases/          # 4 lifecycle phases
│   │   ├── understand/  # Intent → Spec → BDD (entry, lifecycle, rules, prompt)
│   │   ├── plan/        # Design → Task DAG → Test Plan
│   │   ├── verify/      # TDD Red-Green-Refactor → Contract Test → Gates
│   │   └── deliver/     # Stack Preview → e2e → Production + BVT
│   ├── agents/          # Sub-agent definitions
│   │   ├── master.md    # Master orchestrator instructions
│   │   ├── understand-agent.md
│   │   ├── plan-agent.md
│   │   ├── verify-agent.md
│   │   └── deliver-agent.md
│   ├── components/      # 7 component skills (native, desktop, web, backend, wxa, mya, tta)
│   ├── contracts/       # 3-layer contract system (api/events/functions)
│   ├── providers/       # Cloud configs (TCB, Aliyun) with compute_modes
│   ├── templates/       # Project scaffolding + artifacts per phase
│   ├── practices/       # SDD, BDD, TDD practice guides
│   ├── cross-tool/      # Export scripts (CDHA, Cursor, Cline, Copilot)
│   ├── workflows/       # Pipeline workflow YAMLs
│   ├── brownfield/      # Context discovery for existing projects
│   ├── walkthrough/     # Change walkthrough automation
│   └── architecture/    # Project structure documentation
├── npm/                  # npm package wrapper
│   ├── cli.js           # Node.js shim (auto-installs Python dependency)
│   ├── package.json     # npm package metadata
│   └── build-package.sh # Build/publish script
├── .opencode/              # opencode integration
│   ├── skills/ai-dlc-skill → ../../ai-dlc-skill   # Skill symlink
│   └── package.json       # @opencode-ai/plugin dependency
├── scripts/                # CI/Dev utilities
│   └── check_tui_no_print.py  # AST-based guard against bare print() in TUI code
├── tests/                  # pytest test suite (14 files)
├── .github/workflows/     # CI workflows
├── install.sh             # GitHub release installer
├── pyproject.toml          # Package metadata & dependencies
└── version.md             # Version declaration
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

Skills are markdown-based instruction sets with YAML frontmatter, injected into the agent's system prompt at startup.

### Multi-CLI Discovery Architecture

CDH uses a **symlink-based broadcast** + **plugin bridge** approach to make skills work uniformly across all CLIs:

```
ai-dlc-skill/SKILL.md  ←  single source of truth (YAML frontmatter + markdown body)
         │
         ├── .opencode/skills/ai-dlc-skill → ../..        (opencode auto-load)
         ├── .claude/skills/ai-dlc-skill   → ../..        (Claude Code auto-load)
         ├── .agents/skills/ai-dlc-skill   → ../..        (OpenAI Codex / Cursor / Continue.dev)
         └── onecode/builtin_skills/ai-dlc    → ../../ai-dlc-skill  (onecode built-in)
```

### Discovery Paths

CDH searches for skills in:
- `~/.onecode/skills/<name>/SKILL.md` — User skills
- `builtin_skills/` — Skills bundled with CDH (ai-dlc, git, shell)
- `.opencode/skills/<name>/SKILL.md` — OpenCode compatible
- `.claude/skills/<name>/SKILL.md` — Claude Code compatible
- `.agents/skills/<name>/SKILL.md` — Agent protocol compatible (OpenAI Codex, Cursor, Continue.dev)
- Project root directories containing `SKILL.md` — Project-level skills

### Built-in Skill: ai-dlc-skill (v4.0.0)

The `ai-dlc-skill` implements the **AI-Driven Development Lifecycle (AI-DLC)** with adaptive orchestration:

| Phase | Lifecycle Doc | Rules | Practices |
|-------|---------------|-------|-----------|
| ① Understand | `phases/understand/lifecycle.md` | `phases/understand/rules.md` (UND-001..006) | SDD, BDD |
| ② Plan | `phases/plan/lifecycle.md` | `phases/plan/rules.md` (PLN-001..004) | SDD, TDD |
| ③ Verify | `phases/verify/lifecycle.md` | `phases/verify/rules.md` (VRF-001..006 + INT-001..006) | BDD, TDD |
| ④ Deliver | `phases/deliver/lifecycle.md` | `phases/deliver/rules.md` (DLV-001..004 + STK-001..006) | SDD, Cloud |

The **adaptive flow** (`core/adaptive-flow.md`) automatically selects phases based on complexity (L1–L5):
- L1 single-file fix → Verify only
- L2 single-component → Understand → Verify
- L3 multi-component → Understand → Plan → Verify
- L4 full-stack + deploy → Understand → Plan → Verify → Deliver
- L5 architecture refactoring → Plan → Verify

When you run `cdh`, `opencode`, `claude`, or `openai codex` in this repo, the agent automatically loads ai-dlc-skill and follows the adaptive workflow — no manual activation needed.

### Skill Frontmatter

```yaml
---
name: git-release
description: Create consistent releases and changelogs
license: MIT
compatibility:
  opencode: ">=1.15"
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

## Testing

```bash
# install dev dependencies
uv sync --group dev

# run tests
pytest tests/

# check for bare print() in TUI code
python scripts/check_tui_no_print.py
```

CI runs on push/PR to `main` when files under `tui/ansi/` change.

## Entry Points

| Command | Entry Point | Description |
|---------|-------------|-------------|
| `cdh` | `cdh.cli:main` | Main user CLI (launches TUI, config, logs, projects) |
| `onecode` | `onecode.cli:main` | Direct agent CLI access |
| `onecode-agent-acp` | `onecode.agent.onecode_agent_acp:main` | ACP agent server |
| `tui` | `tui.cli:main` | Standalone TUI launcher |
