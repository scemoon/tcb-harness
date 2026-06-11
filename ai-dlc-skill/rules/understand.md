# Understand Rules (UND-*)

Rules for the Understand phase: intent capture, spec writing, and BDD feature creation. Includes multi-component awareness.

## UND-001: Intent Documentation

**Severity:** MUST

**Description:** Before any specification or implementation, the business intent MUST be documented. Intent includes: what is being built, why, and how success is measured.

**Valid:** Intent captured in `requirements.md` (or proposal) with `affects: [...]` declaring which components the feature touches, before spec delta.

**Invalid:** Starting spec delta or feature files without documented intent or without an `affects` declaration.

## UND-002: EARS Format

**Severity:** MUST

**Description:** All functional requirements MUST use EARS syntax (Ubiquitous, Event-Driven, State-Driven, Unwanted, or Optional).

**Valid:**
```markdown
When a user submits valid credentials, the system SHALL return a JWT token.
```

**Invalid:**
```markdown
The login should work well and be fast.  # No EARS, vague terms
```

## UND-003: BDD Scenario Coverage

**Severity:** MUST

**Description:** Each functional requirement MUST have at least 3 BDD scenarios covering positive, negative, and edge cases. Scenarios MUST be tagged with the FR namespace prefix (`@NATIVE-`, `@DESKTOP-`, `@WEB-`, `@BE-`, `@WXA-`, `@MYA-`, `@TTA-`, or `@INT-`).

**Valid:**
```gherkin
@WEB-FR-001 @positive
Scenario: Web login happy path
@WEB-FR-001 @negative
Scenario: Web login with wrong password
@WEB-FR-001 @edge
Scenario: Web login with empty fields
```

**Invalid:**
```gherkin
@FR-001
Scenario: Login  # No namespace prefix, missing negative and edge
```

## UND-004: Affects Declaration

**Severity:** MUST

**Description:** Every spec delta MUST declare which components it affects via an `affects: [native, desktop, web, backend, wxa, mya, tta, contracts]` field. The declaration drives which FR namespaces are used, which lifecycle paths run, and which deploy steps are triggered.

**Valid:**
```markdown
## Change: CHG-001 — User Login
Affects: [web, backend, contracts]
```

**Invalid:** Spec delta without an `affects` declaration.

## UND-005: Cross-Component Feature Decomposition

**Severity:** MUST

**Description:** A feature that affects ≥2 components MUST be split into:
- one FR per affected component in that component's namespace (`NATIVE-*` / `DESKTOP-*` / `WEB-*` / `BE-*` / `WXA-*` / `MYA-*` / `TTA-*`)
- one or more `INT-*` FRs describing the contract
- a `features/cross-stack/*.feature` file with end-to-end scenarios for the `INT-*` FR

**Valid:** `affects: [web, backend]` → `WEB-FR-001`, `BE-FR-001`, `INT-FR-001`, plus `features/cross-stack/auth/login.feature` with ≥3 scenarios.

**Invalid:** A single feature file claiming to test both web and backend behavior, or per-component FRs without an `INT-*` covering their boundary.

## UND-006: Contract-First for Cross-Component

**Severity:** MUST

**Description:** When a feature introduces or changes a public API or event consumed by another component, a contract file MUST be added or updated in `contracts/` (OpenAPI for REST, AsyncAPI for events, GraphQL schema for GraphQL) before any per-component implementation begins.

**Valid:** `contracts/api/auth.yaml` defines `POST /auth/login` request/response, and `INT-FR-001` references it.

**Invalid:** Per-component code that depends on a contract that does not exist in `contracts/`.
