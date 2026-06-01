# Cloud Dev Harness

AI-powered terminal-based development framework for cloud-native applications, featuring a Textual TUI, multi-provider LLM support, pipeline-driven development lifecycle, and MCP integration.

## Features

- **TUI Chat Interface** — Stream AI responses with rich markdown rendering, thinking blocks, tool use visualization, command autocomplete, and file attachment
- **8 LLM Providers** — MiniMaxi (default), OpenAI, Anthropic, DeepSeek, MiniMax, GLM (Zhipu), Ollama (local) with auto-model selection by task complexity
- **Pipeline Lifecycle** — Structured Init → Spec → Design → Coding (TDD) → Testing → Deploy with quality gates
- **MCP Client** — Connect to external Model Context Protocol servers (SSE and stdio transports)
- **Skill System** — Domain-specific knowledge injection with built-in git and shell skills
- **Session Management** — SQLite-backed persistence with create/load/resume/delete/export
- **Multi-Mode Agent** — Build (full tools), Plan (read-only), Solo (independent) modes
- **Subagents** — General, Explore (read-only codebase), Scout (web research)
- **Observability** — Distributed tracing with local JSON export or OTLP
- **Task Management** — Task dependency tracking, cron scheduling
- **ACP Protocol** — Agent Communication Protocol for inter-agent messaging
- **HTTP/SSE Server** — Remote agent access via web interface
- **CloudSpec Framework** — Vendor-neutral specification with multi-cloud support (TCB, Aliyun, AWS)
- **Themes** — Dark and light UI themes with CSS customization

## Quick Start

```bash
# One-liner install
curl -fsSL https://raw.githubusercontent.com/anomalyco/cloud-dev-harness/main/install.sh | bash

# Or from source
git clone https://github.com/anomalyco/cloud-dev-harness.git
cd cloud-dev-harness
pip install -e .

# Initialize config directory
cdh init

# Set API key (MiniMaxi is default provider)
cdh config set provider minimaxi
cdh config set model MiniMax-M2.7

# Start the TUI
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
cdh tui                       # Start TUI
cdh tui --mode plan           # Start in plan mode
cdh tui --agent <name>        # Start specific agent
cdh init                      # Create config directory
cdh config                    # Open configuration editor
cdh config set provider openai
cdh config list               # Show full config
cdh logs --tail               # View logs
```

### Key Commands

| Command | Purpose |
|---------|---------|
| `/model switch <name>` | Switch LLM model |
| `/provider switch <name>` | Switch provider |
| `/mode <plan\|agent\|solo>` | Change agent mode |
| `/skill list/add/remove` | Manage skills |
| `/mcp list/add/remove` | MCP server management |
| `/spec` | Show lifecycle stages |
| `/clear` | Clear chat log |
| `/theme` | Toggle dark/light theme |
| `/vim <file>` | Edit file in vim |

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
```

Environment variables are interpolated with `${VAR}` syntax in config values.

## Project Structure

```
├── cdha/                  # Main Python package (CDH Agent)
│   ├── agent/             # Agent engine, tools, pipeline, sessions
│   ├── models/           # LLM provider abstraction + 8 providers
│   ├── lifecycle/         # Spec/Design/Testing/Deploy stages
│   ├── mcp/               # Model Context Protocol client
│   ├── skills/            # Skill system and loader
│   ├── storage/           # SQLite session store
│   ├── trace/             # Distributed tracing (JSON + OTLP)
│   ├── tasks/             # Task management with dependencies
│   ├── memory/            # Memory systems (pyramid, recall, symbolic)
│   └── server/            # HTTP/SSE agent server
├── tui/                   # Textual TUI (A2TUI)
│   ├── screens/           # Main, store, settings, sessions screens
│   ├── widgets/           # TUI widgets
│   └── acp/               # ACP protocol implementation
├── cloud-spec-skill/       # CloudSpec specification framework
│   ├── rules/             # Development standards
│   ├── providers/         # Cloud abstractions (TCB, Aliyun, AWS)
│   └── templates/         # Project scaffolding
├── builtin_skills/         # Built-in skills (git, shell)
├── tests/                 # pytest test suite
├── install.sh             # GitHub release installer
└── pyproject.toml
```

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

Vendor-neutral specification system with multi-cloud support:

```bash
# Initialize a new project
cdh harness init

# Import existing cloud project
cdh harness import

# Generate specification
/spec generate
```

Rules: GEN-* (general), SEC-* (security), QLT-* (quality), SPC-* (spec)

Supported clouds: Tencent CloudBase (TCB), Aliyun, AWS
