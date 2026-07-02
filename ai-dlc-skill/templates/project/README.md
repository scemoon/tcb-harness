# {{project_name}}

{{description}}

## Stack

| Component | FR Prefix | Default Language | Default UI Framework | Directory | Purpose |
|-----------|-----------|-----------------|---------------------|-----------|---------|
| native | `NATIVE-FR-*` | Dart | Flutter SDK | `apps/native/` | Native mobile client |
| desktop | `DESKTOP-FR-*` | TypeScript | Electron + React | `apps/desktop/` | Desktop client |
| web | `WEB-FR-*` | TypeScript | Next.js | `apps/web/` | Browser frontend |
| backend | `BE-FR-*` | Python / Node / Go | FastAPI / Express / Fiber | `apps/backend/` | Service / API |
| wxa | `WXA-FR-*` | JavaScript | Vant Weapp | `apps/wxa/` | WeChat Mini Program |
| mya | `MYA-FR-*` | JavaScript | Ant Design Mini | `apps/mya/` | Mini Program (e.g. Alipay) |
| tta | `TTA-FR-*` | TypeScript | — | `apps/tta/` | TikTok Mini Program |
| contracts | `INT-FR-*` | — | — | `aidlc/contracts/`, `packages/shared/` | Cross-component contracts |

Cloud: {{cloud_provider}} (default: TCB).

## Quick Start

```bash
# ① Understand — declare scope + namespaces
cat > openspec/changes/CHG-001/spec-delta.md <<'YAML'
affects: [{{primary_components}}]
frs:
  - id: {{primary_namespace}}-FR-001
  - id: INT-FR-001   # if cross-component
YAML
# write features/{component}/{domain}/{feature}.feature
# if cross-component, also write aidlc/features/cross-stack/{domain}/{feature}.feature

# ② Plan
# write openspec/changes/CHG-001/design.md
# write openspec/changes/CHG-001/task-list.md  (DAG with cross-component edges)

# ③ Verify
# Per component: TDD red-green-refactor
{{verify_per_component}}
# Contracts
aidlc/tools/generate_shared.py
pytest tests/contract/
# Cross-stack (if applies)
pytest tests/cross-stack/ -k INT-FR-001

# ④ Deliver
deploy_stack --preview                                # unified stack URL
export PREVIEW_URL=$(deploy_stack --preview --output url)
pytest {e2e_paths} --preview-url $PREVIEW_URL
deploy_stack --env staging
deploy_stack --env production                        # after human approval
bvt ${PRODUCTION_URL}                                # stack-level BVT
```

## Development

### Prerequisites

- Python 3.11+
- Node 20+ (for web/native/desktop/mini-programs)
- uv (Python workspace manager) or pnpm
- pytest + pytest-bdd + pytest-cov
- Cloud CLI: `tcb` (TCB) or `fun` (Aliyun)

### Project Structure

```
{{project_name}}/
├── project.yaml                 # stack topology, components, contracts
├── apps/
│   ├── native/                  # NATIVE-FR-* (native mobile)
│   ├── desktop/                 # DESKTOP-FR-* (desktop)
│   ├── web/                     # WEB-FR-*   (browser frontend)
│   ├── wxa/                     # WXA-FR-*   (WeChat Mini Program)
│   ├── mya/                     # MYA-FR-*   (Mini Program)
│   ├── tta/                     # TTA-FR-*   (TikTok Mini Program)
│   └── backend/                 # BE-FR-*    (service)
├── aidlc/contracts/                   # INT-FR-*  (single source of truth)
│   ├── api/                     # OpenAPI 3.1
│   ├── events/                  # AsyncAPI / CloudEvent
│   └── CHANGELOG.md
├── packages/shared/             # generated from contracts, consumed by all
├── features/
│   └── cross-stack/             # INT-FR-*.feature (full flow)
├── tests/
│   ├── contract/                # contract tests
│   └── cross-stack/             # cross-stack e2e
├── openspec/changes/{id}/       # spec + design + task-list per change
├── providers/{tcb,aliyun}/      # cloud config
└── tools/                       # deploy_stack, contract_diff, generate_shared
```

### AI-DLC Workflow

```bash
# ① Understand
# Intent → spec-delta.md (affects + FR namespaces) → feature files

# ② Plan
# design.md (per-component sections + integration) + task-list.md (DAG)

# ③ Verify (per BDD scenario, per layer)
{{component_verify_block}}
# After all components: contract tests + cross-stack e2e

# ④ Deliver
deploy_stack --preview                          # unified stack URL
# e2e per affected component
# cross-stack e2e against unified URL
deploy_stack --env production                   # after human approval
bvt ${PRODUCTION_URL}                           # stack BVT
```

## Quality Gates

| Gate | Command | Threshold | Scope |
|------|---------|-----------|-------|
| TDD | `pytest --cov` per component | ≥80% | Per component |
| BDD | `pytest-bdd features/` per component | 100% pass | Per component |
| Contract | `pytest tests/contract/` | 100% pass | Cross-component |
| Cross-stack | `pytest tests/cross-stack/` | 100% pass | Stack |
| Security | `bandit -r apps/` | 0 vulns | Per component |
| BVT | `bvt ${URL}` | All checks pass | Stack |

## License

{{license}}
