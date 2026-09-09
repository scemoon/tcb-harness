---
name: ai-dlc-skill
description: |
  AI-Driven Development Lifecycle for monorepo multi-component stacks.
  Core phases: Understand (SDD+BDD), Plan (SDD+TDD), Verify (BDD+TDD),
  Deliver (SDD+Cloud). Adaptive orchestration: Master Agent evaluates
  complexity, delegates sub-tasks.
triggers:
  - ai-dlc
  - lifecycle
  - BDD
  - INT-FR
  - spec-delta
  - EARS
  - feature-file
  - task-list
  - deploy-stack
  - brownfield
  - explore
  - debug
  - tcb-debug
  - tcb-logs
  - 排查日志
allowed_tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
  - TodoClear
  - TodoWrite
  - Task
  - AskUser
phases:
  - understand
  - plan
  - verify
  - deliver
  - brownfield
  - debug
compatibility:
  cdh: ">=1.4"
  opencode: ">=1.15"
  claude-code: ">=1.0"
  openai-codex: ">=1.0"
  cursor: ">=0.45"
license: Apache-2.0
metadata:
  version: "4.0.0"
  stack_topology: monorepo
  fr_namespaces: [NATIVE, DESKTOP, WEB, BE, WXA, MYA, TTA, INT]
---

# AI-DLC Master Orchestrator

## Core Cycle

```
0 Brownfield (optional)  Explore existing codebase → Context summary
① Understand (SDD+BDD)   Intent → Spec Delta → BDD Feature Files
② Plan (SDD+TDD)         Design Doc → Task DAG → Test Plan
③ Verify (BDD+TDD)       Red → Green → Refactor per scenario
④ Deliver (SDD+Cloud)    Stack Preview → e2e → Production + BVT
⑤ Debug (optional)       TCB/云函数日志排查 → 问题定位
```

## Components

| Prefix | Component | Directory | FR Namespace |
|--------|-----------|-----------|--------------|
| NATIVE | Mobile | `apps/native/` | `NATIVE-FR-NNN` |
| DESKTOP | Desktop | `apps/desktop/` | `DESKTOP-FR-NNN` |
| WEB | Browser | `apps/web/` | `WEB-FR-NNN` |
| BE | Service | `apps/backend/` | `BE-FR-NNN` |
| WXA | WeChat Mini | `apps/wxa/` | `WXA-FR-NNN` |
| MYA | Alipay Mini | `apps/mya/` | `MYA-FR-NNN` |
| TTA | TikTok Mini | `apps/tta/` | `TTA-FR-NNN` |
| INT | Contracts | `aidlc/contracts/`, `aidlc/packages/shared/` | `INT-FR-NNN` |

## Adaptive Flow

See `core/adaptive-flow.md` for complexity assessment (L1-L5).
See `core/task-registry.md` for task status tracking.
See `core/security.md` for security baseline (SEC-001~007).

**State file**: `.cdh/state.json`

## Phase Reference

| Phase | Entry | Lifecycle | Rules | Practices |
|-------|-------|-----------|-------|-----------|
| 0 Brownfield | `brownfield/entry.md` | `brownfield/README.md` | — | Explore existing codebase |
| ① Understand | `phases/understand/entry.md` | `phases/understand/lifecycle.md` | `phases/understand/rules.md` | SDD, BDD |
| ② Plan | `phases/plan/entry.md` | `phases/plan/lifecycle.md` | `phases/plan/rules.md` | SDD, TDD |
| ③ Verify | `phases/verify/entry.md` | `phases/verify/lifecycle.md` | `phases/verify/rules.md` | BDD, TDD |
| ④ Deliver | `phases/deliver/entry.md` | `phases/deliver/lifecycle.md` | `phases/deliver/rules.md` | SDD, Cloud |
| ⑤ Debug | `phases/debug/entry.md` | `phases/debug/lifecycle.md` | — | TCB/云函数日志排查 |

## Sub-agent Delegation

Each phase is delegated via `Task(agent_type="ai-dlc-{phase}")` with the phase's `entry.md` as entry point.

## Key Paths

See `aidlc/CONFIG.md` for full path variable definitions.
