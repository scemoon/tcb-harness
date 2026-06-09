# AI-DLC Skill — Requirements

## Overview

This skill implements the AI-Driven Development Lifecycle with four phases: Understand (SDD+BDD), Plan (SDD+TDD), Verify (BDD+TDD), Deliver (SDD+Cloud).

## Functional Requirements

### FR-001: Understand Phase

**Priority:** P0

**When** a developer starts a new feature,
**the system SHALL** capture intent, produce an OpenSpec spec delta in EARS format, and write BDD feature files with Given/When/Then scenarios.

**Acceptance Criteria:**
- Intent documented before implementation
- Spec delta uses EARS (Ubiquitous/Event-Driven/State-Driven/Unwanted/Optional)
- Each FR tagged with `@FR-NNN` in `.feature` files
- Minimum 3 scenarios per FR: positive, negative, edge
- Scenarios reviewed and approved by human

### FR-002: Plan Phase

**Priority:** P0

**When** spec and feature files are approved,
**the system SHALL** produce a technical design, decompose work into units with dependency DAG, and write test plans.

**Acceptance Criteria:**
- Design doc includes architecture, data model, API contract, state machine
- Tasks have explicit dependencies (DAG)
- Test plan written per scenario before implementation

### FR-003: Verify Phase

**Priority:** P0

**When** design and tasks are approved,
**the system SHALL** execute TDD red-green-refactor per BDD scenario and verify all scenarios pass.

**Acceptance Criteria:**
- Tests written before implementation (Red)
- Tests fail initially (confirming assertion works)
- Minimum implementation written to pass (Green)
- Implementation refactored, all tests still pass
- All BDD scenarios pass via pytest-bdd
- Quality gates enforced: coverage ≥80%, scenarios ≥90%, 0 vulns, no TODO

### FR-004: Deliver Phase

**Priority:** P1

**When** all scenarios pass quality gates,
**the system SHALL** deploy to preview, run BDD e2e tests, and after human approval deploy to production with BVT verification.

**Acceptance Criteria:**
- Preview URL dynamically resolved per platform (TCB/Aliyun)
- BDD e2e tests run against preview URL
- Production deploy requires human approval
- BVT (Build Verification Test) passes after production deploy
- Failed BVT triggers rollback
