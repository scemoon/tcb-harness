# AI-DLC Phase 3: Verify (验证)

Execute TDD red-green-refactor per BDD scenario, then verify all scenarios.

## Goal

Ensure every BDD scenario is correctly implemented through test-first development, and that all quality gates pass before delivery.

## Flow

```
Plan + Tasks approved
  │
  ▼
For each unit (DAG order):
  For each BDD scenario in unit:
    │
    RED:   Write pytest test → confirm failure
    │
    GREEN: Write minimum implementation → confirm pass
    │
    REFACTOR: Clean up → confirm all tests still pass
    │
  ─────────────────────────────────
    │
    RUN: pytest-bdd features/ (all scenarios verify)
    RUN: Quality gates (coverage, security, no TODOs)
    │
  Next unit...
  │
  ▼
Gate: All units complete → All gates pass
```

## TDD — Red

Write one pytest test per assertion in the BDD scenario.

```python
# tests/unit/test_auth.py
def test_login_valid_credentials():
    result = authenticate("user@example.com", "correct123")
    assert result.token is not None
    assert result.expires_in == 3600
```

```bash
pytest tests/unit/test_auth.py -v
# FAILED — authenticate() not defined  (RED ✓)
```

**Rule VRF-001:** Test must fail on first run. A passing test on first run means the assertion is invalid or the behavior already exists.

## TDD — Green

Write the minimum code to make the test pass.

```python
# src/auth/login.py
def authenticate(email, password):
    if email == "user@example.com" and password == "correct123":
        return AuthResult(token="jwt_token", expires_in=3600)
    raise AuthError("Invalid credentials")
```

```bash
pytest tests/unit/test_auth.py -v
# PASSED  (GREEN ✓)
```

**Rule VRF-002:** Write the minimum code to pass. No premature abstraction, optimization, or new dependencies.

## TDD — Refactor

Clean up while keeping all tests green.

```bash
# Extract constants, simplify logic, improve naming
pytest --cov --cov-fail-under=80
# All tests passed, coverage ≥80%  (REFACTOR ✓)
```

**Rule VRF-003:** Behavior must not change during refactoring. All existing tests must pass before and after.

## BDD Scenario Verification

After all TDD cycles for a unit, run the BDD scenarios:

```bash
pytest-bdd features/ --verbose
# → All scenarios in unit pass ✓
```

## Quality Gates (Backpressure)

All gates enforced on every attempt to mark a unit complete:

```bash
pytest --cov --cov-fail-under=80 && \
pytest-bdd features/ --verbose && \
bandit -r src/ -q && \
! grep -rn "TODO\|FIXME\|HACK\|XXX" src/
```

| Gate | Threshold | Rule |
|------|-----------|------|
| Unit test coverage | ≥80% | VRF-005 |
| BDD scenarios | 100% pass | VRF-004 |
| Security | 0 vulns | VRF-005 |
| No TODOs | 0 in src/ | VRF-005 |

## Artifacts

| Artifact | Location |
|----------|----------|
| TDD tests | `tests/unit/test_{feature}.py` |
| BDD step defs | `features/steps/test_{feature}_steps.py` |
| Implementation | `src/{module}/{feature}.py` |

## Gate

**Before advancing to Deliver phase:**
- [ ] All BDD scenarios pass (pytest-bdd 100%)
- [ ] Unit test coverage ≥80%
- [ ] BDD scenario coverage ≥90%
- [ ] Security scan: 0 violations
- [ ] No TODO/FIXME/HACK in src/
- [ ] All existing tests still pass
