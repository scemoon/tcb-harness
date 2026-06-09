# Verify Rules (VRF-*)

Rules for the Verify phase: TDD cycles, BDD verification, and quality gates. These are enforced as **backpressure** — the agent cannot stop or advance until all pass. Multi-component scope is per-component.

## VRF-001: TDD Red Phase

**Severity:** MUST

**Description:** Before writing implementation code, write a pytest test that asserts the expected behavior at the right layer (`unit` / `integration` / `e2e` / `cross-stack`). The test MUST fail on first run.

**Valid:**
```bash
pytest apps/backend/tests/unit/test_auth.py -k test_login
# FAILED — authenticate not defined  ✓
```

**Invalid:** Test passes on first run.

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
pytest apps/{component}/ --cov --cov-fail-under=80
# All tests passed, coverage same or better  ✓
```

## VRF-004: BDD Scenario Pass Gate

**Severity:** MUST

**Description:** ALL BDD scenarios for a feature MUST pass at every required layer (`unit` / `integration` / `e2e` / `cross-stack`) before the feature can be marked complete. A single failing scenario blocks completion.

**Verification:**
```bash
pytest-bdd apps/{component}/features/ --verbose
pytest-bdd features/cross-stack/ --verbose   # if cross-component
# All scenarios passed  ✓
```

## VRF-005: Quality Gate Backpressure (per component)

**Severity:** MUST

**Description:** On every attempt to complete a unit, ALL quality gates MUST pass simultaneously for that component. The agent cannot stop, advance, or declare work complete until all gates pass.

**Enforcement (per component):**
```bash
pytest apps/{component}/ --cov --cov-fail-under=80 && \
  pytest-bdd apps/{component}/features/ --verbose && \
  bandit -r apps/{component}/src/ -q && \
  ! grep -rn "TODO\|FIXME\|HACK\|XXX" apps/{component}/src/
```

| Gate | Threshold |
|------|-----------|
| Unit test coverage | ≥80% |
| BDD scenarios | 100% pass |
| Security | 0 violations |
| No TODOs | 0 in src/ |

## VRF-006: Test Layer Correctness

**Severity:** MUST

**Description:** Each BDD scenario MUST be tested at the layer the test plan specified. A `cross-stack` scenario MUST NOT be implemented as a `unit` test, and a `unit` scenario MUST NOT require a running database.

**Valid:** A `cross-stack` scenario lives in `tests/cross-stack/` and runs against a deployed `STACK_URL`; a `unit` scenario lives in `apps/{comp}/tests/unit/` and uses mocks/fakes.

**Invalid:** A `cross-stack` scenario implemented only as a mocked `unit` test, or a `unit` test that boots a real database.
