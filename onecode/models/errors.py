"""Provider exception hierarchy.

These are raised by the ``onecode.models.providers.*`` modules when an upstream
LLM call fails in a way the agent engine should surface to the user as an
error event (rather than rendering the raw response body as agent text).

The engine's ``chat_stream`` loop already has::

    except Exception as e:
        yield StreamEvent.error(str(e))
        break

so simply raising any subclass of :class:`ProviderError` is enough to route
the failure through the TUI as a proper ``agent_message_chunk`` with
``sessionUpdate: "error"``.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import httpx


def retry_after_seconds(resp: "httpx.Response") -> Optional[float]:
    """Parse the ``Retry-After`` header from an HTTP response.

    Accepts both the delta-seconds form and the HTTP-date form (returning
    the delta from ``time.time()`` in either case).  Returns ``None`` if
    the header is missing or unparseable.
    """
    raw = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime
            target = parsedate_to_datetime(raw).timestamp()
            return max(0.0, target - time.time())
        except Exception:
            return None


class ProviderError(Exception):
    """Base class for all provider errors.

    Attributes:
        status_code: HTTP status code returned by the upstream, when
            applicable (``None`` for transport-level failures).
        retry_after: ``Retry-After`` header value, when the upstream
            provided one (``None`` otherwise).
        body: Raw response body, truncated to 4 KiB.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        retry_after: Optional[float] = None,
        body: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after
        self.body = (body or "")[:4096]

    def to_user_message(self) -> str:
        """Build a short, user-friendly message for the TUI."""
        head = f"Error: {self.args[0]}" if self.args else "Error: provider failure"
        if self.status_code is not None:
            head += f" (HTTP {self.status_code})"
        if self.retry_after is not None:
            head += f" — retry after {self.retry_after:.0f}s"
        return head


class RateLimitError(ProviderError):
    """HTTP 429 / upstream rate-limit signal."""


class AuthError(ProviderError):
    """HTTP 401 / 403 — invalid or missing credentials."""


class ContextLengthError(ProviderError):
    """HTTP 400 with a context-length-exceeded error from the upstream."""


class TransientProviderError(ProviderError):
    """5xx or network error — safe to retry."""
