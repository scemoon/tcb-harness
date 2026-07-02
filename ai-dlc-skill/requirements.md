# AI-DLC Skill — Requirements

## Overview

This skill implements the AI-Driven Development Lifecycle for **monorepo multi-component stacks** (native + desktop + web + backend + wxa + mya + tta) with four core phases — Understand (SDD+BDD), Plan (SDD+TDD), Verify (BDD+TDD), Deliver (SDD+Cloud) — plus a first-class **Integration** discipline that governs cross-component contracts (API, events, shared types).

## Topology

```
┌──────────────────── Monorepo Root ─────────────────────┐
│                                                        │
│  apps/native  apps/desktop  apps/web  apps/backend     │
│  (NATIVE-FR-) (DESKTOP-FR-) (WEB-FR-) (BE-FR-)        │
│  apps/wxa     apps/mya      apps/tta                  │
│  (WXA-FR-)    (MYA-FR-)     (TTA-FR-)                 │
│       │              │           │                    │
│       └──────┬───────┴─────┬─────┘                    │
│              │             │                          │
│          aidlc/contracts/  packages/shared/                 │
│          (INT-FR-*)   (generated types)                     │
│                                                        │
│  aidlc/features/  tests/  aidlc/openspec/  aidlc/providers/              │
└────────────────────────────────────────────────────────┘
```

FR namespaces:

| Prefix | Owner | Scope |
|--------|-------|-------|
| `NATIVE-*` | `apps/native` | Native mobile behavior |
| `DESKTOP-*` | `apps/desktop` | Desktop client behavior |
| `WEB-*` | `apps/web` | Browser frontend behavior |
| `BE-*`  | `apps/backend` | Server/service behavior |
| `WXA-*` | `apps/wxa` | WeChat Mini Program behavior |
| `MYA-*` | `apps/mya` | Mini Program (e.g. Alipay) behavior |
| `TTA-*` | `apps/tta` | TikTok Mini Program behavior |
| `INT-*` | `aidlc/contracts/`, `packages/shared/` | Cross-component contract & integration |

## Functional Requirements

### FR-001: Understand Phase

**Priority:** P0

**When** a developer starts a new feature (single-component or cross-cutting),
**the system SHALL** capture intent, produce an OpenSpec spec delta in EARS format, and write BDD feature files with Given/When/Then scenarios.

**Acceptance Criteria:**
- Intent documented before implementation
- Spec delta uses EARS (Ubiquitous/Event-Driven/State-Driven/Unwanted/Optional)
- Each FR tagged with `@FR-{PREFIX}-NNN` in `.feature` files
- Cross-component features use `INT-*` FRs in addition to per-component FRs
- Minimum 3 scenarios per FR: positive, negative, edge
- Scenarios reviewed and approved by human

### FR-002: Plan Phase

**Priority:** P0

**When** spec and feature files are approved,
**the system SHALL** produce a technical design, decompose work into units with dependency DAG, and write test plans.

**Acceptance Criteria:**
- Design doc includes architecture, data model, API contract, state machine
- Tasks have explicit dependencies (DAG), per-component and cross-component
- Cross-component tasks reference the relevant `INT-*` contract FR
- Test plan written per scenario before implementation

### FR-003: Verify Phase

**Priority:** P0

**When** design and tasks are approved,
**the system SHALL** execute TDD red-green-refactor per BDD scenario and verify all scenarios pass.

**Acceptance Criteria:**
- Tests written before implementation (Red)
- Tests fail initially (confirming assertion works)
- Minimum implementation written to pass (Green)
- Implementation refactored, all tests still pass
- All BDD scenarios pass via pytest-bdd (or equivalent per component)
- Quality gates enforced: coverage ≥80%, scenarios ≥90%, 0 vulns, no TODO
- Per-component unit, integration, and e2e layers are all green
- Cross-stack e2e scenarios pass against the unified preview URL

### FR-004: Deliver Phase

**Priority:** P1

**When** all scenarios pass quality gates,
**the system SHALL** deploy the full stack to preview, run cross-stack BDD e2e tests, and after human approval deploy to production with BVT verification.

**Acceptance Criteria:**
- Unified preview URL dynamically resolved per platform (TCB/Aliyun)
- BDD e2e tests run against preview URL for the component they target
- Cross-stack e2e tests run against the unified preview URL
- Production deploy requires human approval
- BVT (Build Verification Test) passes after production deploy
- Failed BVT triggers rollback

### FR-005: Cross-Component Contract Discipline

**Priority:** P0

**When** a feature spans more than one component (e.g. `WEB-*` + `BE-*`, or `NATIVE-*` + `BE-*`),
**the system SHALL** define and verify the contract between components before integration.

**Acceptance Criteria:**
- All public APIs and async events are described in `aidlc/contracts/` (OpenAPI/AsyncAPI) and tagged with `INT-FR-NNN`
- Contract changes require a contract-diff review (backward-compat by default)
- Shared types are generated from contracts, not hand-written, in `packages/shared/`
- Contract tests run on every PR that touches `aidlc/contracts/` or any consumer
- A breaking contract change requires a major version bump and human approval

### FR-006: Monorepo Stack Awareness

**Priority:** P0

**When** the AI agent operates in a monorepo with multiple components,
**the system SHALL** be aware of which component(s) the current work affects and apply the right scope, tests, and deploy steps.

**Acceptance Criteria:**
- Spec delta, design doc, and task list each declare an `affects: [native, desktop, web, backend, wxa, mya, tta, contracts]` field
- Test plan enumerates the layers it covers: `unit`, `integration`, `e2e`, `cross-stack`
- Only the affected components are deployed in the unified preview (others reused or stubbed)
- BVT and rollback operate on the whole stack, not a single component

## Cross-Cutting Rules (summary)

See `rules/` for full definitions.

| Prefix | File | Phase | Scope |
|--------|------|-------|-------|
| UND | `rules/understand.md` | Understand | Single + multi-component |
| PLN | `rules/plan.md` | Plan | Single + multi-component |
| VRF | `rules/verify.md` | Verify | Single + multi-component |
| DLV | `rules/deliver.md` | Deliver | Stack deploy + rollback |
| INT | `rules/integration.md` | All phases | Cross-component contracts |
| STK | `rules/stack.md` | All phases | Monorepo / multi-component |
| SEC | `rules/security.md` | All phases | Security baseline |
