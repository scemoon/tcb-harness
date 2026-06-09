# AI-DLC Development Skill

This skill implements the **AI-Driven Development Lifecycle (AI-DLC)** with **SDD/BDD/TDD** practices, designed for **monorepo multi-component stacks** (app + web + backend) and a first-class **cross-component Integration** discipline.

## Core Cycle

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ① Understand (SDD + BDD)                                              │
│  Intent → Spec Delta (EARS, FR namespace) → BDD Feature Files            │
│  → Gate: human review + scenarios ≥3 per FR                             │
├──────────────────────────────────────────────────────────────────────────┤
│  ② Plan (SDD + TDD)                                                    │
│  Design Doc (per-component + integration) → Task DAG → Test Plan        │
│  → Gate: human review + dependencies explicit + contract refs           │
├──────────────────────────────────────────────────────────────────────────┤
│  ③ Verify (BDD + TDD)                                                  │
│  For each BDD scenario: Red → Green → Refactor                          │
│  unit + integration + e2e + cross-stack                                 │
│  → Gate: cov≥80% + scenarios 100% + 0 vulns + contract tests green      │
├──────────────────────────────────────────────────────────────────────────┤
│  ④ Deliver (SDD + Cloud)                                               │
│  Unified Stack Preview → BDD e2e + Cross-stack e2e → Human Approve       │
│  → Production → BVT (stack-level)                                       │
│  → Gate: BVT pass + all e2e pass + contract diff clean                  │
└──────────────────────────────────────────────────────────────────────────┘
```

## Stack Topology

The skill assumes a **monorepo** with three component kinds and a cross-cutting layer:

| Prefix | Component | Directory | FR Namespace | Typical Tech |
|--------|-----------|-----------|--------------|--------------|
| APP | Mobile / native client | `apps/app/` | `APP-FR-NNN` | React Native / Flutter / Native |
| WEB | Browser frontend | `apps/web/` | `WEB-FR-NNN` | React / Vue / Svelte |
| BE  | Server / service | `apps/backend/` | `BE-FR-NNN` | Python / Node / Go |
| INT | Cross-cutting contracts | `contracts/`, `packages/shared/` | `INT-FR-NNN` | OpenAPI / AsyncAPI / generated types |

A feature that touches more than one component **must** declare:

1. Per-component FRs in each affected component's namespace (`APP-FR-*`, `WEB-FR-*`, `BE-FR-*`).
2. One or more `INT-FR-*` FRs describing the contract between components.
3. The `affects: [app, web, backend, contracts]` field in spec-delta, design, and task-list.

## Monorepo Project Structure

```
{{project_name}}/                       # monorepo root
├── requirements.md                     # Intent + global spec
├── project.yaml                        # Stack topology (components, contracts)
├── apps/
│   ├── app/                            # mobile client (APP-FR-*)
│   │   ├── src/
│   │   ├── tests/{unit,e2e}/
│   │   └── features/                   # APP-FR-*.feature
│   ├── web/                            # browser frontend (WEB-FR-*)
│   │   ├── src/
│   │   ├── tests/{unit,integration,e2e}/
│   │   └── features/                   # WEB-FR-*.feature
│   └── backend/                        # service (BE-FR-*)
│       ├── src/
│       ├── tests/{unit,integration,e2e}/
│       └── features/                   # BE-FR-*.feature
├── contracts/                          # INT-FR-* sources of truth
│   ├── api/                            # OpenAPI 3.1 specs
│   ├── events/                         # AsyncAPI / CloudEvent schemas
│   └── CHANGELOG.md                    # contract version history
├── packages/
│   └── shared/                         # generated types from contracts
├── features/
│   └── cross-stack/                    # INT-FR-*.feature for full flow
├── tests/
│   └── cross-stack/                    # cross-stack e2e (app↔web↔backend)
├── openspec/
│   └── changes/{id}/
│       ├── spec-delta.md               # declares affects + FR namespaces
│       ├── design.md                   # architecture + per-component + integration
│       ├── task-list.md                # DAG with cross-component edges
│       └── contract-diff.md            # auto-generated contract changes
├── providers/                          # cloud config (TCB / Aliyun)
│   ├── tcb/
│   └── aliyun/
├── tools/
│   ├── deploy_stack.py                 # unified preview/prod deploy
│   ├── contract_diff.py                # OpenAPI/AsyncAPI diff + compat check
│   └── generate_shared.py              # contracts → packages/shared
└── pyproject.toml                      # workspace config (uv workspaces / pnpm)
```

The previous single-component structure (`src/`, `features/`, `tests/` at the root) is **deprecated** for new projects. Existing single-component projects continue to work via the legacy layout.

## Phase Detail

### ① Understand — 理解

Capture intent and formalize as spec + behavior scenarios, scoped to the right FR namespace.

```
Intent (business need)
  → OpenSpec spec-delta.md (with affects: [...] + FR namespaces)
  → BDD feature files (APP-/WEB-/BE-/INT- tagged)
  → Human review gate
