# AI-DLC Phase 1: Understand (理解)

Transform business intent into formal specification and behavior scenarios.

## Goal

Convert a business need into unambiguous, verifiable requirements before any design or code work begins.

## Flow

```
Intent (business need / user story)
  │
  ▼
SDD: Proposal (why, what, impact)
  │
  ▼
SDD: Spec Delta (EARS format — ADDED/MODIFIED/REMOVED)
  │
  ▼
BDD: Feature File (Given/When/Then scenarios)
  │
  ▼
Gate: Human review → approved or revise
```

## SDD — Spec-Driven Development

### Intent Capture

Document the what, why, and how to measure success.

```markdown
## Intent

**Title:** User Authentication
**Why:** Users need to securely access their account
**What:** Login with email + password, receive JWT token
**Success:** Login under 200ms p95, 99.9% uptime
```

### Spec Delta (EARS)

Five EARS patterns for formal requirements:

| Pattern | Syntax | When to Use |
|---------|--------|-------------|
| Ubiquitous | `The system SHALL ...` | Always-active rules |
| Event-Driven | `When {event}, the system SHALL ...` | Trigger-based behavior |
| State-Driven | `While {state}, the system SHALL ...` | Active state conditions |
| Unwanted | `If {condition}, the system SHALL ...` | Error handling |
| Optional | `Where {feature} enabled, the system SHALL ...` | Feature flags |

```markdown
## FR-001: User Authentication

**Priority:** P0

**Description (Event-Driven):**
When a user submits valid credentials, the system SHALL return a JWT token with 1-hour expiry.

**Unwanted:**
If credentials are invalid, the system SHALL return 401 with error code AUTH_001.
```

## BDD — Behavior-Driven Development

### Feature Files

```gherkin
@FR-001
Feature: User Login

  @FR-001 @positive
  Scenario: Successful login
    Given the user is on the login page
    When the user submits valid credentials
    Then the user receives a JWT token
    And the user is redirected to dashboard

  @FR-001 @negative
  Scenario: Login with invalid credentials
    Given the user is on the login page
    When the user submits invalid credentials
    Then the user sees error "Invalid credentials"
    And the user stays on the login page

  @FR-001 @edge
  Scenario: Login with empty fields
    Given the user is on the login page
    When the user submits empty email and password
    Then the user sees error "Email and password are required"
```

## Artifacts

| Artifact | Location | Purpose |
|----------|----------|---------|
| Intent | `requirements.md` | Business need capture |
| Spec delta | `openspec/changes/{id}/spec-delta.md` | Formal EARS requirements |
| BDD features | `features/{domain}/{feature}.feature` | Behavior scenarios |

## Gate

**Before advancing to Plan phase:**
- [ ] Intent documented (what, why, success criteria)
- [ ] Spec delta written with EARS format
- [ ] Each FR has ≥3 feature file scenarios (positive, negative, edge)
- [ ] Scenarios tagged with `@FR-NNN`
- [ ] Human reviewed and approved
