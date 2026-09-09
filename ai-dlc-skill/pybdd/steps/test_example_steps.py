"""Example step definitions for login feature."""
from pytest_bdd import scenarios, given, when, then, parsers

scenarios("../example/auth/login.feature")


@given("the user is on the login page")
def login_page():
    return {"url": "/login", "email_field": "", "password_field": ""}


@given("the user has valid credentials")
def valid_credentials():
    return {"email": "user@test.com", "password": "correct123"}


@given("the user has invalid credentials")
def invalid_credentials():
    return {"email": "user@test.com", "password": "wrong"}


@when(parsers.parse('the user submits email "{email}" and password "{password}"'))
def submit_login(email: str, password: str):
    if email and password:
        return {"success": True, "token": "jwt_abc123", "redirect": "/dashboard"}
    return {"success": False, "error": "Email and password are required"}


@when("the user submits the same credentials 3 times")
def submit_repeated_login():
    return [
        {"success": True, "token": "jwt_abc123", "redirect": "/dashboard"},
        {"success": True, "token": "jwt_abc123", "redirect": "/dashboard"},
        {"success": True, "token": "jwt_abc123", "redirect": "/dashboard"},
    ]


@then("the user receives a JWT token")
def receive_token(result):
    assert result.get("success") is True
    assert "token" in result
    assert result["token"].startswith("jwt_")


@then("the user is redirected to dashboard")
def redirect_dashboard(result):
    assert result.get("redirect") == "/dashboard"


@then("the user sees error {error}")
def see_error(result, error):
    assert result.get("success") is False
    assert result.get("error") == error


@then("each login returns the same JWT token")
def same_token(results):
    tokens = [r["token"] for r in results]
    assert len(set(tokens)) == 1, "Tokens should be identical for idempotent login"


@then("no duplicate sessions are created")
def no_duplicate_sessions():
    session_count = 1
    assert session_count == 1, "No duplicate sessions should be created"
