# Security Rules (SEC-*)

## SEC-001: Secrets Management
**Severity:** MUST
Secrets MUST be retrieved from secure storage, never hardcoded or logged.

## SEC-002: Input Validation
**Severity:** MUST
All user input MUST be validated before processing: type, length, format, range.

## SEC-003: SQL Injection Prevention
**Severity:** MUST
All database queries MUST use parameterized statements.

## SEC-004: CORS Configuration
**Severity:** MUST
CORS headers MUST be explicitly configured. Wildcard origins prohibited in production.

## SEC-005: Rate Limiting
**Severity:** MUST
Public endpoints require rate limiting: 100 req/min unauthenticated, 1000 req/min authenticated.

## SEC-006: HTTPS Only
**Severity:** MUST
All production traffic MUST use HTTPS. HTTP redirects to HTTPS.

## SEC-007: Audit Logging
**Severity:** MUST
Security events MUST be logged with timestamps and actor identity.
