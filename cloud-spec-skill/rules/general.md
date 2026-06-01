# General Rules (GEN-*)

Universal coding standards applicable to all cloud-native applications.

## GEN-001: No Hardcoded Secrets

**Severity:** MUST

**Description:** No credentials, API keys, tokens, or secrets shall be hardcoded in source code.

**Valid:**
```python
api_key = os.environ.get("API_KEY")
```

**Invalid:**
```python
api_key = "sk-1234567890abcdef"
```

**Tools:** `cloud-spec lint --rule GEN-001`

## GEN-002: Error Handling Required

**Severity:** MUST

**Description:** All functions that perform I/O operations MUST have error handlers.

**Valid:**
```python
try:
    result = await db.query(sql)
except DatabaseError as e:
    logger.error(f"Query failed: {e}")
    raise
```

**Invalid:**
```python
result = await db.query(sql)  # No error handling
```

## GEN-003: Logging Required

**Severity:** MUST

**Description:** All function entry points MUST log request parameters. All exit points MUST log response status.

**Template:**
```python
def my_function(param):
    logger.info(f"Enter: param={param}")
    try:
        result = process(param)
        logger.info(f"Exit: success")
        return result
    except Exception as e:
        logger.error(f"Exit: error={e}")
        raise
```

## GEN-004: Timeout Configuration

**Severity:** MUST

**Description:** All external service calls MUST have explicit timeouts.

**Valid:**
```python
result = await client.call(timeout=30)
```

**Invalid:**
```python
result = await client.call()  # No timeout
```

## GEN-005: Resource Cleanup

**Severity:** MUST

**Description:** All resources (connections, files, handles) MUST be properly closed.

**Valid:**
```python
with open(filepath) as f:
    content = f.read()
# File automatically closed
```

**Invalid:**
```python
f = open(filepath)
content = f.read()
# Resource leak
```

## GEN-006: Idempotency

**Severity:** SHOULD

**Description:** Cloud functions SHOULD be idempotent to support retry logic.

**Implementation:**
- Use request ID for deduplication
- Implement "check-then-act" patterns with transactions
- Return same result for same input regardless of call count
