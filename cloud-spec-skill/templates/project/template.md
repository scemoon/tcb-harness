# {{project_name}}

## Project Structure

```
{{project_name}}/
├── SPEC.md                    # Project specification
├── design/                    # Architecture documents
│   ├── frontend/
│   ├── service/
│   └── shared/
├── src/                       # Source code
│   ├── frontend/
│   ├── functions/
│   └── shared/
├── tests/                     # Test suites
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── .cloud-spec/               # CloudSpec config
│   ├── config.yaml
│   ├── providers/
│   └── state.json
└── deploy/                   # Deployment configs
```

## Getting Started

```bash
# Install dependencies
npm install

# Start development
cloud-spec dev start

# Run tests
cloud-spec test

# Deploy
cloud-spec deploy --env production
```

## CloudSpec Commands

| Command | Description |
|---------|-------------|
| `cloud-spec dev start` | Start development server |
| `cloud-spec test` | Run test suite |
| `cloud-spec lint` | Check code style |
| `cloud-spec spec validate` | Validate SPEC.md |
| `cloud-spec deploy` | Deploy to cloud |
| `cloud-spec status` | Show project state |

## Development Workflow

1. Create feature branch: `git checkout -b feature/FR-001`
2. Update `SPEC.md` with requirement details
3. Implement and test
4. Run validation: `cloud-spec lint && cloud-spec test`
5. Submit PR for review

## License

MIT
