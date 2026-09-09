"""Tests for the OAuth stub framework."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from onecode.mcp.oauth import (
    ManualOAuthFlow,
    OAuthStore,
    TokenBundle,
    is_oauth_required,
)


@pytest.fixture
def auth_path(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home / ".onecode" / "mcp-auth.json"


class TestTokenBundle:
    def test_not_expired_when_zero(self):
        b = TokenBundle()
        assert not b.is_expired()

    def test_expired(self):
        b = TokenBundle(expires_at=1)
        assert b.is_expired()

    def test_not_expired_future(self):
        b = TokenBundle(expires_at=time.time() + 3600)
        assert not b.is_expired()

    def test_roundtrip(self):
        b = TokenBundle(
            access_token="abc",
            refresh_token="def",
            expires_at=123.0,
            scope="read",
            extra={"tenant": "x"},
        )
        d = b.to_dict()
        b2 = TokenBundle.from_dict(d)
        assert b2.access_token == "abc"
        assert b2.refresh_token == "def"
        assert b2.expires_at == 123.0
        assert b2.scope == "read"
        assert b2.extra == {"tenant": "x"}


class TestOAuthStore:
    def test_get_missing(self, auth_path):
        s = OAuthStore()
        assert s.get("nope") is None

    def test_save_and_get(self, auth_path):
        s = OAuthStore()
        s.save("srv", TokenBundle(access_token="tk", expires_at=time.time() + 3600))
        b = s.get("srv")
        assert b is not None
        assert b.access_token == "tk"

    def test_remove(self, auth_path):
        s = OAuthStore()
        s.save("srv", TokenBundle(access_token="tk"))
        assert s.remove("srv") is True
        assert s.get("srv") is None
        assert s.remove("srv") is False

    def test_auth_header(self, auth_path):
        s = OAuthStore()
        s.save("srv", TokenBundle(access_token="tk", expires_at=time.time() + 3600))
        h = s.auth_header("srv")
        assert h == {"Authorization": "Bearer tk"}

    def test_auth_header_expired(self, auth_path):
        s = OAuthStore()
        s.save("srv", TokenBundle(access_token="tk", expires_at=1))
        assert s.auth_header("srv") is None

    def test_auth_header_custom_token_type(self, auth_path):
        s = OAuthStore()
        s.save("srv", TokenBundle(access_token="tk", token_type="Token", expires_at=time.time() + 3600))
        h = s.auth_header("srv")
        assert h == {"Authorization": "Token tk"}

    def test_save_creates_parent_dirs(self, auth_path):
        # auth_path parent doesn't exist yet
        assert not auth_path.parent.exists()
        OAuthStore().save("srv", TokenBundle(access_token="x"))
        assert auth_path.exists()


class TestIsOAuthRequired:
    def test_yes_401_bearer(self):
        assert is_oauth_required(401, {"WWW-Authenticate": "Bearer realm=x"})

    def test_yes_401_oauth(self):
        assert is_oauth_required(401, {"WWW-Authenticate": "OAuth2"})

    def test_no_200(self):
        assert not is_oauth_required(200, {"WWW-Authenticate": "Bearer"})

    def test_no_401_no_header(self):
        assert not is_oauth_required(401, {})

    def test_no_403(self):
        assert not is_oauth_required(403, {"WWW-Authenticate": "Bearer"})

    def test_yes_case_insensitive_header(self):
        assert is_oauth_required(401, {"www-authenticate": "Bearer"})


class TestManualOAuthFlow:
    def test_construct_with_dict(self):
        f = ManualOAuthFlow({"authorizationUrl": "https://x", "clientId": "c"})
        assert f.config["clientId"] == "c"

    def test_construct_with_none(self):
        f = ManualOAuthFlow(None)
        assert f.config == {}

    def test_construct_with_non_dict(self):
        f = ManualOAuthFlow("string")
        assert f.config == "string"
