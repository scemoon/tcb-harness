# CloudSpec Skill

CloudSpec is a vendor-neutral specification framework for cloud-native development.

## Overview

CloudSpec provides:

- **Development Rules** — Standards for code quality, security, and specifications
- **Provider Abstraction** — Unified interface for multi-cloud support
- **Standard Workflows** — CI/CD and development pipelines
- **Templates** — Project scaffolding and documentation

## Key Concepts

### 1. Spec-First Development

All features begin with formal specification in `SPEC.md`:

```markdown
## FR-001: Feature Name

**Priority:** P0

**Description:** The system SHALL...

**Acceptance Criteria:**
- [ ] AC1: Positive case
- [ ] AC2: Negative case
```

### 2. EARS Syntax

| Pattern | Syntax | Use Case |
|---------|--------|----------|
| Ubiquitous | `The system shall...` | Universal requirements |
| Event-Driven | `When {event}, the system shall...` | Trigger-based |
| State-Driven | `While {state}, the system shall...` | Active states |
| Unwanted | `If {condition}, the system shall...` | Exceptions |
| Optional | `Where {feature} enabled, shall...` | Feature flags |

### 3. Multi-Cloud Abstraction

CloudSpec defines vendor-neutral interfaces:

```yaml
FunctionService:
  - deploy(name, code, config)
  - invoke(name, payload)
  - list()

StorageService:
  - upload(source, dest)
  - download(dest, source)
  - list(prefix)
```

Providers implement these interfaces for their specific platform.

### 4. Quality Gates

| Gate | Tool | Threshold |
|------|------|-----------|
| Spec Validation | `cloud-spec spec validate` | 100% AC coverage |
| Lint | `cloud-spec lint` | No violations |
| Tests | `cloud-spec test --coverage` | ≥ 80% |
| Security | `cloud-spec security scan` | 0 issues |

## CLI Commands

```bash
# Project initialization
cloud-spec init --name <project>

# Specification
cloud-spec spec new          # Create SPEC.md
cloud-spec spec validate     # Validate spec
cloud-spec spec diff         # Show changes

# Development
cloud-spec dev start         # Start dev server
cloud-spec dev functions     # Develop functions locally

# Deployment
cloud-spec deploy --env <env>  # Deploy to environment
cloud-spec deploy status     # Check deployment status

# Provider management
cloud-spec provider add tcb  # Add cloud provider
cloud-spec provider list     # List providers
```

## File Structure

```
project/
├── SPEC.md              # Project specification
├── design/              # Architecture docs
│   ├── frontend/
│   ├── service/
│   └── shared/
├── src/                 # Source code
│   ├── frontend/
│   ├── functions/
│   └── shared/
├── tests/               # Test suites
├── .cloud-spec/         # CloudSpec config
└── deploy/              # Deployment configs
```

## Rules Reference

### General Rules (GEN-*)

- GEN-001: No hardcoded secrets
- GEN-002: Error handling required
- GEN-003: Logging required
- GEN-004: Timeout configuration
- GEN-005: Resource cleanup
- GEN-006: Idempotency

### Security Rules (SEC-*)

- SEC-001: Secrets management
- SEC-002: Input validation
- SEC-003: SQL injection prevention
- SEC-004: CORS configuration
- SEC-005: Rate limiting
- SEC-006: HTTPS only
- SEC-007: Audit logging

### Quality Rules (QLT-*)

- QLT-001: Test coverage ≥ 80%
- QLT-002: No TODO in spec-covered code
- QLT-003: Complexity limits
- QLT-004: Naming conventions
- QLT-005: Documentation
- QLT-006: No dead code

### Spec Rules (SPC-*)

- SPC-001: Acceptance criteria required
- SPC-002: No vague terms
- SPC-003: Unique requirement IDs
- SPC-004: Priority classification
- SPC-005: State machine definition
- SPC-006: Data model consistency
- SPC-007: Error code registry

## Provider Support

| Provider | Functions | Storage | Database | Hosting |
|----------|-----------|---------|----------|---------|
| TCB | ✅ | ✅ | ✅ | ✅ |
| Aliyun | Planned | Planned | Planned | Planned |
| AWS | Planned | Planned | Planned | Planned |

## Resources

- [Full Specification](./SPEC.md)
- [Rules](./rules/)
- [Providers](./providers/)
- [Workflows](./workflows/)
- [Templates](./templates/)
