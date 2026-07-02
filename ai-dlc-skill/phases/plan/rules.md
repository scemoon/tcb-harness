# Plan Rules (PLN-*)

## PLN-001: Design Documentation
**Severity:** MUST
**Description:** Each feature MUST have a design document covering architecture, data model, API contracts, and state machine. For multi-component features, MUST have per-component sections and an integration section.
**Valid:** `aidlc/openspec/changes/{id}/design.md` with `## Component: backend`, `## Component: web`, `## Integration`.
**Invalid:** A single flat architecture section with no per-component concerns.

## PLN-002: Dependency DAG
**Severity:** MUST
**Description:** Units MUST be decomposed with explicit dependency DAG including cross-component edges. A task producing/consuming a contract MUST depend on the corresponding `INT-FR-*` task.
**Valid:** `depends_on: [int-contract-1, be-unit-1]` for a web task consuming the contract.
**Invalid:** Per-component task lists with no cross-component edges.

## PLN-003: Test Plan Before Implementation
**Severity:** MUST
**Description:** Test plans for each scenario MUST be written before implementation and MUST name the test layer (`unit`, `integration`, `e2e`, `cross-stack`, `contract`).
**Valid:** `BE-FR-001 @positive → layer: integration → test_login_valid_credentials`
**Invalid:** A test plan with no layer designation.

## PLN-004: Contract Plan
**Severity:** MUST
**Description:** For each contract change, the design doc MUST identify version impact (additive vs. breaking), consumers affected, and backward-compat strategy.
**Valid:** `INT-FR-001 change: additive, MINOR bump; no consumer migration needed`
**Invalid:** Contract change with no version impact noted.
