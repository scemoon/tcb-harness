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

Each FR must have at least 3 scenarios:

| Type | Purpose | Example Tag |
|------|---------|-------------|
| Positive | Happy path, should work | `@FR-001 @positive` |
| Negative | Error handling, should fail | `@FR-001 @negative` |
| Edge case | Boundary conditions | `@FR-001 @edge` |

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
```

## pytest-bdd Integration

```python
# features/steps/test_login_steps.py
from pytest_bdd import scenarios, given, when, then, parsers

scenarios("../auth/login.feature")

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
pytest-bdd features/ --verbose

# Run scenarios for a specific FR
pytest-bdd features/ -k "FR-001"

# BDD scenario coverage
pytest-bdd features/ --coverage
```
