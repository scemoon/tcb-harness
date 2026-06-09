# Understand Rules (UND-*)

Rules for the Understand phase: intent capture, spec writing, and BDD feature creation.

## UND-001: Intent Documentation

**Severity:** MUST

**Description:** Before any specification or implementation, the business intent MUST be documented. Intent includes: what is being built, why, and how success is measured.

**Valid:** Intent captured in `requirements.md` or proposal before spec delta.

**Invalid:** Starting spec delta or feature files without documented intent.

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

**Description:** Each functional requirement MUST have at least 3 BDD scenarios covering positive, negative, and edge cases. Scenarios MUST be tagged with `@FR-NNN`.

**Valid:**
```gherkin
@FR-001 @positive
Scenario: Successful login
@FR-001 @negative
Scenario: Login with invalid password
@FR-001 @edge
Scenario: Login with empty fields
```

**Invalid:**
```gherkin
@FR-001
Scenario: Login  # Only one scenario, missing negative and edge
```
