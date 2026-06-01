# {{name}} - Specification

Version: {{version}}
Last Updated: {{date}}
Author: {{author}}

## Overview

{{description}}

## Goals

- [ ] Goal 1
- [ ] Goal 2
- [ ] Goal 3

## Non-Functional Requirements

### Performance

| Metric | Target | Measurement |
|--------|--------|-------------|
| Response Time (p99) | < 200ms | APM dashboard |
| Throughput | > 1000 RPS | Load test |
| Cold Start | < 3s | Function metrics |

### Availability

| Metric | Target |
|--------|--------|
| Uptime | 99.9% |
| Error Rate | < 0.1% |
| Recovery Time | < 5 min |

### Security

- All data encrypted at rest and in transit
- OAuth 2.0 authentication
- Rate limiting on all public endpoints
- Security audit logging

## Functional Requirements

### FR-001: [Requirement Title]

**Priority:** P0

**Description:**
The system SHALL...

**Acceptance Criteria:**
- [ ] AC1: [Positive case - what should work]
- [ ] AC2: [Negative case - what should not happen]
- [ ] AC3: [Edge case - boundary conditions]

**Data Model:**
```typescript
interface Example {
  id: string;
  name: string;
  created_at: Date;
}
```

### FR-002: [Next Requirement]

**Priority:** P1

**Description:**
...

## Data Models

### User

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | Unique identifier |
| email | string | UNIQUE, NOT NULL | User email |
| created_at | timestamp | NOT NULL | Creation time |

## API Endpoints

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| POST | /auth/login | User login |
| POST | /auth/logout | User logout |
| POST | /auth/refresh | Refresh token |

### Users

| Method | Path | Description |
|--------|------|-------------|
| GET | /users/:id | Get user by ID |
| PUT | /users/:id | Update user |
| DELETE | /users/:id | Delete user |

## Error Codes

| Code | HTTP | Description | Recovery |
|------|------|-------------|----------|
| AUTH_001 | 401 | Invalid credentials | Retry with valid creds |
| AUTH_002 | 401 | Token expired | Re-authenticate |
| VAL_001 | 400 | Invalid input | Fix and retry |

## State Machine

### Order Lifecycle

```
PENDING → CONFIRMED → PROCESSING → SHIPPED → DELIVERED
   ↓
 CANCELLED (from PENDING, CONFIRMED)
```

## Security Considerations

- Passwords hashed with bcrypt (cost factor 12)
- JWT tokens expire in 1 hour
- CORS restricted to known origins
- Rate limiting: 100 req/min per IP

## Appendix

### Glossary

| Term | Definition |
|------|------------|
| FR | Functional Requirement |
| NFR | Non-Functional Requirement |
| AC | Acceptance Criteria |

### References

- [CloudSpec Rules](../rules/)
- [Provider Spec](../providers/)
