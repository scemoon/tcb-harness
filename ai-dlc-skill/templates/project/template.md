# {{project_name}}

AI-DLC monorepo project. Stack: native + desktop + web + backend + wxa + mya + tta with cross-component contracts.

## Project Layout

```
{{project_name}}/
├── project.yaml                       # Stack topology
├── requirements.md                    # Intent + global spec
├── apps/
│   ├── native/                        # NATIVE-FR-* native mobile
│   │   ├── src/
│   │   ├── tests/{unit,e2e}/
│   │   └── features/
│   ├── desktop/                       # DESKTOP-FR-* desktop
│   │   ├── src/
│   │   ├── tests/{unit,e2e}/
│   │   └── features/
│   ├── web/                           # WEB-FR-*    browser frontend
│   │   ├── src/
│   │   ├── tests/{unit,integration,e2e}/
│   │   └── features/
│   ├── wxa/                           # WXA-FR-*    WeChat Mini Program
│   │   ├── src/
│   │   ├── tests/{e2e}/
│   │   └── features/
│   ├── mya/                           # MYA-FR-*    Mini Program
│   │   ├── src/
│   │   ├── tests/{e2e}/
│   │   └── features/
│   ├── tta/                           # TTA-FR-*    TikTok Mini Program
│   │   ├── src/
│   │   ├── tests/{e2e}/
│   │   └── features/
│   └── backend/                       # BE-FR-*     service / API
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
    - id: native    { fr_prefix: NATIVE, tech: react-native | flutter,        dir: apps/native,  default_language: dart,        default_ui_framework: flutter-sdk }
    - id: desktop   { fr_prefix: DESKTOP, tech: electron | tauri,            dir: apps/desktop, default_language: typescript,   default_ui_framework: electron-react }
    - id: web       { fr_prefix: WEB,    tech: react | vue | svelte,        dir: apps/web,     default_language: typescript,   default_ui_framework: nextjs }
    - id: backend   { fr_prefix: BE,     tech: python | node | go,          dir: apps/backend }
    - id: wxa       { fr_prefix: WXA,    tech: miniprogram,                 dir: apps/wxa,     default_language: javascript,   default_ui_framework: vant-weapp }
    - id: mya       { fr_prefix: MYA,    tech: miniprogram,                 dir: apps/mya,     default_language: javascript,   default_ui_framework: ant-design-mini }
    - id: tta       { fr_prefix: TTA,    tech: miniprogram,                 dir: apps/tta,     default_language: typescript }
  cross_cutting:
    fr_prefix: INT
    contracts: contracts/
    shared_types: packages/shared/
```

## AI-DLC Workflow

```bash
# ① Understand
# requirements.md → openspec/changes/{id}/spec-delta.md (with affects)
# → features/{component}/{domain}/{feature}.feature
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
