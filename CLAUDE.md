# cloud-dev-harness

<!-- ═══════════════════════════════════════════════════════════
     Generated from ai-dlc-skill/SKILL.md — do not edit manually.
     Rebuild with `cdh scaffold` to sync with the source skill.
     ═══════════════════════════════════════════════════════════ -->

## AI-DLC v4.0.0 — Master Orchestrator

AI-Driven Development Lifecycle for monorepo multi-component stacks.
Core phases: Understand (SDD+BDD), Plan (SDD+TDD), Verify (BDD+TDD),
Deliver (SDD+Cloud). Adaptive orchestration — evaluate complexity, select
phases, delegate sub-tasks.

### Core Cycle

```
① Understand (SDD+BDD)   Intent → Spec Delta → BDD Feature Files
② Plan (SDD+TDD)         Design Doc → Task DAG → Test Plan
③ Verify (BDD+TDD)       Red → Green → Refactor per scenario
④ Deliver (SDD+Cloud)    Stack Preview → e2e → Production + BVT
```

### Components

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

### Adaptive Flow

Analyze intent → determine complexity (L1-L5) → select phases:

| Level | Trigger | Phases |
|-------|---------|--------|
| L1 | Single-file bug fix, no behavior change | Verify |
| L2 | Single-component feature, no INT contract | Understand → Verify |
| L3 | Multi-component feature, needs INT contract | Understand → Plan → Verify |
| L4 | Full-stack feature + deploy | Understand → Plan → Verify → Deliver |
| L5 | Architecture refactor / platform migration | Plan → Verify |

Evaluation dimensions: Scope (single/multi/full-stack), Type (bug/feature/refactor/migration),
Contract (INT-FR involved?), Deploy (production?).

### Phase Reference

| Phase | Lifecycle | Rules | Practices |
|-------|-----------|-------|-----------|
| ① Understand | `phases/understand/lifecycle.md` | `phases/understand/rules.md` | SDD, BDD |
| ② Plan | `phases/plan/lifecycle.md` | `phases/plan/rules.md` | SDD, TDD |
| ③ Verify | `phases/verify/lifecycle.md` | `phases/verify/rules.md` | BDD, TDD |
| ④ Deliver | `phases/deliver/lifecycle.md` | `phases/deliver/rules.md` | SDD, Cloud |

Security baseline: `core/security.md` (all phases).

<!-- ═══════════════════════════════════════════════════════════
     Project Rules
     ═══════════════════════════════════════════════════════════ -->

## Project Rules

1. Intent → Spec (EARS) → BDD → Design (DAG) → TDD Red-Green-Refactor → Deploy
2. Contract-first for cross-component changes (`aidlc/contracts/`)
3. FR namespaces: NATIVE|DESKTOP|WEB|BE|WXA|MYA|TTA (apps/) + INT (aidlc/contracts/)
4. Quality gates: coverage ≥80%, BDD 100%, 0 vulns, no TODO, backward-compat contracts
5. Cross-stack e2e mandatory for changes affecting ≥2 components
6. Never commit secrets; never force-push to main/master
7. Chinese for user communication, English for code
8. Run lint/typecheck/test after non-trivial edits
