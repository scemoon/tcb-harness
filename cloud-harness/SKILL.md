# TCB Harness — CloudBase Development Pipeline

Full-lifecycle CloudBase (TCB) development harness driving:

```
Init → Spec → Design → Coding (TDD) → Testing → Deploy
```

## Commands

| Command | Purpose |
|---------|---------|
| `python3 scripts/init_project.py init --name <name> --platform <mp\|web\|oa\|hybrid>` | Create new project |
| `python3 scripts/init_project.py switch <name>` | Set active project |
| `python3 scripts/validate_spec.py specs/<name>/requirements.md` | Validate spec |
| `python3 scripts/project_status.py --name <name>` | Show project status |
| `tcb env list / use / info` | Environment management |
| `tcb fn deploy <name> --env-id <id>` | Deploy cloud function |
| `tcb hosting deploy <dir> --env-id <id>` | Deploy static hosting |

## Platform Types

| Type | Frontend | Auth |
|------|----------|------|
| `mp` | WeChat Mini Program | OPENID |
| `web` | Browser (TDesign React) | Web SDK |
| `oa` | WeChat OA H5 (JSSDK+OAuth) | OAuth 2.0 |
| `hybrid` | Combined | Per-platform |

## Pipeline Phases

### Init
Create project scaffold: `init_project.py --name <name> --platform <type>`
Creates `.harness/config.json` with envId, appid, platform.

### Spec
Write `specs/<name>/requirements.md` using EARS syntax:
- **Ubiquitous:** `The {system} shall {response}`
- **Event-Driven:** `When {trigger}, the {system} shall {response}`
- **Unwanted:** `If {condition}, the {system} shall {response}`
- **State-Driven:** `While {state}, the {system} shall {response}`
- **Optional:** `Where {feature} is enabled, the {system} shall {response}`

Validate with `validate_spec.py`. Each FR needs:
- Priority (P0/P1/P2)
- At least 2 acceptance criteria (positive + exception)
- No vague terms (fast, good, nice, friendly, etc.)

### Design
Write to `design/`:
- `frontend/{platform}/` — UI + component design
- `service/` — API contracts, data models, function signatures
- `shared/` — cross-platform types

### Coding (TDD)
RED → GREEN → REFACTOR cycle:
1. Write test (fails)
2. Write minimal code to pass
3. Refactor

Use `agent_spawn` for parallel independent modules.

### Testing
Generate test cases: `gen_test_cases.py --project <name>`
Coverage ≥ 80% required.

### Deploy
1. Deploy backend (cloud functions first)
2. Deploy frontend (Web hosting or MP upload)
3. Validate with `deploy-config.json`

## EARS Patterns (Quick Reference)

| Pattern | Syntax | Example |
|---------|--------|---------|
| Ubiquitous | `The system shall...` | "The system shall encrypt passwords." |
| Event-Driven | `When X, the system shall Y` | "When user taps Submit, create order." |
| Unwanted | `If X, the system shall Y` | "If write fails, show error toast." |
| State-Driven | `While X, the system shall Y` | "While loading, show spinner." |
| Optional | `Where X is enabled, shall Y` | "Where dark mode, use dark theme." |

## CloudBase CLI

```bash
tcb env list/use/create/info     # Environments
tcb fn deploy/list/invoke        # Cloud functions
tcb db model list/pull/push       # Database models
tcb storage upload/download/list  # Storage
tcb hosting deploy/list          # Static hosting
tcb service create/list           # HTTP access service
```

## Platform Constraints

- **MP:** Max 20 records/query (need pagination), 20s cloud function timeout
- **Web:** CORS handled by CloudBase automatically
- **OA:** Requires OAuth redirect URI configuration

## Project Structure

```
projects/<name>/
├── .harness/
│   ├── config.json         # envId, appid, platform
│   ├── state.json          # phase, tasks, blockers
│   └── deploy-config.json  # deployment tracking
├── specs/                  # requirements.md, design.md, tasks.md
├── design/
│   ├── frontend/{mp,web,oa}/
│   ├── service/
│   └── shared/
├── src/                    # frontend code
├── cloud/                  # cloud functions
└── tests/                  # unit, integration, e2e
```