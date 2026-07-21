from __future__ import annotations

from dataclasses import dataclass, field

from asyncio import Future
from typing import Mapping, TYPE_CHECKING
from textual.message import Message

import rich.repr

from tui.answer import Answer
from tui.acp import protocol
from tui.acp.encode_tool_call_id import encode_tool_call_id

if TYPE_CHECKING:
    from tui.acp.agent import Mode
    from tui.widgets.terminal_tool import ToolState


class AgentMessage(Message):
    pass


@dataclass
class ContextUpdate(AgentMessage):
    """Context token usage update from the engine."""
    used: int
    size: int


@dataclass
class Thinking(AgentMessage):
    type: str
    text: str


@dataclass
class SessionReplay(AgentMessage):
    """Marks the start/end of a session replay (loading historical messages)."""
    active: bool
    total_messages: int = 0
    visible_count: int = 0


@dataclass
class UpdateStatusLine(AgentMessage):
    status_line: str


@dataclass
class Update(AgentMessage):
    type: str
    text: str


@dataclass
class UserMessage(Message):
    type: str
    text: str


@dataclass
@rich.repr.auto
class RequestPermission(AgentMessage):
    options: list[protocol.PermissionOption]
    tool_call: protocol.ToolCallUpdatePermissionRequest
    result_future: Future[Answer]


@dataclass
class AskUser(AgentMessage):
    question: str = ""
    context: str = ""
    options: list[dict] = field(default_factory=list)
    questions: list[dict] = field(default_factory=list)
    tool_id: str = ""


@dataclass
class AwaitingUserInput(AgentMessage):
    """The agent yielded control to the user without invoking AskUser.

    Sent in response to the ``awaiting_user_input`` ACP sessionUpdate.
    The next user_input_submitted should be routed as a reply to the
    question currently on screen, not queued as a brand-new task.
    """
    prompt_preview: str = ""


@dataclass
class AIDLCState(AgentMessage):
    current_phase: str
    completed_phases: list[str]
    gate_results: dict


@dataclass
class Plan(AgentMessage):
    entries: list[protocol.PlanEntry]


@dataclass
class ToolCall(AgentMessage):
    tool_call: protocol.ToolCall

    @property
    def tool_id(self) -> str:
        """An id suitable for use as a TCSS ID."""
        return encode_tool_call_id(self.tool_call["toolCallId"])


@dataclass
class ToolCallUpdate(AgentMessage):
    tool_call: protocol.ToolCall
    update: protocol.ToolCallUpdate

    @property
    def tool_id(self) -> str:
        """An id suitable for use as a TCSS ID."""
        return encode_tool_call_id(self.tool_call["toolCallId"])


@dataclass
class AvailableCommandsUpdate(AgentMessage):
    """The agent is reporting its slash commands."""

    commands: list[protocol.AvailableCommand]


@dataclass
class CreateTerminal(AgentMessage):
    """Request a terminal in the conversation."""

    terminal_id: str
    command: str
    result_future: Future[bool]
    args: list[str] | None = None
    cwd: str | None = None
    env: Mapping[str, str] | None = None
    output_byte_limit: int | None = None


@dataclass
class KillTerminal(AgentMessage):
    """Kill a terminal process."""

    terminal_id: str


@dataclass
class GetTerminalState(AgentMessage):
    """Get the state of the terminal."""

    terminal_id: str
    result_future: Future[ToolState]


@dataclass
class ReleaseTerminal(AgentMessage):
    """Release the terminal."""

    terminal_id: str


@dataclass
class WaitForTerminalExit(AgentMessage):
    """Wait for the terminal to exit."""

    terminal_id: str
    result_future: Future[tuple[int, str | None]]


@rich.repr.auto
@dataclass
class SetModes(AgentMessage):
    """Set modes from agent."""

    current_mode: str
    modes: dict[str, Mode]


@dataclass
class ModeUpdate(AgentMessage):
    """Agent informed us about a mode change."""

    current_mode: str


@dataclass
class SubAgentStart(AgentMessage):
    """Sub-agent task started."""

    subagent_id: str
    agent_type: str
    prompt: str = ""


@dataclass
class SubAgentChunk(AgentMessage):
    """Sub-agent streaming text chunk."""

    subagent_id: str
    text: str


@dataclass
class SubAgentThinking(AgentMessage):
    """Sub-agent thinking block."""

    subagent_id: str
    text: str


@dataclass
class SubAgentEnd(AgentMessage):
    """Sub-agent task completed."""

    subagent_id: str
    agent_type: str
    status: str = "completed"
    error: str = ""
