# Plan Rules (PLN-*)

Rules for the Plan phase: design documentation, task decomposition, and test planning. Includes multi-component awareness.

## PLN-001: Design Documentation

**Severity:** MUST

**Description:** Each feature MUST have a design document covering architecture, data model, API contracts, and (where relevant) state machine before implementation begins. For multi-component features, the design doc MUST have per-component sections and an integration section.

**Valid:** Design doc in `openspec/changes/{id}/design.md` with:
- `## Component: backend` (architecture, data model, API surface referencing INT-FR-*)
- `## Component: web` (architecture, routes, data flow)
- `## Integration` (cross-component flow, contract refs, failure modes, backward compat)

**Invalid:** A single flat architecture section that doesn't distinguish per-component concerns from cross-component integration.

## PLN-002: Dependency DAG

**Severity:** MUST

**Description:** Units of work MUST be decomposed with explicit dependency relationships expressed as a directed acyclic graph (DAG), including **cross-component edges**. A task that produces or consumes a contract MUST depend on the corresponding `INT-FR-*` task.

**Valid:**
```yaml
units:
  - id: int-contract-1
    fr: INT-FR-001
    affects: [contracts]
    depends_on: []
  - id: be-unit-2
    fr: BE-FR-001
    depends_on: [int-contract-1, be-unit-1]   # cross-component edge
  - id: cross-stack-1
    fr: INT-FR-001
    depends_on: [be-unit-2, web-unit-1]
    layer: cross-stack
```

**Invalid:** Per-component task lists with no cross-component edges, or a contract change task that has no consumers depending on it.

## PLN-003: Test Plan Before Implementation

**Severity:** MUST

**Description:** Test plans for each scenario MUST be written before implementation begins, and MUST name the **test layer** (`unit`, `integration`, `e2e`, `cross-stack`, or `contract`).

**Valid:** Test cases listed in `task-list.md` (or a separate `test-plan.md`) with explicit layer per scenario:
```markdown
- BE-FR-001 @positive → layer: integration → test_login_valid_credentials
- INT-FR-001 @positive → layer: cross-stack → test_web_login_e2e_against_preview
```

**Invalid:** A test plan with no layer, or a `cross-stack` scenario without an entry in `tests/cross-stack/`.

## PLN-004: Contract Plan

**Severity:** MUST

**Description:** For each contract change, the design doc (or `contract-diff.md` placeholder) MUST identify the version impact (additive vs. breaking), the consumers affected, and the backward-compat strategy.

**Valid:** `INT-FR-001` change notes: "additive, MINOR bump; no consumer migration needed" or "breaking, MAJOR bump, migration: see contracts/CHANGELOG.md v2.0.0".

**Invalid:** A contract change in the design doc with no version impact noted.
