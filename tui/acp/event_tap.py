from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from tui.acp.protocol import SessionUpdate

logger = logging.getLogger("tui.acp.event_tap")


@dataclass
class AcpTapMetrics:
    tool_call_count: int = 0
    tool_call_updates: int = 0
    user_message_chunks: int = 0
    agent_message_chunks: int = 0
    thought_chunks: int = 0
    subagent_starts: int = 0
    ask_user_count: int = 0
    turn_count: int = 0
    tool_errors: int = 0
    verification_passed: int = 0
    verification_failed: int = 0


class AcpEventTap:
    """Passively sniff ACP session/update stream.

    Requires zero cooperation from the engine — it simply observes
    the existing ACP protocol messages that every engine already sends.
    Works with any engine: onecode, opencode, claude, cursor, etc.
    """

    def __init__(self) -> None:
        self.metrics = AcpTapMetrics()
        self._session_id: str = ""
        self._collecting: bool = False

    def start_collecting(self, session_id: str) -> None:
        self._session_id = session_id
        self.metrics = AcpTapMetrics()
        self._collecting = True

    def stop_collecting(self) -> dict[str, Any]:
        self._collecting = False
        return self._derive_session_metrics()

    def on_session_update(self, update: SessionUpdate) -> None:
        """Called for every session/update message. Thread-safe call from ACP dispatch."""
        if not self._collecting:
            return

        discriminator = update.get("sessionUpdate", "")

        if discriminator == "tool_call":
            self.metrics.tool_call_count += 1
        elif discriminator == "tool_call_update":
            self.metrics.tool_call_updates += 1
        elif discriminator == "user_message_chunk":
            self.metrics.user_message_chunks += 1
        elif discriminator == "agent_message_chunk":
            self.metrics.agent_message_chunks += 1
        elif discriminator == "agent_thought_chunk":
            self.metrics.thought_chunks += 1
        elif discriminator == "subagent_start":
            self.metrics.subagent_starts += 1
        elif discriminator == "ask_user":
            self.metrics.ask_user_count += 1

    def on_session_event(self, event: dict) -> None:
        """Handle structured session/event notification (onecode enhancement).

        Provides more precise metrics than passive session/update sniffing.
        """
        if not self._collecting:
            return

        event_type = event.get("type", "")

        if event_type == "tool_executed":
            self.metrics.tool_call_count += 1
        elif event_type == "tool_result":
            if event.get("is_error"):
                self.metrics.tool_errors += 1
        elif event_type == "session_ended":
            self.metrics.turn_count = event.get("turn_count", 0)
        elif event_type == "verification_passed":
            self.metrics.verification_passed += 1
        elif event_type == "verification_failed":
            self.metrics.verification_failed += 1

    def _derive_session_metrics(self) -> dict[str, Any]:
        tool_efficiency = 1.0
        if self.metrics.tool_call_count > 0:
            tool_efficiency = min(1.0, 10.0 / max(self.metrics.tool_call_count, 1))

        return {
            "session_id": self._session_id,
            "tool_call_count": self.metrics.tool_call_count,
            "tool_errors": self.metrics.tool_errors,
            "tool_efficiency": tool_efficiency,
            "turn_count": self.metrics.turn_count,
            "has_subagents": self.metrics.subagent_starts > 0,
            "verification_passed": self.metrics.verification_passed,
            "verification_failed": self.metrics.verification_failed,
        }