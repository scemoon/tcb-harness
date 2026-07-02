# AI-DLC Phase 3: Verify (验证)

Execute TDD red-green-refactor per BDD scenario at the right test layer, verify all scenarios, and run cross-component contract and cross-stack gates.

## Goal

Ensure every BDD scenario is correctly implemented at the right layer, every contract is backward-compatible, and the full stack e2e flow works — before delivery.

## Flow

```
Plan + Tasks approved
  │
  ▼
For each unit in DAG order (within each affected component):
  For each BDD scenario in unit:
    │
    RED:   Write test at the right layer → confirm failure
    GREEN: Write minimum implementation → confirm pass
    REFACTOR: Clean up → confirm all tests still pass
    │
  ─────────────────────────────────
  Next unit...
  │
  ▼
After per-component units: regenerate shared types + contract tests
  aidlc/tools/generate_shared.py
  pytest tests/contract/
  aidlc/tools/contract_diff.py
  │
  ▼
After contracts: cross-stack e2e against unified preview
  pytest tests/cross-stack/
  │
  ▼
Gate: All layers green + contracts compatible + cross-stack pass
```

## Test Layers

| Layer | When | Test Location | Run Against |
|-------|------|---------------|-------------|
| `unit` | Per function / module | `apps/{comp}/tests/unit/` | Local |
| `integration` | Component + its DB / internal API | `apps/{comp}/tests/integration/` | Local container |
| `e2e` | Whole component against preview | `apps/{comp}/tests/e2e/` | Component preview URL |
| `cross-stack` | Full multi-client ↔ backend flow | `tests/cross-stack/` | Unified stack preview URL |
| `contract` | Contract shape + backward compat | `tests/contract/` | Generated `packages/shared/` |

## TDD — Red

Write one pytest test per assertion in the BDD scenario, at the layer the test plan specified.

```python
# apps/backend/tests/unit/test_auth.py
def test_login_valid_credentials():
    result = authenticate("user@example.com", "correct123")
    assert result.token is not None
    assert result.expires_in == 3600
```

```bash
pytest apps/backend/tests/unit/test_auth.py -v
# FAILED — authenticate() not defined  (RED ✓)
```

**Rule VRF-001:** Test must fail on first run.

## TDD — Green

Write the minimum code to make the test pass. No premature abstraction.

```python
# apps/backend/src/auth/login.py
def authenticate(email, password):
    if email == "user@example.com" and password == "correct123":
        return AuthResult(token="jwt_token", expires_in=3600)
    raise AuthError("Invalid credentials")
```

**Rule VRF-002:** Minimum code to pass.

## TDD — Refactor

```bash
pytest --cov --cov-fail-under=80
# All tests passed, coverage ≥80%  (REFACTOR ✓)
```

**Rule VRF-003:** Behavior must not change. All existing tests must pass before and after.

## Contract Verification (INT-001, INT-002, INT-003)

After per-component units pass and before cross-stack e2e:

```bash
# 1. Regenerate shared types from contracts
aidlc/tools/generate_shared.py
# → packages/shared/{api,events} updated

# 2. Run contract tests
pytest tests/contract/ --verbose
# → All contract scenarios pass (uses packages/shared)

# 3. Run contract compat check
aidlc/tools/contract_diff.py --base main --head HEAD
# → exit 0 = backward-compatible
# → exit 1 = breaking change detected, BLOCKED unless human-approved
```

**Rule INT-001:** Contract tests must be 100% pass.

**Rule INT-002:** Any breaking contract change (field removed, type changed, status code changed, required field added) is BLOCKED until a human approves the major version bump and a migration note is added to `aidlc/contracts/CHANGELOG.md`.

**Rule INT-003:** Shared types must be generated, not hand-written. CI runs `generate_shared` and fails the build if `packages/shared/` is out of date.

## Cross-Stack E2E (STK-001)

```bash
export STACK_URL=$(deploy_stack --preview --output url)
pytest tests/cross-stack/ --stack-url $STACK_URL --verbose
# All cross-stack scenarios pass
```

**Rule STK-001:** All `cross-stack` scenarios must pass. A single failure blocks delivery.

## BDD Scenario Verification (per layer)

```bash
# Per component
pytest-bdd apps/backend/features/ --verbose
pytest-bdd apps/web/features/ --verbose       # e.g. via cucumber-js
pytest-bdd apps/native/features/ --verbose    # or via detox/cavy
pytest-bdd apps/desktop/features/ --verbose    # or via spectron
pytest-bdd apps/wxa/features/ --verbose
pytest-bdd apps/mya/features/ --verbose
pytest-bdd apps/tta/features/ --verbose

# Cross-stack
pytest-bdd aidlc/features/cross-stack/ --verbose
```

## Quality Gates (Backpressure)

All gates enforced on every attempt to mark a unit / change complete:

```bash
# Per component
pytest apps/{component}/ --cov --cov-fail-under=80 && \
  pytest-bdd apps/{component}/features/ --verbose && \
  bandit -r apps/{component}/src/ -q && \
  ! grep -rn "TODO\|FIXME\|HACK\|XXX" apps/{component}/src/

# Cross-component
pytest tests/contract/ && \
  aidlc/tools/contract_diff.py --base main --head HEAD

# Stack
pytest tests/cross-stack/ --stack-url $STACK_URL
```

| Gate | Threshold | Rule | Scope |
|------|-----------|------|-------|
| Unit/integration coverage | ≥80% | VRF-005 | Per component |
| BDD scenarios | 100% pass | VRF-004 | Per component |
| Security | 0 vulns | VRF-005 | Per component |
| No TODOs | 0 in src/ | VRF-005 | Per component |
| Contract tests | 100% pass | INT-001 | Cross-component |
| Contract compat | backward-compat | INT-002 | Cross-component |
| Shared types | generated, in sync | INT-003 | Cross-component |
| Cross-stack e2e | 100% pass | STK-001 | Stack |

## Artifacts

| Artifact | Location |
|----------|----------|
| TDD tests (unit/integration) | `apps/{comp}/tests/{unit,integration}/test_{feature}.py` |
| TDD tests (e2e) | `apps/{comp}/tests/e2e/test_{feature}.py` |
| BDD step defs (component) | `apps/{comp}/features/steps/test_{feature}_steps.py` |
| BDD step defs (cross-stack) | `aidlc/features/cross-stack/steps/test_{feature}_steps.py` |
| Implementation | `apps/{comp}/src/{module}/{feature}.py` |
| Contract tests | `tests/contract/test_{contract}.py` |
| Cross-stack e2e | `tests/cross-stack/test_{flow}.py` |
| Contract diff | `aidlc/openspec/changes/{id}/contract-diff.md` (filled) |

## Gate

**Before advancing to Deliver phase:**
- [ ] Per-component: All BDD scenarios pass (100%), coverage ≥80%, 0 vulns, no TODO
- [ ] Contracts: `aidlc/aidlc/tools/contract_diff.py` exits 0; `tests/contract/` 100% pass; `packages/shared/` regenerated and in sync
- [ ] Cross-stack: `tests/cross-stack/` 100% pass against stack preview
- [ ] `aidlc/openspec/changes/{id}/contract-diff.md` is filled and reviewed
- [ ] All existing tests still pass
