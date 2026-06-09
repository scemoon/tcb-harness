# Verify Rules (VRF-*)

Rules for the Verify phase: TDD cycles, BDD verification, and quality gates. These are enforced as **backpressure** — the agent cannot stop or advance until all pass.

## VRF-001: TDD Red Phase

**Severity:** MUST

**Description:** Before writing implementation code, write a pytest test that asserts the expected behavior. The test MUST fail on first run, confirming the assertion is valid and the behavior does not yet exist.

**Valid:**
```bash
pytest tests/ -k test_login
# FAILED — authenticate not defined  ✓
```

**Invalid:** Test passes on first run (assertion is invalid or behavior already exists).

## VRF-002: TDD Green Phase

**Severity:** MUST

**Description:** Write the minimum amount of code needed to make the test pass. Do not add features, optimizations, or abstractions beyond what the test requires.

**Valid:** Only the code path required by the test is implemented.

**Invalid:** Adding database, caching, or logging before the test requires it.

## VRF-003: TDD Refactor Phase

**Severity:** MUST

**Description:** After tests pass, refactor to improve code quality while keeping ALL existing tests green. No behavior changes during refactoring.

**Valid:**
```bash
pytest --cov --cov-fail-under=80
# All tests passed, coverage same or better  ✓
```

## VRF-004: BDD Scenario Pass Gate

**Severity:** MUST

**Description:** ALL BDD scenarios for a feature MUST pass before the feature can be marked complete. A single failing scenario blocks completion.

**Verification:**
```bash
pytest-bdd features/ --verbose
# All scenarios passed  ✓
```

## VRF-005: Quality Gate Backpressure

**Severity:** MUST

**Description:** On every attempt to complete a unit, ALL quality gates MUST pass simultaneously. The agent cannot stop, advance, or declare work complete until all gates pass.

**Enforcement:**
```bash
pytest --cov --cov-fail-under=80 && \
pytest-bdd features/ --verbose && \
bandit -r src/ -q && \
! grep -rn "TODO\|FIXME\|HACK\|XXX" src/
```

| Gate | Threshold |
|------|-----------|
| Unit test coverage | ≥80% |
| BDD scenarios | 100% pass |
| Security | 0 violations |
| No TODOs | 0 in src/ |
