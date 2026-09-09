@INT-FR-001
Feature: User Authentication

  Cross-stack authentication feature covering positive, negative, edge cases, and logic consistency.

  @INT-FR-001 @positive
  Scenario: Successful login with valid credentials
    Given the user is on the login page
    And the user has valid credentials
    When the user submits email "user@test.com" and password "correct123"
    Then the user receives a JWT token
    And the user is redirected to dashboard

  @INT-FR-001 @negative
  Scenario: Login fails with wrong password
    Given the user is on the login page
    And the user has invalid credentials
    When the user submits email "user@test.com" and password "wrong"
    Then the user sees error "Invalid credentials"

  @INT-FR-001 @edge
  Scenario: Login fails with empty fields
    Given the user is on the login page
    When the user submits email "" and password ""
    Then the user sees error "Email and password are required"

  @INT-FR-001 @logic
  Scenario: Login is idempotent
    Given the user has valid credentials
    When the user submits the same credentials 3 times
    Then each login returns the same JWT token
    And no duplicate sessions are created
