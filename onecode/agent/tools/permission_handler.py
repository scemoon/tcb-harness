from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from onecode.agent.tools.permissions import PermissionResult


@dataclass(frozen=True)
class PermissionDecision:
    result: PermissionResult
    reason: str = ""


PermissionHandler = Callable[[str, str, dict], PermissionDecision]
"""Signature: (tool_name: str, question: str, tool_input: dict) -> PermissionDecision"""


class InteractivePermissionHandler:
    """Handles ASK-level permission requests from tools.

    Clawd-Code pattern: when a tool's check_permissions() returns ASK,
    the handler determines whether to allow or deny based on user input.

    The default implementation denies all ASK requests (fail-safe).
    Callers can provide a custom handler to prompt the user interactively.
    """

    def __init__(self, handler: Optional[PermissionHandler] = None) -> None:
        self._handler = handler

    def handle(
        self,
        tool_name: str,
        tool_input: dict,
        question: str = "",
    ) -> PermissionDecision:
        if self._handler is not None:
            return self._handler(tool_name, question, tool_input)
        return PermissionDecision(
            result=PermissionResult.DENY,
            reason="No interactive permission handler configured",
        )

    def __repr__(self) -> str:
        return f"InteractivePermissionHandler(handler={'set' if self._handler else 'None'})"
