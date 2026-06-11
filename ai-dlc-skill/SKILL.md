---
name: ai-dlc-skill
description: |
  AI-Driven Development Lifecycle for monorepo multi-component stacks
  (native + desktop + web + backend + wxa + mya + tta).
  ① Understand (SDD+BDD) → ② Plan (SDD+TDD) → ③ Verify (BDD+TDD) → ④ Deliver (SDD+Cloud).
  Cross-component INT-FR contract discipline. Default cloud: TCB.
allowed_tools:
  - read
  - grep
  - glob
  - bash
  - edit
  - write
  - webfetch
triggers:
  - ai-dlc
  - "ai dlc"
  - lifecycle
  - understand
  - plan
  - verify
  - deliver
  - spec-delta
  - EARS
  - BDD
  - feature file
  - monorepo
  - INT-FR
phases: [understand, plan, verify, deliver]
compatibility:
  cdh: ">=1.4"
  opencode: ">=1.15"
  claude-code: ">=1.0"
  openai-codex: ">=1.0"
license: Apache-2.0
metadata:
  version: "3.0.0"
  stack_topology: monorepo
  fr_namespaces: [NATIVE, DESKTOP, WEB, BE, WXA, MYA, TTA, INT]
---

# AI-DLC Development Skill

AI-Driven Development Lifecycle for monorepo multi-component stacks.

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
| INT | Contracts | `contracts/`, `packages/shared/` | `INT-FR-NNN` |

## Lifecycle

| Phase | Lifecycle | Rules | Practices |
|-------|-----------|-------|-----------|
| ① Understand | `lifecycle/understand.md` | `rules/understand.md` | SDD, BDD |
| ② Plan | `lifecycle/plan.md` | `rules/plan.md` | SDD, TDD |
| ③ Verify | `lifecycle/verify.md` | `rules/verify.md`, `rules/integration.md` | BDD, TDD |
| ④ Deliver | `lifecycle/deliver.md` | `rules/deliver.md`, `rules/stack.md` | SDD, Cloud |

Security baseline: `rules/security.md` (all phases).
