# Specification Rules (SPC-*)

Rules for writing formal requirements in SPEC.md.

## SPC-001: Acceptance Criteria Required

**Severity:** MUST

**Description:** Every functional requirement MUST have at least 2 acceptance criteria.

**Structure:**
```markdown
## FR-001: User Authentication

**Priority:** P0

**Description:** The system SHALL authenticate users using OAuth 2.0.

**Acceptance Criteria:**
- [ ] AC1: Valid credentials return JWT token with 1-hour expiry
- [ ] AC2: Invalid credentials return 401 Unauthorized
- [ ] AC3: Expired tokens return 401 with "token_expired" error code
```

**Minimum AC Count:** 2 (positive + negative/edge case)

## SPC-002: No Vague Terms

**Severity:** MUST

**Prohibited Terms:**
- "fast", "slow", "quick"
- "good", "bad", "nice", "friendly"
- "easy", "simple", "complex"
- "secure", "safe" (without definition)
- "optimized", "efficient" (without metrics)
- "user-friendly", "intuitive"
- "robust", "reliable" (without specification)

**Valid:**
```markdown
- Response time SHALL be < 200ms for 95th percentile
- Error rate SHALL be < 0.1% under normal operation
- Password SHALL be hashed using bcrypt with cost factor 12
```

## SPC-003: Unique Requirement IDs

**Severity:** MUST

**Format:** `FR-{###}` for functional requirements, `NFR-{###}` for non-functional

**Rules:**
- IDs MUST be unique within a project
- IDs MUST NOT be reused when requirements are removed
- Deprecated requirements keep their ID with "DEPRECATED" marker

## SPC-004: Priority Classification

**Severity:** MUST

| Priority | Definition | Deadline |
|----------|-----------|----------|
| P0 | Must ship with release | Blocking |
| P1 | Should ship with release | Within 2 sprints |
| P2 | Nice to have | No deadline |

**Every requirement MUST have a priority.**

## SPC-005: State Machine Definition

**Severity:** SHOULD

**Description:** For systems with significant state, define state machine explicitly.

```markdown
## State Machine: Order

**States:** PENDING → CONFIRMED → PROCESSING → SHIPPED → DELIVERED

**Transitions:**
| From | Event | To | Side Effects |
|------|-------|----|----|
| PENDING | payment_received | CONFIRMED | Send confirmation email |
| CONFIRMED | warehouse_pick | PROCESSING | - |
| PROCESSING | carrier_pickup | SHIPPED | Update tracking number |
| SHIPPED | delivery_confirmed | DELIVERED | Notify customer |

**Invalid Transitions:**
- PENDING → SHIPPED (cannot skip processing)
```

## SPC-006: Data Model Consistency

**Severity:** MUST

**Description:** Data models in spec MUST match implementation.

```markdown
## Data Model: User

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, auto-generated | Unique identifier |
| email | string | UNIQUE, NOT NULL | User email |
| password_hash | string | NOT NULL | bcrypt hash |
| created_at | timestamp | NOT NULL, default=now | Creation time |
```

## SPC-007: Error Code Registry

**Severity:** MUST

**Description:** All error codes MUST be documented.

```markdown
## Error Codes

| Code | HTTP Status | Description | Recovery |
|------|-------------|-------------|----------|
| AUTH_001 | 401 | Invalid credentials | Retry with valid creds |
| AUTH_002 | 401 | Token expired | Re-authenticate |
| AUTH_003 | 403 | Insufficient permissions | Request access |
| VAL_001 | 400 | Invalid input | Fix and retry |
```
