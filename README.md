# Cloud Dev Harness

AI-powered terminal-based development framework for cloud-native applications, featuring a Textual TUI, multi-provider LLM support, pipeline-driven development lifecycle, and MCP integration.

## Features

- **TUI Chat Interface** — Stream AI responses with rich markdown rendering, thinking blocks, tool use visualization, and command autocomplete
- **7 LLM Providers** — OpenAI, Anthropic Claude, DeepSeek, MiniMax, GLM (Zhipu), Ollama (local), with auto-model selection by task complexity
- **Pipeline Lifecycle** — Structured Init → Spec → Design → Coding (TDD) → Testing → Deploy with quality gates
- **MCP Client** — Connect to external Model Context Protocol servers for extended tool capabilities
- **Skill System** — Domain-specific knowledge injection (git, shell, cloud-harness)
- **Session Management** — SQLite-backed persistence with create/load/rename/delete/export
- **Multi-Mode Agent** — Build (full tools), Plan (read-only), Solo (independent)
- **Observability** — Distributed tracing with local JSON export or OTLP
- **Themes** — Dark and light UI themes with CSS variable customization

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

# Set API key (pick your provider)
cdh config set provider openai
cdh config set model gpt-4o

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
cdh tui                    # Start TUI
cdh tui --mode plan        # Start in plan mode
cdh init                   # Create config directory
cdh config set workspace ~/my-project
cdh config list            # Show full config
```

### Key Commands

| Command | Purpose |
|---------|---------|
| `/model switch <name>` | Switch LLM model |
| `/provider switch <name>` | Switch provider |
| `/mode <plan\|agent\|solo>` | Change agent mode |
| `/session list / new / load` | Session management |
| `/spec generate / accept` | Lifecycle — spec phase |
| `/design generate / accept` | Lifecycle — design phase |
| `/test run / accept` | Lifecycle — testing phase |
| `/deploy` | Lifecycle — deployment |
| `/harness init / import` | CloudBase project scaffolding |
| `/skill list / toggle` | Manage skills |
| `/mcp list / connect` | MCP server management |
| `/trace start / stop / view` | Observability |
| `/vim <file>` | Edit file in vim |
| `/clear` | Clear chat log |
| `/theme` | Toggle dark/light theme |

## Configuration

Config file: `~/.cloud-dev-harness/cdh.config.yaml`

```yaml
default_provider: openai
default_model: gpt-4o
default_mode: agent
log_level: info

providers:
  openai:
    api_key: ${OPENAI_API_KEY}
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
  deepseek:
    api_key: ${DEEPSEEK_API_KEY}

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
├── cdh/                  # Main Python package
│   ├── agent/            # Agent engine, tools, pipeline, sessions
│   ├── models/           # LLM provider abstraction + 7 providers
│   ├── tui/              # Textual TUI (app, widgets, screens, commands)
│   ├── lifecycle/        # Spec/Design/Testing/Deploy stages
│   ├── mcp/              # Model Context Protocol client
│   ├── cloud/            # Cloud provider integration (TCB)
│   ├── storage/          # SQLite session store, project config
│   └── trace/            # Distributed tracing (JSON + OTLP)
├── cloud-harness/        # CloudBase development skill (bundled)
├── skills/               # Built-in skills (git, shell)
├── tests/                # pytest test suite (100+ tests)
├── install.sh            # GitHub release installer
└── pyproject.toml
```

## Supported Providers

| Provider | Models | Env Var |
|----------|--------|---------|
| OpenAI | gpt-4o, gpt-4-turbo | `OPENAI_API_KEY` |
| Anthropic | claude-3-opus, claude-3-sonnet, claude-3-haiku | `ANTHROPIC_API_KEY` |
| DeepSeek | deepseek-chat, deepseek-reasoner | `DEEPSEEK_API_KEY` |
| MiniMax | MiniMax-M2.7, MiniMax-M2.5 | `MINIMAX_API_KEY` |
| GLM | glm-4-plus, glm-4-flash | `GLM_API_KEY` |
| Ollama | llama2, codellama (local) | — |
