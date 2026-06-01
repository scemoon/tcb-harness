# CloudSpec

Vendor-neutral cloud development specification framework.

## Overview

CloudSpec defines standards for building portable cloud-native applications across multiple cloud providers. It provides development rules, provider abstraction, standard workflows, and templates.

## Quick Start

```bash
# Create new project from template
cloud-spec init --name my-app --template project

# Validate specification
cloud-spec spec validate

# Start development
cloud-spec dev start

# Deploy
cloud-spec deploy --env production
```

## Core Concepts

### 1. Development Rules

Standards organized by category:

| Category | File | Coverage |
|----------|------|----------|
| General | `rules/general.md` | Coding practices |
| Security | `rules/security.md` | Security requirements |
| Quality | `rules/quality.md` | Test coverage, naming |
| Specification | `rules/spec.md` | EARS syntax, AC format |

**Quick Rules Reference:**

```
GEN-001: No hardcoded secrets
GEN-002: Error handling required
GEN-003: Logging at entry/exit
SEC-001: Secrets via secure storage
SEC-002: Input validation on all endpoints
QLT-001: ≥80% test coverage
SPC-001: All FRs need acceptance criteria
SPC-002: No vague terms (fast, good, nice...)
```

### 2. Provider Abstraction

Multi-cloud support via unified interfaces:

| Provider | Functions | Storage | Database | Hosting |
|----------|-----------|---------|----------|---------|
| TCB | ✅ | ✅ | ✅ | ✅ |
| Aliyun | Planned | - | - | - |
| AWS | Planned | - | - | - |

**Interface Examples:**

```yaml
FunctionService:
  deploy(name, code, runtime, config)
  invoke(name, payload, sync)
  list(region)

StorageService:
  upload(source, dest)
  download(dest, source)
  list(prefix)
```

### 3. EARS Specification

Event-driven AgeNts Requirements Specification:

```markdown
## FR-001: User Authentication

**Priority:** P0

**Description:**
When user submits credentials, the system SHALL authenticate via OAuth 2.0.

**Acceptance Criteria:**
- [ ] AC1: Valid credentials return JWT (1hr expiry)
- [ ] AC2: Invalid credentials return 401
```

**EARS Patterns:**

| Pattern | Syntax | Use |
|---------|--------|-----|
| Ubiquitous | `The system shall...` | Always active |
| Event-Driven | `When {event}, shall...` | Trigger-based |
| State-Driven | `While {state}, shall...` | Active states |
| Unwanted | `If {condition}, shall...` | Exceptions |
| Optional | `Where {feature} enabled, shall...` | Feature flags |

### 4. Standard Workflows

**Deployment Pipeline:**

```
validate → build → test → deploy_backend → deploy_frontend → smoke_test
```

**Development Loop:**

```bash
cloud-spec dev start      # Hot reload dev server
cloud-spec spec diff      # Show spec changes
cloud-spec lint           # Check code style
cloud-spec test --watch   # Run tests on change
```

## Project Structure

```
<project>/
├── SPEC.md                    # Project specification
├── design/                    # Architecture docs
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
│   └── providers/
└── deploy/                   # Deployment configs
```

## Quality Gates

| Gate | Command | Threshold |
|------|---------|-----------|
| Spec | `cloud-spec spec validate` | 100% AC coverage |
| Lint | `cloud-spec lint` | 0 violations |
| Test | `cloud-spec test --coverage` | ≥80% |
| Security | `cloud-spec security scan` | 0 issues |

## File Reference

| Path | Description |
|------|-------------|
| `SPEC.md` | CloudSpec framework specification |
| `SKILL.md` | Skill loader entry point |
| `rules/` | Development standards |
| `providers/` | Cloud vendor implementations |
| `workflows/` | CI/CD pipeline definitions |
| `templates/` | Project and spec templates |

## License

MIT
