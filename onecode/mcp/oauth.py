"""OAuth helpers for remote MCP servers (stub framework).

Provides:
  * ``OAuthStore``: load/save token bundles in ``~/.onecode/mcp-auth.json``.
  * ``OAuthFlow``: minimal abstraction; the default ``ManualOAuthFlow``
    prints an authorization URL and waits for the user to paste the
    callback URL or token.
  * ``is_oauth_required``: detect a 401 response with a
    ``WWW-Authenticate`` header so the agent can prompt the user to
    run ``cdh mcp auth <name>``.

CloudBase does not currently use this flow (it relies on static API
key environment variables), but the framework is in place so future
remote MCP servers can plug in.
"""

from __future__ import annotations

import json
import logging
import time
import webbrowser
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("onecode.mcp.oauth")

AUTH_FILENAME = "mcp-auth.json"


def _default_auth_path() -> Path:
    """Resolve the default auth file path at call time (test-friendly)."""
    return Path.home() / ".onecode" / AUTH_FILENAME


@dataclass
class TokenBundle:
    access_token: str = ""
    refresh_token: str = ""
    token_type: str = "Bearer"
    expires_at: float = 0.0
    scope: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, *, skew_seconds: int = 30) -> bool:
        if not self.expires_at:
            return False
        return time.time() >= (self.expires_at - skew_seconds)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TokenBundle":
        scalar_fields = ("access_token", "refresh_token", "token_type", "expires_at", "scope")
        kwargs = {k: data.get(k) for k in scalar_fields}
        stored_extra = data.get("extra") or {}
        extra = {**stored_extra, **{k: v for k, v in data.items() if k not in scalar_fields and k != "extra"}}
        return cls(extra=extra, **kwargs)


class OAuthStore:
    """Persistent OAuth token store at ``~/.onecode/mcp-auth.json``."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else _default_auth_path()

    def load_all(self) -> dict[str, TokenBundle]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("OAuth: failed to read %s: %s", self.path, e)
            return {}
        if not isinstance(raw, dict):
            return {}
        out: dict[str, TokenBundle] = {}
        for name, entry in raw.items():
            if isinstance(entry, dict):
                out[name] = TokenBundle.from_dict(entry)
        return out

    def get(self, name: str) -> Optional[TokenBundle]:
        return self.load_all().get(name)

    def save(self, name: str, bundle: TokenBundle) -> None:
        all_bundles = self.load_all()
        all_bundles[name] = bundle
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {n: b.to_dict() for n, b in all_bundles.items()},
                indent=2,
            )
            + "\n"
        )

    def remove(self, name: str) -> bool:
        bundles = self.load_all()
        if name not in bundles:
            return False
        del bundles[name]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({n: b.to_dict() for n, b in bundles.items()}, indent=2) + "\n"
        )
        return True

    def auth_header(self, name: str) -> Optional[dict[str, str]]:
        bundle = self.get(name)
        if not bundle or not bundle.access_token:
            return None
        if bundle.is_expired():
            logger.info("OAuth: token for '%s' is expired; run `cdh mcp auth %s`", name, name)
            return None
        return {"Authorization": f"{bundle.token_type or 'Bearer'} {bundle.access_token}"}


class OAuthFlow:
    """Base class for OAuth flows. Subclasses implement :meth:`run`."""

    def __init__(self, oauth_config: Any):
        self.config = oauth_config or {}

    def run(self, *, server_name: str) -> TokenBundle:
        raise NotImplementedError


class ManualOAuthFlow(OAuthFlow):
    """Print the authorization URL, then ask the user to paste a token.

    If the config contains ``authorizationUrl`` and ``clientId`` we open
    the browser (if available) and prompt for either the full callback
    URL or just the token.
    """

    def run(self, *, server_name: str) -> TokenBundle:
        auth_url = ""
        client_id = ""
        if isinstance(self.config, dict):
            auth_url = str(self.config.get("authorizationUrl") or "")
            client_id = str(self.config.get("clientId") or "")
            scope = str(self.config.get("scope") or "")
        else:
            scope = ""

        if auth_url:
            print(f"OAuth: open this URL to authorize '{server_name}':\n  {auth_url}")
            try:
                if client_id:
                    webbrowser.open(auth_url)
            except Exception as e:  # pragma: no cover
                logger.debug("OAuth: browser open failed: %s", e)

        print("Paste the access token (or the full callback URL) below.")
        try:
            token = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            token = ""

        # If they pasted a callback URL, try to extract the token.
        if token.startswith("http"):
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(token).query)
            for key in ("access_token", "token", "code"):
                if key in qs and qs[key]:
                    token = qs[key][0]
                    break

        bundle = TokenBundle(access_token=token, scope=scope)
        return bundle


def is_oauth_required(status_code: int, headers: Any) -> bool:
    """Return True if an HTTP response looks like an OAuth challenge."""
    if status_code != 401:
        return False
    if not headers:
        return False
    try:
        www_auth = headers.get("WWW-Authenticate") or headers.get("www-authenticate")
    except Exception:
        www_auth = None
    if not www_auth:
        return False
    return "Bearer" in str(www_auth) or "oauth" in str(www_auth).lower()


__all__ = [
    "TokenBundle",
    "OAuthStore",
    "OAuthFlow",
    "ManualOAuthFlow",
    "is_oauth_required",
    "AUTH_FILENAME",
]