```

**SDD:** proposal, spec delta (ADDED/MODIFIED/REMOVED), EARS (Ubiquitous/Event-Driven/State-Driven/Unwanted/Optional).

**BDD:** `.feature` files tagged `@FR-{PREFIX}-NNN`, minimum 3 scenarios per FR (positive/negative/edge). Cross-component features split into per-component `*.feature` plus a `features/cross-stack/*.feature` for the end-to-end flow.

### ② Plan — 规划

Design the solution and decompose into tracked units of work, including cross-component edges.

```
Design doc (architecture, data model, API contract, state machine, integration)
  → Task breakdown with dependency DAG (intra + inter component)
  → Test plan per scenario (unit / integration / e2e / cross-stack)
  → Human review gate
```

**SDD:** design doc, task list with DAG.

**TDD:** test plan written before implementation.

**Integration:** when a task changes a contract, the design doc must reference the `INT-FR-*` it implements and the `contract-diff.md` placeholder is filled in `Verify`.

### ③ Verify — 验证

Execute one TDD cycle per BDD scenario at the right test layer.

```
For each BDD scenario in each affected component:
  RED:   Write test at the right layer (unit/integration/e2e) → confirm failure
  GREEN: Write minimum implementation → confirm pass
  REFACTOR: Clean up → all existing tests still pass

After all scenarios:
  pytest --cov --cov-fail-under=80          # per component
  pytest-bdd features/                       # per component
  contract test suite                        # INT-FR-* + OpenAPI/AsyncAPI
  pytest tests/cross-stack/                  # full app↔web↔backend
  Quality gates: coverage ≥80%, scenarios ≥90%, 0 vulns, no TODO, contract diff clean
```

**TDD:** red-green-refactor per scenario.

**BDD:** pytest-bdd scenario verification at the right layer (unit → integration → e2e → cross-stack).

**Integration gates:**
- Contract test green against the generated `packages/shared/`
- OpenAPI/AsyncAPI schema validation green
- Backward-compat check: removing a field or changing a type is a breaking change

### ④ Deliver — 交付

Deploy the full stack together, verify end-to-end, release with stack-level BVT.

```
Unified Stack Preview Deploy (dynamic URL from TCB/Aliyun)
  → Per-component BDD e2e (against component preview URL or stack URL)
  → Cross-stack e2e (full app↔web↔backend against unified URL)
  → Staging deploy + smoke
  → Human approval gate
  → Production deploy (whole stack)
  → BVT (stack-level: /health on backend, app launch probe, web smoke, DB)
  → Gate: BVT pass + all e2e pass + contract diff archived
```

**SDD:** archive change artifacts including `contract-diff.md`.

**Cloud:** TCB (default) or Aliyun, unified stack URL resolved at deploy time. `PREVIEW_URL` is the backend gateway; `app` and `web` receive it as a build-time or runtime config.

## Test Layers (per feature)

| Layer | Scope | Run Against | Speed | Owner |
|-------|-------|-------------|-------|-------|
| `unit` | Single function/module | Local | <1s/test | Component |
| `integration` | Component + its DB / internal API | Local container | ~1s | Component |
| `e2e` | Whole component against its preview | Component preview URL | ~10s | Component |
| `cross-stack` | app ↔ web ↔ backend full flow | Unified stack preview URL | ~30s | Integration |

`cross-stack` is mandatory for any feature that touches ≥2 components. Otherwise `e2e` per component is the highest required layer.

## Quality Gates

| ID | Gate | Command | Threshold | Scope |
|----|------|---------|-----------|-------|
| VRF-001 | TDD Red | `pytest -k {scenario}` | Test fails first | Per component |
| VRF-002 | TDD Green | `pytest -k {scenario}` | Test passes | Per component |
| VRF-003 | TDD Refactor | `pytest --cov` | Coverage ≥80% | Per component |
| VRF-004 | BDD Scenarios | `pytest-bdd features/` | 100% pass | Per component |
| VRF-005 | Backpressure | All gates | Block until pass | Per component |
| INT-001 | Contract test | `pytest tests/contract/` | 100% pass | Cross-component |
| INT-002 | Contract compat | `tools/contract_diff.py` | Backward-compat | Cross-component |
| INT-003 | Shared types build | `tools/generate_shared.py` | Exit 0 | Cross-component |
| STK-001 | Cross-stack e2e | `pytest tests/cross-stack/` | 100% pass | Stack |
| DLV-003 | Stack BVT | `bvt ${STACK_URL}` | All checks pass | Stack |

## Rule Categories

| Prefix | File | Phase | Scope |
|--------|------|-------|-------|
| UND | `rules/understand.md` | Understand | All |
| PLN | `rules/plan.md` | Plan | All |
| VRF | `rules/verify.md` | Verify | Per component |
| INT | `rules/integration.md` | All phases | Cross-component |
| STK | `rules/stack.md` | All phases | Monorepo / multi-component |
| DLV | `rules/deliver.md` | Deliver | Stack |
| SEC | `rules/security.md` | All phases | All |

## Cloud Platforms

| Platform | Default | Stack Deploy | Per-component | Preview URL |
|----------|---------|--------------|---------------|-------------|
| TCB | ✅ | `deploy_stack --preview` | `tcb fn deploy` / `tcb hosting deploy` | `https://{env-id}.tcb-preview.com` (gateway) |
| Aliyun | | `deploy_stack --preview` | `fun deploy` / OSS / FC | `https://{gateway}.{region}.fc.devs.com` |

The stack deploy command orchestrates: backend (functions + DB migrate) → web (hosting) → app (build + config injection with `BACKEND_URL`). Preview URL is the backend gateway; component build configs read it from env.

## Quick Start (monorepo)

```bash
# ① Understand — declare scope + namespaces
cat > openspec/changes/CHG-001/spec-delta.md <<'YAML'
affects: [web, backend, contracts]
frs:
  - id: WEB-FR-001   # login UI
  - id: BE-FR-001    # login API
  - id: INT-FR-001   # POST /auth/login contract
YAML
# → write features/web/auth/login.feature  (WEB-FR-001)
# → write features/backend/auth/login.feature (BE-FR-001)
# → write features/cross-stack/auth/login.feature (INT-FR-001)

# ② Plan
# → write design.md (per-component sections + integration section)
# → write task-list.md with DAG crossing web → contracts → backend

# ③ Verify
# Backend
pytest apps/backend/tests/unit/ --verbose          # RED
# implement apps/backend/src/auth/login.py
pytest apps/backend/tests/unit/ --verbose          # GREEN
pytest apps/backend/ --cov --cov-fail-under=80     # REFACTOR
# Frontend
pnpm --filter web test                               # RED/GREEN/REFACTOR
# Contracts
tools/generate_shared.py                             # regenerate packages/shared
pytest tests/contract/                               # contract tests green
# Cross-stack
pytest tests/cross-stack/ -k INT-FR-001

# ④ Deliver
deploy_stack --preview                                # unified URL
export PREVIEW_URL=$(deploy_stack --preview --output url)
pytest apps/web/tests/e2e/ --preview-url $PREVIEW_URL
pytest tests/cross-stack/ --preview-url $PREVIEW_URL
deploy_stack --env staging
deploy_stack --env production                        # after human approval
bvt ${PRODUCTION_URL}                                # stack-level BVT
```
