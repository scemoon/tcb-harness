# Behavior-Driven Development (BDD)

BDD is the behavior specification and verification methodology used in Understand and Verify phases.

## Role in AI-DLC

| Phase | BDD Usage |
|-------|-----------|
| Understand | Feature files with Given/When/Then scenarios |
| Verify | pytest-bdd scenario verification against implementation |
| Deliver | BDD e2e tests against preview URL |

## Gherkin Syntax

| Keyword | Purpose |
|---------|---------|
| `Feature` | High-level feature description |
| `Scenario` | Single behavior example |
| `Given` | Precondition / starting state |
| `When` | Action performed |
| `Then` | Expected outcome |
| `And` / `But` | Additional clause |
| `Background` | Steps before every scenario |
| `Scenario Outline` | Template with Examples table |
| `@tag` | Metadata (FR ID, type) |

## Scenario Coverage Rules

Each FR must have at least 4 scenarios:

| Type | Coverage Dimension | Purpose | Example Tag |
|------|-------------------|---------|-------------|
| Positive | 处理逻辑 | Happy path, should work | `@FR-001 @positive` |
| Negative | 异常处理 | Error handling, should fail | `@FR-001 @negative` |
| Edge case | 边界情况 | Boundary conditions | `@FR-001 @edge` |
| Logic | 逻辑一致性 | Idempotency, state consistency | `@FR-001 @logic` |

### @logic 场景说明

`@logic` 场景验证操作的逻辑一致性和理性：

- **幂等性**: 重复执行结果一致
- **状态一致性**: 操作后状态转换正确
- **因果合理性**: 操作结果与原因合理对应
- **数据完整性**: 操作不破坏数据完整性

## Example

```gherkin
@FR-001
Feature: User Login

  @FR-001 @positive
  Scenario: Successful login
    Given the user is on the login page
    When the user submits email "user@test.com" and password "correct123"
    Then the user receives a JWT token
    And the user is redirected to dashboard

  @FR-001 @negative
  Scenario: Login with wrong password
    Given the user is on the login page
    When the user submits email "user@test.com" and password "wrong"
    Then the user sees error "Invalid credentials"

  @FR-001 @edge
  Scenario: Login with empty fields
    Given the user is on the login page
    When the user submits email "" and password ""
    Then the user sees error "Email and password are required"

  @FR-001 @logic
  Scenario: Login is idempotent
    Given the user has valid credentials
    When the user submits the same credentials 3 times
    Then each login returns the same JWT token
    And no duplicate sessions are created
```

## pytest-bdd Integration

```python
# aidlc/features/steps/test_login_steps.py
from pytest_bdd import scenarios, given, when, then, parsers

scenarios("../cross-stack/auth/login.feature")

@given("the user is on the login page")
def login_page():
    return LoginPage()

@when(parsers.parse("the user submits email {email} and password {password}"))
def submit(email, password):
    ...
```

## Verification

```bash
# Run all BDD scenarios
pytest aidlc/features/ --verbose

# Run scenarios for a specific FR
pytest aidlc/features/ -k "FR-001"

# Generate step definitions
pytest-bdd generate aidlc/features/cross-stack/auth/login.feature

# BDD scenario coverage
pytest aidlc/features/ --cov --cov-fail-under=80
```

## Feature File Locations

| Type | Location |
|------|----------|
| Cross-stack contracts | `aidlc/features/cross-stack/` |
| Web component | `apps/web/features/` |
| Backend component | `apps/backend/features/` |
