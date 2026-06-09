# Spec-Driven Development (SDD)

SDD is the specification methodology used in Understand and Plan phases.

## Role in AI-DLC

| Phase | SDD Usage |
|-------|-----------|
| Understand | Intent capture, spec delta with EARS |
| Plan | Design doc, task decomposition with DAG |
| Deliver | Artifact archiving |

## Core Artifacts

### Proposal (Why/What/Impact)

```markdown
## Change: CHG-001 — User Authentication

**Why:** Users need to securely access their accounts
**What:** Email + password login with JWT session
**Impact:** New auth module, changes to user model
```

### Spec Delta (EARS)

```markdown
## ADDED Requirements

### FR-001: User Authentication

**Priority:** P0

**Description (Event-Driven):**
When a user submits valid credentials, the system SHALL authenticate and return a JWT token.

**Acceptance Criteria:**
- AC1: Valid credentials return JWT with 1-hour expiry
- AC2: Invalid credentials return 401
- AC3: Empty fields return validation error
```

### Design Doc

```markdown
## Data Model: User

| Field | Type | Constraints |
|-------|------|-------------|
| id | UUID | PK |
| email | string | UNIQUE, NOT NULL |

## API: POST /auth/login

Request: `{email, password}`  Response: `{token, expires_in}`
```

### Task List with DAG

```yaml
units:
  - id: unit-1
    name: Database schema
    depends_on: []
  - id: unit-2
    name: Login endpoint
    depends_on: [unit-1]
```

## EARS Patterns

| Pattern | Syntax | Example |
|---------|--------|---------|
| Ubiquitous | `The system SHALL ...` | Always-hash passwords with bcrypt |
| Event-Driven | `When {event}, SHALL ...` | When user logs in, create session |
| State-Driven | `While {state}, SHALL ...` | While session active, auto-refresh |
| Unwanted | `If {condition}, SHALL ...` | If DB fails, return 503 |
| Optional | `Where {feature}, SHALL ...` | Where SSO enabled, skip password |

## Tools

- Spec format: Markdown with EARS
- Design: Markdown + Mermaid diagrams
- Tasks: YAML with DAG structure
