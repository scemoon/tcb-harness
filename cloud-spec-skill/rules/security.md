# Security Rules (SEC-*)

Security requirements for cloud-native applications.

## SEC-001: Secrets Management

**Severity:** MUST

**Description:** All secrets MUST be retrieved from secure storage, never hardcoded or logged.

**Valid:**
```python
from cloud_spec import get_secret
api_key = get_secret("api_key")
```

**Invalid:**
```python
api_key = os.environ.get("API_KEY")  # Must use secure retrieval
log.info(f"API key: {api_key}")  # Never log secrets
```

## SEC-002: Input Validation

**Severity:** MUST

**Description:** All user input MUST be validated before processing.

**Requirements:**
- Type validation
- Length limits
- Format validation (regex for strings)
- Range validation for numbers
- Allowlist for allowed characters

**Valid:**
```python
def create_user(name: str, age: int):
    if not isinstance(name, str) or len(name) > 100:
        raise ValidationError("Invalid name")
    if not isinstance(age, int) or age < 0 or age > 150:
        raise ValidationError("Invalid age")
```

## SEC-003: SQL Injection Prevention

**Severity:** MUST

**Description:** All database queries MUST use parameterized statements.

**Valid:**
```python
db.query("SELECT * FROM users WHERE id = ?", (user_id,))
```

**Invalid:**
```python
db.query(f"SELECT * FROM users WHERE id = {user_id}")  # SQL injection
```

## SEC-004: CORS Configuration

**Severity:** MUST

**Description:** CORS headers MUST be explicitly configured. Wildcard origins are prohibited in production.

**Valid:**
```yaml
cors:
  allow_origins:
    - "https://example.com"
  allow_methods:
    - GET
    - POST
  allow_headers:
    - Authorization
```

**Invalid:**
```yaml
cors:
  allow_origins:
    - "*"  # Prohibited in production
```

## SEC-005: Rate Limiting

**Severity:** MUST

**Description:** All public endpoints MUST have rate limiting configured.

**Minimum:**
- 100 requests/minute per IP for unauthenticated
- 1000 requests/minute per token for authenticated

## SEC-006: HTTPS Only

**Severity:** MUST

**Description:** All production traffic MUST use HTTPS. HTTP redirects to HTTPS.

**Configuration:**
```yaml
security:
  force_https: true
  hsts:
    max_age: 31536000
    include_subdomains: true
```

## SEC-007: Audit Logging

**Severity:** MUST

**Description:** Security-relevant events MUST be logged with timestamps and actor identity.

**Events to log:**
- Authentication success/failure
- Authorization failures
- Data access (read/write/delete)
- Configuration changes
- Admin operations
