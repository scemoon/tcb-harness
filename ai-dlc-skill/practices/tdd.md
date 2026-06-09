# Test-Driven Development (TDD)

TDD is the implementation methodology used in the Verify phase.

## Role in AI-DLC

| Phase | TDD Usage |
|-------|-----------|
| Plan | Test plan written per scenario |
| Verify | Red → Green → Refactor per BDD scenario |

## Core Cycle

```
For each BDD scenario:
  ┌──────────────────┐
  │  1. RED          │  Write pytest test → confirm FAILURE
  │  2. GREEN        │  Write minimum implementation → confirm PASS
  │  3. REFACTOR     │  Clean up → all tests still PASS
  └──────────────────┘
```

## RED Phase

Write a test that asserts the expected behavior. It must fail on first run.

```python
# tests/unit/test_auth.py
def test_login_valid_credentials():
    result = authenticate("user@test.com", "correct123")
    assert result.token is not None
    assert result.expires_in == 3600
```

```bash
pytest tests/unit/test_auth.py -v
# FAILED — authenticate not defined  ✓ (RED confirmed)
```

**Rules:**
- Test written before implementation code
- Test must fail (confirms the assertion is valid)
- Test covers only this scenario's behavior

## GREEN Phase

Write the minimum code to make the test pass.

```python
# src/auth/login.py
def authenticate(email, password):
    if email == "user@test.com" and password == "correct123":
        return AuthResult(token="jwt_placeholder", expires_in=3600)
    raise AuthError("Invalid credentials")
```

```bash
pytest tests/unit/test_auth.py -v
# PASSED  ✓ (GREEN)
```

**Rules:**
- Minimum code to pass — no extras
- No premature optimization
- No new dependencies unless required

## REFACTOR Phase

Improve code quality without changing behavior.

```bash
pytest --cov --cov-fail-under=80
# All tests passed, coverage ≥80%  ✓ (REFACTOR)
```

**Rules:**
- Keep all tests green
- No behavior changes
- Repeat for next scenario

## Naming Convention

| Artifact | Location | Example |
|----------|----------|---------|
| Tests | `tests/unit/test_{feature}.py` | `tests/unit/test_auth.py` |
| Step defs | `features/steps/test_{feature}_steps.py` | `features/steps/test_login_steps.py` |
| Source | `src/{module}/{feature}.py` | `src/auth/login.py` |

## Quality Gates

```bash
pytest --cov --cov-fail-under=80
pytest-bdd features/ --verbose
bandit -r src/ -q
```
