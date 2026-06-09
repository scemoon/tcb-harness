# Plan Rules (PLN-*)

Rules for the Plan phase: design documentation, task decomposition, and test planning.

## PLN-001: Design Documentation

**Severity:** MUST

**Description:** Each feature MUST have a design document covering architecture, data model, API contracts, and (where relevant) state machine before implementation begins.

**Valid:** Design doc in `openspec/changes/{id}/design.md` with architecture, models, API, and state machine.

**Invalid:** Starting implementation without a design doc.

## PLN-002: Dependency DAG

**Severity:** MUST

**Description:** Units of work MUST be decomposed with explicit dependency relationships expressed as a directed acyclic graph (DAG).

**Valid:**
```yaml
units:
  - id: unit-1
    depends_on: []
  - id: unit-2
    depends_on: [unit-1]
```

**Invalid:** Implicit or undocumented dependencies between work units.

## PLN-003: Test Plan Before Implementation

**Severity:** MUST

**Description:** Test plans for each scenario MUST be written before implementation begins. This includes: what test cases exist, what assertions are made, and what edge cases are covered.

**Valid:** Test cases listed in task-list.md or a separate test-plan.md before any implementation code.
