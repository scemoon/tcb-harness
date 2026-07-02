# Understand Rules (UND-*)

## UND-001: Intent Documentation
**Severity:** MUST
**Description:** Before any specification or implementation, the business intent MUST be documented. Intent includes: what is being built, why, and how success is measured.
**Valid:** Intent captured in `requirements.md` with `affects: [...]` before spec delta.
**Invalid:** Starting spec delta or feature files without documented intent or without an `affects` declaration.

## UND-002: EARS Format
**Severity:** MUST
**Description:** All functional requirements MUST use EARS syntax (Ubiquitous, Event-Driven, State-Driven, Unwanted, or Optional).
**Valid:** `When a user submits valid credentials, the system SHALL return a JWT token.`
**Invalid:** `The login should work well and be fast.`

## UND-003: BDD Scenario Coverage
**Severity:** MUST
**Description:** Each functional requirement MUST have at least 3 BDD scenarios covering positive, negative, and edge cases. Scenarios MUST be tagged with the FR namespace prefix (`@NATIVE-`, `@DESKTOP-`, `@WEB-`, `@BE-`, `@WXA-`, `@MYA-`, `@TTA-`, or `@INT-`).
**Valid:** `@WEB-FR-001 @positive` with three scenarios per FR.
**Invalid:** One scenario per FR, or missing namespace prefix.

## UND-004: Affects Declaration
**Severity:** MUST
**Description:** Every spec delta MUST declare `affects: [native, desktop, web, backend, wxa, mya, tta, contracts]`.
**Valid:** `## Change: CHG-001 — User Login\nAffects: [web, backend, contracts]`
**Invalid:** Spec delta without an `affects` declaration.

## UND-005: Cross-Component Feature Decomposition
**Severity:** MUST
**Description:** A feature that affects ≥2 components MUST be split into: one FR per component, one or more `INT-*` FRs, and a `aidlc/features/cross-stack/*.feature` file.
**Valid:** `affects: [web, backend]` → `WEB-FR-001`, `BE-FR-001`, `INT-FR-001`, plus cross-stack feature file.
**Invalid:** A single feature file claiming to test both web and backend behavior.

## UND-006: Contract-First for Cross-Component
**Severity:** MUST
**Description:** When a feature introduces or changes a public API or event consumed by another component, a contract file MUST be added or updated in `aidlc/contracts/` before any per-component implementation.
**Valid:** `aidlc/contracts/api/auth.yaml` defines `POST /auth/login` before any code.
**Invalid:** Per-component code that depends on a contract not in `aidlc/contracts/`.
