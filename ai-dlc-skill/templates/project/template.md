# {{project_name}}

AI-DLC project following Understand → Plan → Verify → Deliver lifecycle.

## Project Structure

```
{{project_name}}/
├── requirements.md              # Intent + spec
├── openspec/
│   └── changes/{id}/
│       ├── spec-delta.md        # EARS requirements
│       ├── design.md            # Architecture + data model
│       └── task-list.md         # DAG task breakdown
├── features/                    # BDD .feature files
│   ├── steps/                   # pytest-bdd step defs
│   └── {domain}/{feature}.feature
├── tests/                       # TDD tests
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── src/                         # Implementation
├── providers/                   # Cloud platform config
└── pyproject.toml
```

## AI-DLC Workflow

```bash
# ① Understand
# Intent → spec-delta.md (EARS) → feature files (BDD)

# ② Plan
# design.md + task-list.md (DAG)

# ③ Verify (per BDD scenario)
pytest tests/unit/ --verbose       # RED: fail
# implement src/{module}/{feature}.py
pytest tests/unit/ --verbose       # GREEN: pass
pytest --cov --cov-fail-under=80   # REFACTOR: still green
pytest-bdd features/               # All scenarios pass

# ④ Deliver
deploy_cloud --preview             # Dynamic URL
pytest tests/e2e/
deploy_cloud --env production      # After human approval
bvt ${PRODUCTION_URL}
```

## Quality Gates

| Gate | Command | Threshold |
|------|---------|-----------|
| TDD | `pytest --cov` | ≥80% |
| BDD | `pytest-bdd features/` | 100% pass |
| Security | `bandit -r src/` | 0 vulns |
| BVT | `bvt ${URL}` | All checks pass |

## License

{{license}}
