# {{project_name}}

AI-DLC monorepo project. Stack: app + web + backend with cross-component contracts.

## Project Layout

```
{{project_name}}/
├── project.yaml                       # Stack topology
├── requirements.md                    # Intent + global spec
├── apps/
│   ├── app/                           # APP-FR-*   mobile / native
│   │   ├── src/
│   │   ├── tests/{unit,e2e}/
│   │   └── features/
│   ├── web/                           # WEB-FR-*   browser frontend
│   │   ├── src/
│   │   ├── tests/{unit,integration,e2e}/
│   │   └── features/
│   └── backend/                       # BE-FR-*    service / API
│       ├── src/
│       ├── tests/{unit,integration,e2e}/
│       └── features/
├── contracts/                         # INT-FR-*   single source of truth
│   ├── api/                           # OpenAPI 3.1
│   ├── events/                        # AsyncAPI / CloudEvent
│   └── CHANGELOG.md
├── packages/shared/                   # generated from contracts
├── features/cross-stack/              # INT-FR-*.feature full flow
├── tests/
│   ├── contract/                      # INT contract tests
│   └── cross-stack/                   # cross-stack e2e
├── openspec/changes/{id}/
│   ├── spec-delta.md                  # declares affects + FR namespaces
│   ├── design.md                      # per-component + integration
│   ├── task-list.md                   # DAG with cross-component edges
│   └── contract-diff.md               # auto-generated contract changes
├── providers/{tcb,aliyun}/
└── tools/
    ├── deploy_stack.py                # unified stack deploy
    ├── contract_diff.py               # contract compat check
    └── generate_shared.py             # contracts → packages/shared
```

## project.yaml

```yaml
stack:
  topology: monorepo
  components:
    - id: app       { fr_prefix: APP, tech: react-native, dir: apps/app }
    - id: web       { fr_prefix: WEB, tech: react,        dir: apps/web }
    - id: backend   { fr_prefix: BE,  tech: python,       dir: apps/backend }
  cross_cutting:
    fr_prefix: INT
    contracts: contracts/
    shared_types: packages/shared/
```

## AI-DLC Workflow

```bash
# ① Understand
# requirements.md → openspec/changes/{id}/spec-delta.md (with affects)
# → features/{app|web|backend}/{domain}/{feature}.feature
# → features/cross-stack/{domain}/{feature}.feature  (if cross-component)

# ② Plan
# → openspec/changes/{id}/design.md  (per-component + integration)
# → openspec/changes/{id}/task-list.md (DAG with cross-component edges)

# ③ Verify
# For each affected component, per BDD scenario: RED → GREEN → REFACTOR
# Then: tools/generate_shared.py  →  pytest tests/contract/
# Then: pytest tests/cross-stack/  (if cross-component)

# ④ Deliver
deploy_stack --preview                # unified stack URL
# per-component e2e + cross-stack e2e against PREVIEW_URL
deploy_stack --env staging
deploy_stack --env production         # after human approval
bvt ${PRODUCTION_URL}                 # stack BVT
```

## Quality Gates

| Gate | Command | Threshold |
|------|---------|-----------|
| TDD coverage | `pytest --cov` per component | ≥80% |
| BDD scenarios | `pytest-bdd features/` per component | 100% pass |
| Contract | `pytest tests/contract/` | 100% pass |
| Cross-stack e2e | `pytest tests/cross-stack/` | 100% pass |
| Contract diff | `tools/contract_diff.py` | backward-compat |
| Security | `bandit -r apps/` | 0 vulns |
| Stack BVT | `bvt ${URL}` | all checks pass |

## License

{{license}}
