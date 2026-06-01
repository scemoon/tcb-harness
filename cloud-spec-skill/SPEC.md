# CloudSpec — Cloud Development Specification

Version: 1.0.0

## Overview

CloudSpec defines a vendor-neutral specification for cloud-native application development. It provides:

- **Rules** — Development standards and quality gates
- **Providers** — Cloud provider abstraction (TCB, Aliyun, AWS, etc.)
- **Workflows** — Standard development and deployment pipelines
- **Templates** — Project scaffolding and configuration templates

## Core Principles

1. **Spec-First** — All features begin with formal specification
2. **Multi-Cloud** — Abstract cloud vendor specifics behind unified interfaces
3. **Observable** — Built-in tracing, logging, and metrics
4. **Secure-by-Default** — Security rules enforced at development time
5. **Incremental** — Small, verifiable changes with mandatory review

## Project Lifecycle

```
Init → Spec → Design → Implement → Test → Deploy → Monitor
```

| Phase | Purpose | Output |
|-------|---------|--------|
| Init | Bootstrap project | Project scaffold with config |
| Spec | Capture requirements formally | `SPEC.md` with EARS |
| Design | Architecture and data model | `design/` docs |
| Implement | Feature code | Source in `src/` |
| Test | Verification | Tests in `tests/` |
| Deploy | Release to cloud | Deployed artifacts |
| Monitor | Runtime observation | Metrics & logs |

## Specification Format

All specifications use EARS (Event-driven AgeNts Requirements Specification):

### Patterns

| Pattern | Syntax | When to Use |
|---------|--------|-------------|
| Ubiquitous | `The system shall...` | Universal requirements |
| Event-Driven | `When {event}, the system shall {response}` | Trigger-based behavior |
| State-Driven | `While {state}, the system shall...` | Active state conditions |
| Unwanted | `If {condition}, the system shall {response}` | Exception handling |
| Optional | `Where {feature} is enabled, the system shall...` | Feature flags |

### Required Fields

Every functional requirement MUST have:

- **ID**: Unique identifier (e.g., `FR-001`)
- **Priority**: P0 (critical), P1 (important), P2 (nice-to-have)
- **Description**: Clear, unambiguous statement
- **Acceptance Criteria**: At least 2 (positive + negative case)
- **No Vague Terms**: "fast", "good", "user-friendly" are prohibited

## Quality Gates

| Gate | Criteria | Tool |
|------|----------|------|
| Spec | All FRs have AC, no vague terms | `cloud-spec spec validate` |
| Code | Lint passes, no TODOs in spec-covered code | `cloud-spec lint` |
| Test | Coverage ≥ 80%, all AC testable | `cloud-spec test` |
| Security | No secrets in code, dependencies secure | `cloud-spec security scan` |
| Deploy | Smoke test passes | `cloud-spec deploy --check` |

## Project Structure

```
<project>/
├── SPEC.md                    # Project specification (EARS)
├── design/                    # Architecture documents
│   ├── frontend/             # UI/UX specs
│   ├── service/              # API contracts, data models
│   └── shared/               # Cross-cutting concerns
├── src/                      # Source code
│   ├── frontend/
│   ├── functions/            # Cloud functions
│   └── shared/
├── tests/                    # Test suites
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── .cloud-spec/
│   ├── config.yaml           # CloudSpec project config
│   ├── providers/            # Provider-specific configs
│   └── state.json            # Lifecycle state
└── deploy/                   # Deployment configs
```

## Provider Abstraction

CloudSpec defines standard interfaces that each provider implements:

### Core Interfaces

```yaml
Provider:
  name: string
  regions: string[]
  services:
    compute: ComputeService
    storage: StorageService
    database: DatabaseService
    network: NetworkService
    functions: FunctionService

ComputeService:
  - list_instances()
  - create_instance(config)
  - delete_instance(id)

StorageService:
  - upload(path, dest)
  - download(path, source)
  - list(prefix)

DatabaseService:
  - query(sql)
  - insert(table, data)
  - update(table, filters, data)
  - delete(table, filters)

FunctionService:
  - deploy(name, code, config)
  - invoke(name, payload)
  - list()

NetworkService:
  - configure_cors(rules)
  - get_domain_cert()
```

## Workflows

### Standard Deployment

```yaml
deploy:
  stages:
    - name: build
      steps:
        - lint
        - test
        - package
    - name: backend
      steps:
        - deploy_functions
        - run_migrations
    - name: frontend
      steps:
        - build
        - deploy_hosting
    - name: verify
      steps:
        - smoke_test
        - health_check
```

### Development Loop

```yaml
dev:
  commands:
    - spec diff     # Show spec changes
    - code lint     # Check code style
    - test watch   # Run tests on change
    - deploy dev    # Deploy to dev environment
```

## Templates

CloudSpec includes standard templates for:

- `template/project` — New project scaffold
- `template/spec` — `SPEC.md` template
- `template/function` — Cloud function boilerplate
- `template/frontend` — Frontend app scaffold
- `template/test` — Test file template

## CLI Commands

```bash
cloud-spec init --name <project>     # Create new project
cloud-spec spec validate             # Validate SPEC.md
cloud-spec lint                     # Check code style
cloud-spec test                     # Run test suite
cloud-spec deploy --env <env>       # Deploy to environment
cloud-spec status                   # Show project state
cloud-spec provider add <name>      # Add cloud provider
cloud-spec template list            # List available templates
```

## OpenSpec Reference

CloudSpec is inspired by [OpenSpec](https://github.com/cloudnativesandboxes/openspec) and follows similar principles of vendor-neutral, tooling-agnostic specification.
