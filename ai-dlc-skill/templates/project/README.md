# {{name}}

{{description}}

## Quick Start

```bash
# ① Understand: write spec + feature
touch requirements.md
mkdir -p features/{{domain}}/
touch features/{{domain}}/{{feature}}.feature

# ② Plan: design + task DAG
mkdir -p openspec/changes/{{change_id}}/

# ③ Verify: TDD per scenario
pytest tests/unit/ --verbose        # RED
# implement src/{{module}}/{{feature}}.py
pytest tests/unit/ --verbose        # GREEN
pytest --cov --cov-fail-under=80    # REFACTOR
pytest-bdd features/                # ALL SCENARIOS PASS

# ④ Deliver
deploy_cloud --preview
pytest tests/e2e/
# human approval
deploy_cloud --env production
bvt ${PRODUCTION_URL}
```

## Development

### Prerequisites

- Python 3.11+
- pytest + pytest-bdd + pytest-cov
- Cloud CLI (TCB: `tcb`, Aliyun: `fun`)

### Project Structure

```
├── requirements.md       # Intent
├── features/             # BDD (.feature + steps/)
├── tests/                # TDD (unit, integration, e2e)
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── src/                  # Implementation
├── openspec/             # Spec artifacts
└── providers/            # Cloud config
```

## License

{{license}}
