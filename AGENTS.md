# AGENTS.md — Project Constitution

Hard rules every AI agent must follow when working in this repo.
Read once per session; behavior is enforced by the agent runtime.

## Project Overview

- **Name**: cloud-dev-harness (CDH)
- **Type**: monorepo — multi-engine AI agent integration framework
- **Python**: >= 3.14.2
- **Architecture layers**:
  - **cdh** (`cdh/`) — **Multi-engine integration platform**: launcher, project registry, platform-level skill/MCP/session management, TUI (vendored from A2TUI). Global state root: `~/.cdh/`
  - **onecode** (`onecode/`) — **Independent agent engine** (registered as a cdh pluggable engine). Owns its own private state root: `~/.onecode/`
  - **tui** (`tui/`) — **Terminal UI (vendored A2TUI), defaults to cdh**. State/log: `~/.cdh/state/tui/`, `~/.cdh/logs/`
  - **opencode / claude / cursor / vtcode / …** — **Independent agent engines** with their own global state directories; registered in `tui/data/agents/*.toml`
  - **npm/** — npm-registry shim package
  - **ai-dlc-skill/** — AI-DLC methodology skill resource repo (source of truth; runtime install → `~/.cdh/skills/ai-dlc-skill/`)
  - `scripts/`, `tests/`, `dist/`, `cloud_dev_harness.egg-info/` — tooling & build

**Key principle**: cdh owns the platform (shared skill pool, shared MCP pool, project registry, session aggregator). Each engine (onecode, opencode, claude…) manages its own private state (`~/.onecode/`, `~/.config/opencode/`, `~/.claude/` …) — no engine hardcodes `~/.cdh/` paths.

## Quality Gates

Hard thresholds the agent must respect and the user will gate on:

- Test coverage >= **80%**
- BDD scenario pass rate = **100%**
- 0 vulns in dependencies
- 0 TODO markers in `src/` / `onecode/` / `tui/` / `cdh/`
- Contract backward-compat by default (breaking → human approval)
- Cross-stack e2e mandatory for multi-component changes

## Code Style (Python)

- Lint: `ruff check .`
- Type check: `mypy onecode/`
- Test: `pytest tests/`
- All public functions must have type hints
- Line length: 100 (ruff default for this project)

## 目标项目 (AI-DLC)

Work is partitioned by component prefix. Place new code in the matching directory:

| Prefix | Component | Path |
|--------|-----------|------|
| NATIVE | Mobile | `apps/native/` |
| DESKTOP | Desktop | `apps/desktop/` |
| WEB | Browser | `apps/web/` |
| BE | Service | `apps/backend/` |
| WXA | WeChat Mini | `apps/wxa/` |
| MYA | Alipay Mini | `apps/mya/` |
| TTA | TikTok Mini | `apps/tta/` |
| INT | Contracts | `contracts/`, `packages/shared/` |

> **注**: 以上是 AI-DLC skill 期望的**目标 monorepo 布局**，与 cdh 工具自身的仓库结构不同。FR 命名空间仅在 AI-DLC 生命周期中使用。

Reference skill: `~/.cdh/skills/ai-dlc-skill/SKILL.md` (full AI-DLC methodology; installed by cdh platform bootstrap).

## File / Path Hygiene

**Never read, write, or modify** any of these (they're local-only / secrets / build artifacts):

- `.cdh/` — project-level runtime state (managed by CLI; never hand-edit)
- `.opencode/`, `.claude/`, `.agents/` — tool configs (owned by user)
- `.qwen/`, `.idea/` — IDE / tool caches
- `dist/`, `*.egg-info/`, `__pycache__/`, `build/`, `.venv/`
- `npm/npm_pkg/*` — npm build output
- `.python-version`, `uv.lock` — Python toolchain pinning (user-managed)
- `.clinerules` — legacy Cline config (kept for reference; superseded by this file)

**Global state directories** (managed at runtime, do not hand-edit):
- `~/.cdh/` — cdh platform global state (projects/, skills/, mcps/, state/, logs/)
- `~/.onecode/` — onecode engine private state (sessions, traces, memory, mcps, skills, config)

## Forbidden Actions

- Commit secrets (API keys, tokens, passwords) — use env vars or vault
- Force-push to `main` / `master`
- Modify files outside the project root
- Run `npm publish` / `pip upload` without explicit user approval
- Hand-edit `.cdh/state.json`, `.cdh/todos.json`, `.cdh/last_session.json` — use CLI / slash commands
- Delete tracked files outside `dist/`, `build/`, `__pycache__/` without confirmation
- Skip `ruff` / `mypy` / `pytest` on non-trivial changes

## Working Conventions

- **Plan first**: Use `TodoCreate` for any non-trivial task (3+ steps)
- **Route execution**:
  - Single-step (1 tool, 1 file) → direct tool call, then `TodoUpdate(status="completed")`
  - Multi-step / multi-file / research → `Spawn(agent_type, prompt)`, then `TodoUpdate(status="completed")`
  - Use `TodoClear` to reset the entire plan and start fresh
- **Session hygiene**:
  - New sessions start with a blank plan (no auto-load of previous todos)
  - Use `/resume <session_id>` to recover a previous session's plan
  - Use `/clear-todos` to reset the current plan
- **Language**: Chinese for explanations to user, English for code / comments / commit messages
- **Verification**: After non-trivial edits, run `ruff check`, `mypy`, and `pytest` before declaring done

## Where to Find More

- **AI-DLC methodology**: `~/.cdh/skills/ai-dlc-skill/SKILL.md` (load via `Skill` tool; installed by cdh bootstrap)
- **Human-readable README**: `README.md`
- **Architecture / practices**: `docs/` if present, or ask the user
- **Legacy Cline rules**: `.clinerules` (some overlap; this file supersedes)
