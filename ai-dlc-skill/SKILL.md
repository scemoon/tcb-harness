---
name: ai-dlc-skill
description: |
  AI-Driven Development Lifecycle for monorepo multi-component stacks.
  Core phases: Understand (SDD+BDD), Plan (SDD+TDD), Verify (BDD+TDD),
  Deliver (SDD+Cloud). Adaptive orchestration: Master Agent evaluates
  complexity, delegates sub-tasks.
allowed_tools:
  - read
  - grep
  - glob
  - bash
  - edit
  - write
  - webfetch
  - websearch
  - task
  - skill
triggers:
  - ai-dlc
  - ai dlc
  - lifecycle
  - BDD
  - INT-FR
phases:
  - understand
  - plan
  - verify
  - deliver
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
① Understand (SDD+BDD)   Intent → Spec Delta → BDD Feature Files
② Plan (SDD+TDD)         Design Doc → Task DAG → Test Plan
③ Verify (BDD+TDD)       Red → Green → Refactor per scenario
④ Deliver (SDD+Cloud)    Stack Preview → e2e → Production + BVT
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

See `core/adaptive-flow.md` for complexity assessment.
See `core/task-registry.md` for task status tracking.

1. **Check Registry**: Read `.opencode/plans/task-registry.json`, check if intent already processed
   - Found + all phases completed → SKIP, return existing result
   - Found + partially completed → skip completed phases, run pending only
   - Not found → create new task entry
2. Analyze intent → determine complexity (L1-L5)
3. Select phases to execute (skip any already completed per registry)
4. `taskRegistry.create()` — record task with phase list
5. For each pending phase:
   a. Call `TodoClear` to reset the plan
   b. Delegate via `Task(agent_type="general", prompt=...)` using the phase's `prompt.md`
   c. Collect result, enforce gate
   d. `taskRegistry.completePhase()` — mark phase completed with artifacts
6. All phases done → mark task `completed` in registry

```

## Phase Reference

| Phase | Lifecycle | Rules | Practices |
|-------|-----------|-------|-----------|
| ① Understand | `phases/understand/lifecycle.md` | `phases/understand/rules.md` | SDD, BDD |
| ② Plan | `phases/plan/lifecycle.md` | `phases/plan/rules.md` | SDD, TDD |
| ③ Verify | `phases/verify/lifecycle.md` | `phases/verify/rules.md` | BDD, TDD |
| ④ Deliver | `phases/deliver/lifecycle.md` | `phases/deliver/rules.md` | SDD, Cloud |

Security baseline: `core/security.md` (all phases).
