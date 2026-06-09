# AI-DLC Phase 1: Understand (理解)

Transform business intent into formal specification and behavior scenarios, scoped to the right FR namespace.

## Goal

Convert a business need into unambiguous, verifiable requirements before any design or code work begins. For multi-component features, capture the **cross-component boundary** in addition to per-component behavior.

## Flow

```
Intent (business need / user story)
  │
  ▼
Identify scope: which components does this touch?
  │
  ▼
SDD: Proposal (why, what, impact, affects: [app|web|backend|contracts])
  │
  ▼
SDD: Spec Delta (EARS format — ADDED/MODIFIED/REMOVED, FR namespaces)
  │
  ▼
BDD: Feature Files
  - features/{component}/{domain}/{feature}.feature   (per-component)
  - features/cross-stack/{domain}/{feature}.feature   (full flow, if applies)
  │
  ▼
Gate: Human review → approved or revise
```

## Scope Identification

Before writing the spec, declare which components the feature affects. This determines the FR namespaces and which lifecycle paths run.

| Affects | Example | FRs |
|---------|---------|-----|
| `[backend]` only | Internal API | `BE-FR-NNN` |
| `[web, backend]` | Login UI + API | `WEB-FR-NNN`, `BE-FR-NNN`, `INT-FR-NNN` |
| `[app, web, backend]` | Full feature | `APP-FR-NNN`, `WEB-FR-NNN`, `BE-FR-NNN`, `INT-FR-NNN` |
| `[contracts]` | Schema-only change | `INT-FR-NNN` only |

`affects: [contracts]` is reserved for **pure contract changes** (e.g. add a new field shared by all components). It still requires Plan + Verify.

## SDD — Spec-Driven Development

### Intent Capture

```markdown
## Intent

**Title:** {{title}}
**Affects:** [{{components}}]
**Why:** {{why}}
**What:** {{what}}
**Success:** {{success_criteria}}
```

### Spec Delta (EARS) with Namespace

```markdown
## Change: CHG-{{id}} — {{title}}

**Affects:** [{{components}}]
**Contracts touched:** {{list or "none"}}

## ADDED Requirements

### INT-FR-{{nnn}}: {{contract_title}}
(only if affects contracts or ≥2 components)

**Description (Event-Driven):**
When a {{event}}, the system SHALL {{behavior}} on the contract boundary.

### BE-FR-{{nnn}}: {{backend_title}}
**Description (Event-Driven):**
When {{event}}, the backend SHALL {{behavior}}.

### WEB-FR-{{nnn}}: {{web_title}}
**Description (Event-Driven):**
When {{event}}, the web client SHALL {{behavior}}.
```

### EARS Patterns

| Pattern | Syntax | When to Use |
|---------|--------|-------------|
| Ubiquitous | `The system SHALL ...` | Always-active rules |
| Event-Driven | `When {event}, the system SHALL ...` | Trigger-based behavior |
| State-Driven | `While {state}, the system SHALL ...` | Active state conditions |
| Unwanted | `If {condition}, the system SHALL ...` | Error handling |
| Optional | `Where {feature} enabled, the system SHALL ...` | Feature flags |

## BDD — Behavior-Driven Development

### Per-Component Feature Files

```gherkin
@WEB-FR-001
Feature: Web Login UI

  @WEB-FR-001 @positive
  Scenario: User logs in successfully
    Given the web app is on the login page
    When the user submits valid credentials
    Then the user is redirected to dashboard
    And the user receives a JWT in storage

  @WEB-FR-001 @negative
  Scenario: Invalid credentials show error
    ...

  @WEB-FR-001 @edge
  Scenario: Empty fields show validation
    ...
```

### Cross-Stack Feature File (mandatory for `affects ≥ 2 components`)

```gherkin
@INT-FR-001
Feature: Cross-stack login flow

  @INT-FR-001 @positive
  Scenario: Web login reaches backend and stores token
    Given the web app is on the login page
    When the user submits valid credentials
    Then the backend POST /auth/login returns 200 with JWT
    And the web app stores the token
    And the user is redirected to dashboard

  @INT-FR-001 @negative
  Scenario: Backend rejects invalid credentials with 401
    ...

  @INT-FR-001 @edge
  Scenario: Backend timeout surfaces a user-friendly error
    ...
```

## Artifacts

| Artifact | Location | Purpose |
|----------|----------|---------|
| Intent | `requirements.md` | Business need + `affects` |
| Spec delta | `openspec/changes/{id}/spec-delta.md` | EARS, FR namespaces, `affects` |
| Per-component BDD | `apps/{component}/features/{domain}/{feature}.feature` | Component behavior |
| Cross-stack BDD | `features/cross-stack/{domain}/{feature}.feature` | End-to-end flow |
| Contract spec | `contracts/{api,events}/{name}.{yaml,graphql}` | INT-FR-NNN source of truth |

## Gate

**Before advancing to Plan phase:**
- [ ] `affects: [...]` declared in spec-delta
- [ ] Spec delta uses EARS format
- [ ] Per-component FRs: each tagged `@FR-{PREFIX}-NNN`, ≥3 scenarios (positive/negative/edge)
- [ ] If `affects` includes ≥2 components: at least one `INT-FR-NNN` and a `features/cross-stack/*.feature` with ≥3 scenarios
- [ ] If `affects` includes contracts: contract file present in `contracts/`
- [ ] Human reviewed and approved
