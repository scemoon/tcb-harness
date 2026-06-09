# AI-DLC Development Skill

This skill implements the **AI-Driven Development Lifecycle (AI-DLC)** with **SDD/BDD/TDD** practices.

## Core Cycle

```
┌──────────────────────────────────────────────────────────────────────┐
│  ① Understand (SDD + BDD)                                          │
│  Intent → Spec Delta (EARS) → BDD Feature Files                     │
│  → Gate: human review + scenarios ≥3 per FR                         │
├──────────────────────────────────────────────────────────────────────┤
│  ② Plan (SDD + TDD)                                                │
│  Design Doc → Task DAG → Test Plan                                  │
│  → Gate: human review + dependencies explicit                       │
├──────────────────────────────────────────────────────────────────────┤
│  ③ Verify (BDD + TDD)                                              │
│  For each BDD scenario: Red → Green → Refactor                      │
│  → Gate: pytest cov≥80% + pytest-bdd 100% + 0 vulns                 │
├──────────────────────────────────────────────────────────────────────┤
│  ④ Deliver (SDD + Cloud)                                           │
│  Preview Deploy → BDD E2E → Human Approve → Production → BVT       │
│  → Gate: BVT pass + all e2e pass                                    │
└──────────────────────────────────────────────────────────────────────┘
```

## Phase Detail

### ① Understand — 理解

Capture intent and formalize as spec + behavior scenarios.

```
Intent (business need)
  → OpenSpec spec-delta.md with EARS format
  → BDD feature file with Given/When/Then scenarios
  → Human review gate
```

**SDD:** proposal, spec delta (ADDED/MODIFIED/REMOVED), EARS (Ubiquitous/Event-Driven/State-Driven/Unwanted/Optional)

**BDD:** `.feature` files tagged `@FR-NNN`, minimum 3 scenarios per FR (positive/negative/edge)

### ② Plan — 规划

Design the solution and decompose into tracked units of work.

```
Design doc (architecture, data model, API, state machine)
  → Task breakdown with dependency DAG
  → Test plan per scenario
  → Human review gate
```

**SDD:** design doc, task list with DAG

**TDD:** test plan written before implementation

### ③ Verify — 验证

Execute one TDD cycle per BDD scenario.

```
For each BDD scenario:
  RED:   Write pytest test → confirm failure
  GREEN: Write minimum implementation → confirm pass
  REFACTOR: Clean up → all existing tests still pass

After all scenarios:
  pytest-bdd features/ → all scenarios pass
  Quality gates: coverage ≥80%, scenarios ≥90%, 0 vulns, no TODO
```

**TDD:** red-green-refactor per scenario

**BDD:** pytest-bdd scenario verification

### ④ Deliver — 交付

Deploy, verify in production-like environment, and release.

```
Preview deploy (dynamic URL from TCB/Aliyun)
  → BDD e2e tests against preview URL
  → Staging deploy + smoke
  → Human approval gate
  → Production deploy
  → BVT (Build Verification Test)
```

**SDD:** archive change artifacts

**Cloud:** TCB (default) or Aliyun, URL resolved at runtime

## Quality Gates

| ID | Gate | Command | Threshold |
|----|------|---------|-----------|
| VRF-001 | TDD Red | `pytest -k {scenario}` | Test fails first |
| VRF-002 | TDD Green | `pytest -k {scenario}` | Test passes |
| VRF-003 | TDD Refactor | `pytest --cov` | Coverage ≥80% |
| VRF-004 | BDD Scenarios | `pytest-bdd features/` | 100% pass |
| VRF-005 | Backpressure | All gates | Block until pass |
| DLV-003 | BVT | `bvt ${URL}` | All health checks pass |

## Rule Categories

| Prefix | File | Phase |
|--------|------|-------|
| UND | `rules/understand.md` | Understand |
| PLN | `rules/plan.md` | Plan |
| VRF | `rules/verify.md` | Verify |
| DLV | `rules/deliver.md` | Deliver |

## Project Structure

```
project/
├── requirements.md              # Intent + spec
├── openspec/
│   └── changes/{id}/            # Spec artifacts
│       ├── spec-delta.md
│       ├── design.md
│       └── task-list.md
├── features/                    # BDD feature files
│   ├── steps/                   # pytest-bdd step defs
│   └── {domain}/{feature}.feature
├── tests/                       # TDD tests
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── src/                         # Implementation
└── providers/                   # Cloud config
```

## Cloud Platforms

| Platform | Default | Functions | Database | Storage | Hosting |
|----------|---------|-----------|----------|---------|---------|
| TCB | ✅ | CloudBase | DocDB+MySQL | COS | Static + Preview |
| Aliyun | | FC | RDS+TableStore | OSS | Static + CDN |

Preview URLs dynamically resolved per platform at deploy time.

## Quick Start

```bash
# ① Understand
echo "Intent: User Login" > requirements.md
# → write spec-delta.md (EARS)
# → write features/auth/login.feature (BDD)

# ② Plan
# → write design.md + task-list.md with DAG

# ③ Verify
pytest tests/unit/ --verbose    # RED: fails
# implement src/auth/login.py
pytest tests/unit/ --verbose    # GREEN: passes
# refactor
pytest --cov --cov-fail-under=80  # still green
pytest-bdd features/              # all scenarios pass

# ④ Deliver
deploy_cloud --preview           # dynamic URL
pytest tests/e2e/
deploy_cloud --env production    # after human approval
bvt ${PRODUCTION_URL}
```
