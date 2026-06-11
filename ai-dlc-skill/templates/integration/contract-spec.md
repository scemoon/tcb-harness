# Contract Spec — {{contract_name}}

> Source of truth for cross-component contract. Implements `INT-FR-{{int_fr_id}}`.
> Consumers: {{consumers}}
> Producers: {{producers}}

## Kind

- [ ] REST API (OpenAPI 3.1) — `contracts/api/{{name}}.yaml`
- [ ] AsyncAPI event — `contracts/events/{{name}}.yaml`
- [ ] GraphQL schema — `contracts/api/{{name}}.graphql`

## Versioning

- Current version: `{{version}}`  (SemVer: MAJOR.MINOR.PATCH)
- MAJOR: breaking (field removed, type changed, status code changed)
- MINOR: additive (new optional field, new endpoint)
- PATCH: doc / example only

> Any MAJOR bump requires human approval (INT-002) and a migration note in
> `contracts/CHANGELOG.md`.

## Change

| Field | Value |
|-------|-------|
| Change ID | `{{change_id}}` |
| Affects | {{affects: [native, desktop, web, backend, wxa, mya, tta]}} |
| Direction | {{provider → consumer / bidirectional}} |
| Breaking? | {{yes / no}} |
| Migration | {{link to migration doc or "none"}} |

## FR Mapping

| FR | Component | Role |
|----|-----------|------|
| `INT-FR-{{int_fr_id}}` | contracts | Contract definition |
| `{{provider_namespace}}-FR-{{provider_fr}}` | {{provider}} | Provider behavior |
| `{{consumer_namespace}}-FR-{{consumer_fr}}` | {{consumer}} | Consumer behavior |

## Contract Test Mapping

- `tests/contract/test_{{contract_name}}.py`
- Scenarios: @INT-FR-{{int_fr_id}} @positive / @negative / @edge

## See Also

- `contracts/CHANGELOG.md` — version history
- `openspec/changes/{{change_id}}/contract-diff.md` — auto-generated diff
