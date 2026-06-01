# Quality Rules (QLT-*)

Code quality metrics and thresholds.

## QLT-001: Test Coverage

**Severity:** MUST

**Threshold:** ≥ 80% line coverage

**Measurement:**
```bash
cloud-spec test --coverage
```

**Requirements:**
- All public functions MUST have unit tests
- All cloud functions MUST have integration tests
- Critical paths MUST have 100% coverage

**Coverage Report:**
```
TOTAL   LINE    BRANCH   FUNCTION
src/    85.3%   72.1%    90.0%
  functions/   92.1%   85.0%    95.0%
  handlers/    78.5%   60.0%    85.0%
```

## QLT-002: No TODO in Spec-Covered Code

**Severity:** MUST

**Description:** No `TODO`, `FIXME`, `HACK`, or `XXX` comments allowed in code that implements specification items.

**Detection:**
```bash
grep -rn "TODO\|FIXME\|HACK\|XXX" src/
```

**Invalid:**
```python
# TODO: Implement caching
def get_user(id):
    pass
```

## QLT-003: Complexity Limits

**Severity:** SHOULD

| Metric | Warning | Error |
|--------|---------|-------|
| Cyclomatic Complexity | > 10 | > 20 |
| Function Length | > 50 lines | > 100 lines |
| Class Length | > 300 lines | > 500 lines |
| Module Length | > 500 lines | > 1000 lines |

**Measurement:**
```bash
cloud-spec lint --complexity
```

## QLT-004: Naming Conventions

**Severity:** MUST

| Type | Convention | Example |
|------|-----------|---------|
| Function | snake_case | `get_user_by_id` |
| Class | PascalCase | `UserService` |
| Constant | UPPER_SNAKE | `MAX_RETRY_COUNT` |
| Private Method | _prefix | `_internal_method` |
| File | snake_case | `user_service.py` |
| Environment | UPPER_SNAKE | `API_KEY` |

## QLT-005: Documentation

**Severity:** SHOULD

**Requirements:**
- All public functions MUST have docstrings
- All cloud functions MUST have API documentation
- Complex algorithms MUST have inline comments

**Docstring Format:**
```python
def get_user(user_id: str) -> User | None:
    """Retrieve a user by ID.

    Args:
        user_id: Unique identifier for the user

    Returns:
        User object if found, None otherwise

    Raises:
        DatabaseError: If database connection fails
    """
```

## QLT-006: No Dead Code

**Severity:** SHOULD

**Description:** Unused imports, variables, and functions should not exist.

**Detection:**
```bash
cloud-spec lint --dead-code
```
