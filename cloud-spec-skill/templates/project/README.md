# {{name}}

Project created from CloudSpec template.
{{description}}

## Quick Start

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

## Project Structure

```
{{name}}/
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
└── deploy/                    # Deployment configs
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

## Development

### Prerequisites

- Node.js 18+
- Python 3.11+
- CloudSpec CLI (`npm install -g cloud-spec`)

### Setup

```bash
# Clone repository
git clone <repo-url>
cd {{name}}

# Install dependencies
npm install
pip install -r requirements.txt

# Initialize environment
cloud-spec dev init
```

### Workflow

1. Create feature branch: `git checkout -b feature/FR-042`
2. Update `SPEC.md` with requirement details
3. Generate implementation: `cloud-spec spec generate --from FR-042`
4. Implement and test
5. Run validation: `cloud-spec lint && cloud-spec test`
6. Submit PR for review

## License

{{license}}
