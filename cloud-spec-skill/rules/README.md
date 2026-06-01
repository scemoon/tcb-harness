# CloudSpec Rules

Development standards and quality gates for cloud-native applications.

## Rule Categories

- [General](./general.md) — Universal coding standards
- [Security](./security.md) — Security requirements
- [Quality](./quality.md) — Code quality metrics
- [Spec](./spec.md) — Specification guidelines

## Quick Reference

| Rule ID | Category | Severity | Description |
|---------|----------|----------|-------------|
| GEN-001 | General | MUST | No hardcoded secrets |
| GEN-002 | General | MUST | All functions have error handlers |
| GEN-003 | General | MUST | Logging at entry/exit points |
| SEC-001 | Security | MUST | No secrets in environment variables |
| SEC-002 | Security | MUST | Input validation on all endpoints |
| QLT-001 | Quality | MUST | 80% test coverage |
| QLT-002 | Quality | MUST | No TODO/FIXME in production code |
| SPC-001 | Spec | MUST | All FRs have acceptance criteria |
| SPC-002 | Spec | MUST | No vague terms in requirements |

Run `cloud-spec lint --rule <rule-id>` to check specific rules.
