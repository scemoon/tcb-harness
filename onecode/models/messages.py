"""Typed message model for agent interactions.

Inspired by DeepSeek-TUI's structured message hierarchy:
- AgentMessage: base with id, role, type, timestamp
- ThinkBlock: collapsible thinking/reasoning  
- ToolCall: with name, args, lifecycle status
- ToolResult: typed by tool category
- SubAgentBlock: independent lifecycle tracking
- HistoryCell: unified renderable cell (mirrors DeepSeek-TUI's core rendering model)
- ErrorSeverity: severity taxonomy for error cells
"""

from __future__ import annotations

import sys
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


def _now() -> float:
    return time.time()


def _uid() -> str:
    return uuid.uuid4().hex[:12]


# ── Status enums ──

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    ERROR = "error"


class BlockType(str, Enum):
    TEXT = "text"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SUBAGENT = "subagent"


class LifecycleStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorSeverity(str, Enum):
    """Categorized engine/tool error severity, mirroring DeepSeek-TUI."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    CRITICAL = "critical"


class RenderMode(str, Enum):
    """Controls whether tool/thinking cells render compact 'Live' or full 'Transcript' form."""
    LIVE = "live"
    TRANSCRIPT = "transcript"


class ToolCategory(str, Enum):
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_EDIT = "file_edit"
    FILE_LIST = "file_list"
    FILE_GLOB = "file_glob"
    FILE_GREP = "file_grep"
    BASH = "bash"
    WEB_FETCH = "web_fetch"
    WEB_SEARCH = "web_search"
    TASK = "task"              # sub-agent
    TASK_MGMT = "task_mgmt"    # task/todo CRUD
    INTERACTION = "interaction"  # user approval / AskUser
    UNKNOWN = "unknown"


TOOL_CATEGORY_MAP: dict[str, ToolCategory] = {
    "Read": ToolCategory.FILE_READ,
    "Write": ToolCategory.FILE_WRITE,
    "Edit": ToolCategory.FILE_EDIT,
    "Insert": ToolCategory.FILE_EDIT,
    "UndoEdit": ToolCategory.FILE_EDIT,
    "List": ToolCategory.FILE_LIST,
    "Glob": ToolCategory.FILE_GLOB,
    "Grep": ToolCategory.FILE_GREP,
    "Bash": ToolCategory.BASH,
    "WebFetch": ToolCategory.WEB_FETCH,
    "WebSearch": ToolCategory.WEB_SEARCH,
    "Spawn": ToolCategory.TASK,
    "SendMessage": ToolCategory.INTERACTION,
    "Agent": ToolCategory.TASK,
    "ToolSearch": ToolCategory.TASK_MGMT,
    "TodoCreate": ToolCategory.TASK_MGMT,
    "TodoGet": ToolCategory.TASK_MGMT,
    "TodoList": ToolCategory.TASK_MGMT,
    "TodoUpdate": ToolCategory.TASK_MGMT,
    "TodoOutput": ToolCategory.TASK_MGMT,
    "TodoStop": ToolCategory.TASK_MGMT,
    "AskUser": ToolCategory.INTERACTION,
}


def get_tool_category(name: str) -> ToolCategory:
    return TOOL_CATEGORY_MAP.get(name, ToolCategory.UNKNOWN)


# ── Core data types ──

@dataclass
class ThinkBlock:
    """A thinking/reasoning block — collapsible in UI."""
    id: str = field(default_factory=_uid)
    content: str = ""
    timestamp: float = field(default_factory=_now)
    
    def to_dict(self) -> dict:
        return {
            "type": BlockType.THINKING.value,
            "thinking": self.content,
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> "ThinkBlock":
        return cls(content=d.get("thinking", ""))


@dataclass
class ToolCall:
    """A tool invocation with lifecycle status."""
    id: str = field(default_factory=_uid)
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    status: LifecycleStatus = LifecycleStatus.RUNNING
    timestamp: float = field(default_factory=_now)
    category: ToolCategory = ToolCategory.UNKNOWN
    caller: str = "agent"
    
    def __post_init__(self):
        if self.category == ToolCategory.UNKNOWN:
            self.category = get_tool_category(self.name)
    
    def to_dict(self) -> dict:
        return {
            "type": BlockType.TOOL_CALL.value,
            "tool_use": {
                "id": self.id,
                "name": self.name,
                "input": self.arguments,
                "caller": self.caller,
                "status": self.status.value,
                "category": self.category.value,
            }
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> "ToolCall":
        tu = d.get("tool_use", {})
        return cls(
            id=tu.get("id", ""),
            name=tu.get("name", ""),
            arguments=tu.get("input", {}),
            status=LifecycleStatus(tu.get("status", "running")),
            category=ToolCategory(tu.get("category", "unknown")),
            caller=tu.get("caller", "agent"),
        )


@dataclass
class ToolResult:
    """Result of a tool execution — typed by tool category."""
    tool_use_id: str = ""
    content: str = ""
    is_error: bool = False
    category: ToolCategory = ToolCategory.UNKNOWN
    truncated: bool = False
    full_size: int = 0
    timestamp: float = field(default_factory=_now)
    
    def to_dict(self) -> dict:
        return {
            "type": BlockType.TOOL_RESULT.value,
            "tool_result": {
                "tool_use_id": self.tool_use_id,
                "content": self.content,
                "is_error": self.is_error,
                "category": self.category.value,
                "truncated": self.truncated,
                "full_size": self.full_size,
            }
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> "ToolResult":
        tr = d.get("tool_result", {})
        return cls(
            tool_use_id=tr.get("tool_use_id", ""),
            content=tr.get("content", ""),
            is_error=tr.get("is_error", False),
            category=ToolCategory(tr.get("category", "unknown")),
            truncated=tr.get("truncated", False),
            full_size=tr.get("full_size", 0),
        )


@dataclass
class SubAgentBlock:
    """A sub-agent execution with independent lifecycle."""
    id: str = field(default_factory=_uid)
    agent_type: str = "general"
    prompt: str = ""
    status: LifecycleStatus = LifecycleStatus.PENDING
    result: str = ""
    error: str = ""
    timestamp: float = field(default_factory=_now)
    blocks: list[dict] = field(default_factory=list)  # nested blocks streamed from sub-agent
    
    def to_dict(self) -> dict:
        return {
            "type": BlockType.SUBAGENT.value,
            "subagent": {
                "id": self.id,
                "agent_type": self.agent_type,
                "prompt": self.prompt,
                "status": self.status.value,
                "result": self.result,
                "error": self.error,
                "blocks": self.blocks,
            }
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> "SubAgentBlock":
        sa = d.get("subagent", {})
        return cls(
            id=sa.get("id", ""),
            agent_type=sa.get("agent_type", "general"),
            prompt=sa.get("prompt", ""),
            status=LifecycleStatus(sa.get("status", "pending")),
            result=sa.get("result", ""),
            error=sa.get("error", ""),
            blocks=sa.get("blocks", []),
        )


@dataclass  
class TextBlock:
    """A plain text block."""
    id: str = field(default_factory=_uid)
    content: str = ""
    
    def to_dict(self) -> dict:
        return {
            "type": BlockType.TEXT.value,
            "text": self.content,
        }


# ── Stream events (ai-sdk-python style typed protocol) ──

class StreamEventType(str, Enum):
    TEXT_DELTA = "text_delta"
    THINKING = "thinking"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_ARGS = "tool_call_args"
    TOOL_CALL_COMPLETE = "tool_call_complete"
    TOOL_RESULT = "tool_result"
    ASK_USER = "ask_user"
    ERROR = "error"
    PLAN = "plan"
    SUBAGENT_START = "subagent_start"
    SUBAGENT_CHUNK = "subagent_chunk"
    SUBAGENT_THINKING = "subagent_thinking"
    SUBAGENT_END = "subagent_end"


@dataclass
class StreamEvent:
    """Typed streaming event — replaces raw XML string protocol between Engine and TUI.
    
    ai-sdk-python reference:
    - textStream equivalent: TEXT_DELTA events
    - fullStream equivalent: TOOL_CALL_START → TOOL_CALL_ARGS → TOOL_RESULT + TEXT_DELTA
    """
    type: StreamEventType
    # TEXT_DELTA fields
    text: str = ""
    # THINKING fields
    thinking: str = ""
    # TOOL_CALL_START fields
    tool_name: str = ""
    tool_id: str = ""
    tool_category: ToolCategory = ToolCategory.UNKNOWN
    # TOOL_CALL_ARGS / TOOL_CALL_COMPLETE fields
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_args_delta: str = ""
    # TOOL_RESULT fields
    result_content: str = ""
    result_is_error: bool = False
    result_category: ToolCategory = ToolCategory.UNKNOWN
    # ASK_USER fields
    ask_action: str = ""
    ask_question: str = ""
    ask_context: str = ""
    ask_options: list[dict] = field(default_factory=list)
    ask_questions: list[dict] = field(default_factory=list)
    ask_action_type: str = ""
    ask_path: str = ""
    ask_command: str = ""
    # ERROR fields
    error_message: str = ""
    # PLAN fields
    plan_entries: list[dict] = field(default_factory=list)
    # SUBAGENT fields
    subagent_id: str = ""
    subagent_type: str = ""
    subagent_text: str = ""
    subagent_prompt: str = ""
    subagent_thinking_text: str = ""
    subagent_status: str = ""
    subagent_error: str = ""

    @classmethod
    def text_delta(cls, text: str) -> "StreamEvent":
        return cls(type=StreamEventType.TEXT_DELTA, text=text)

    @classmethod
    def thinking(cls, thought: str) -> "StreamEvent":
        return cls(type=StreamEventType.THINKING, thinking=thought)

    @classmethod
    def tool_call_start(cls, name: str, call_id: str) -> "StreamEvent":
        return cls(
            type=StreamEventType.TOOL_CALL_START,
            tool_name=name,
            tool_id=call_id,
            tool_category=get_tool_category(name),
        )

    @classmethod
    def tool_call_args_delta(cls, call_id: str, name: str, args_delta: str) -> "StreamEvent":
        return cls(
            type=StreamEventType.TOOL_CALL_ARGS,
            tool_id=call_id,
            tool_name=name,
            tool_category=get_tool_category(name),
            tool_args_delta=args_delta,
        )

    @classmethod
    def tool_call_complete(cls, call_id: str, name: str, arguments: dict[str, Any]) -> "StreamEvent":
        return cls(
            type=StreamEventType.TOOL_CALL_COMPLETE,
            tool_id=call_id,
            tool_name=name,
            tool_category=get_tool_category(name),
            tool_args=arguments,
        )

    @classmethod
    def tool_result(cls, call_id: str, content: str, is_error: bool = False,
                    category: ToolCategory = ToolCategory.UNKNOWN) -> "StreamEvent":
        return cls(
            type=StreamEventType.TOOL_RESULT,
            tool_id=call_id,
            result_content=content,
            result_is_error=is_error,
            result_category=category,
        )

    @classmethod
    def ask_user(cls, call_id: str, action: str, question: str,
                 context: str = "", action_type: str = "",
                 path: str = "", command: str = "",
                 options: list[dict] | None = None,
                 questions: list[dict] | None = None) -> "StreamEvent":
        return cls(
            type=StreamEventType.ASK_USER,
            tool_id=call_id,
            ask_action=action,
            ask_question=question,
            ask_context=context,
            ask_options=options or [],
            ask_questions=questions or [],
            ask_action_type=action_type,
            ask_path=path,
            ask_command=command,
        )

    @classmethod
    def error(cls, message: str) -> "StreamEvent":
        return cls(type=StreamEventType.ERROR, error_message=message)

    @classmethod
    def plan(cls, entries: list[dict]) -> "StreamEvent":
        """Create a plan update event.

        Args:
            entries: List of plan entries, each with:
                - content: str - The task description
                - status: str - "pending" | "in_progress" | "completed"
                - priority: str - "high" | "medium" | "low"
        """
        return cls(type=StreamEventType.PLAN, plan_entries=entries)

    @classmethod
    def subagent_start(cls, agent_type: str, call_id: str, prompt: str = "") -> "StreamEvent":
        return cls(
            type=StreamEventType.SUBAGENT_START,
            subagent_id=call_id,
            subagent_type=agent_type,
            subagent_prompt=prompt,
        )

    @classmethod
    def subagent_chunk(cls, call_id: str, text: str) -> "StreamEvent":
        return cls(
            type=StreamEventType.SUBAGENT_CHUNK,
            subagent_id=call_id,
            subagent_text=text,
        )

    @classmethod
    def subagent_thinking(cls, call_id: str, text: str) -> "StreamEvent":
        return cls(
            type=StreamEventType.SUBAGENT_THINKING,
            subagent_id=call_id,
            subagent_thinking_text=text,
        )

    @classmethod
    def subagent_end(
        cls, call_id: str, agent_type: str = "", status: str = "completed", error: str = ""
    ) -> "StreamEvent":
        return cls(
            type=StreamEventType.SUBAGENT_END,
            subagent_id=call_id,
            subagent_type=agent_type,
            subagent_status=status,
            subagent_error=error,
        )

    @staticmethod
    def is_text(event: "StreamEvent") -> bool:
        return event.type in (StreamEventType.TEXT_DELTA, StreamEventType.THINKING)

    def to_block_dict(self) -> dict:
        """Convert this stream event to a block dict for TUI rendering."""
        if self.type == StreamEventType.TEXT_DELTA:
            return TextBlock(content=self.text).to_dict()
        elif self.type == StreamEventType.THINKING:
            return ThinkBlock(content=self.thinking).to_dict()
        elif self.type == StreamEventType.TOOL_CALL_START:
            return {
                "type": "tool_use_start",
                "tool_use": {
                    "name": self.tool_name,
                    "id": self.tool_id,
                    "category": self.tool_category.value,
                }
            }
        elif self.type == StreamEventType.TOOL_CALL_COMPLETE:
            return ToolCall(
                id=self.tool_id,
                name=self.tool_name,
                arguments=self.tool_args,
                status=LifecycleStatus.COMPLETE,
                category=self.tool_category,
            ).to_dict()
        elif self.type == StreamEventType.TOOL_RESULT:
            return ToolResult(
                tool_use_id=self.tool_id,
                content=self.result_content,
                is_error=self.result_is_error,
                category=self.result_category,
            ).to_dict()
        elif self.type == StreamEventType.ASK_USER:
            result = {
                "type": "ask_user",
                "ask_user": {
                    "tool_use_id": self.tool_id,
                    "action": self.ask_action,
                    "category": self.tool_category.value,
                    "question": self.ask_question,
                    "context": self.ask_context,
                    "options": self.ask_options,
                    "questions": self.ask_questions,
                    "action_type": self.ask_action_type,
                    "path": self.ask_path,
                    "command": self.ask_command,
                }
            }
            return result
        elif self.type == StreamEventType.ERROR:
            return TextBlock(content=f"[Error: {self.error_message}]").to_dict()
        elif self.type == StreamEventType.SUBAGENT_START:
            return {
                "type": "subagent_start",
                "subagent": {
                    "id": self.subagent_id,
                    "agent_type": self.subagent_type,
                    "status": "running",
                }
            }
        elif self.type == StreamEventType.SUBAGENT_CHUNK:
            return {
                "type": "subagent_chunk",
                "subagent": {
                    "id": self.subagent_id,
                    "text": self.subagent_text,
                }
            }
        elif self.type == StreamEventType.SUBAGENT_END:
            return {
                "type": "subagent_end",
                "subagent": {
                    "id": self.subagent_id,
                    "status": "completed",
                }
            }
        return TextBlock(content="").to_dict()


# ── Unified block type ──

if sys.version_info >= (3, 10):
    AgentBlock = ThinkBlock | ToolCall | ToolResult | SubAgentBlock | TextBlock
else:
    from typing import Union
    AgentBlock = Union[ThinkBlock, ToolCall, ToolResult, SubAgentBlock, TextBlock]
StreamEventOrStr = "StreamEvent | str"  # Marker type for documentation


def block_from_dict(d: dict) -> AgentBlock:
    """Parse a raw dict into a typed AgentBlock."""
    btype = d.get("type", "")
    if btype == "thinking":
        return ThinkBlock.from_dict(d)
    elif btype == "tool_use" or btype == "tool_call":
        if "tool_use" not in d:
            d = {"type": "tool_call", "tool_use": d.get("tool_use", {})}
        return ToolCall.from_dict(d)
    elif btype == "tool_result":
        return ToolResult.from_dict(d)
    elif btype == "subagent":
        return SubAgentBlock.from_dict(d)
    elif btype == "text":
        return TextBlock(content=d.get("text", ""))
    elif btype == "tool_use_start":
        tu = d.get("tool_use", {})
        return ToolCall(
            id=tu.get("id", ""),
            name=tu.get("name", ""),
            status=LifecycleStatus.RUNNING,
            category=get_tool_category(tu.get("name", "")),
        )
    return TextBlock(content=str(d))


# ── AgentMessage ──

@dataclass
class AgentMessage:
    """A turn-level message with typed content blocks."""
    id: str = field(default_factory=_uid)
    role: MessageRole = MessageRole.ASSISTANT
    blocks: list[AgentBlock] = field(default_factory=list)
    timestamp: float = field(default_factory=_now)
    
    def add_text(self, text: str) -> None:
        self.blocks.append(TextBlock(content=text))
    
    def add_thinking(self, content: str) -> None:
        self.blocks.append(ThinkBlock(content=content))
    
    def add_tool_call(self, tc: ToolCall) -> None:
        self.blocks.append(tc)
    
    def add_tool_result(self, tr: ToolResult) -> None:
        self.blocks.append(tr)
    
    def add_subagent(self, sa: SubAgentBlock) -> None:
        self.blocks.append(sa)
    
    @property
    def text_blocks(self) -> list[TextBlock]:
        return [b for b in self.blocks if isinstance(b, TextBlock)]
    
    @property
    def think_blocks(self) -> list[ThinkBlock]:
        return [b for b in self.blocks if isinstance(b, ThinkBlock)]
    
    @property
    def tool_calls(self) -> list[ToolCall]:
        return [b for b in self.blocks if isinstance(b, ToolCall)]
    
    @property
    def tool_results(self) -> list[ToolResult]:
        return [b for b in self.blocks if isinstance(b, ToolResult)]
    
    @property
    def subagents(self) -> list[SubAgentBlock]:
        return [b for b in self.blocks if isinstance(b, SubAgentBlock)]
    
    @property
    def text(self) -> str:
        return "\n".join(b.content for b in self.text_blocks)
    
    @property
    def thinking(self) -> str:
        return "\n\n".join(b.content for b in self.think_blocks)
    
    def get_tool_result(self, tool_use_id: str) -> Optional[ToolResult]:
        for tr in self.tool_results:
            if tr.tool_use_id == tool_use_id:
                return tr
        return None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role.value,
            "blocks": [b.to_dict() for b in self.blocks],
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> "AgentMessage":
        return cls(
            id=d.get("id", ""),
            role=MessageRole(d.get("role", "assistant")),
            blocks=[block_from_dict(b) for b in d.get("blocks", [])],
            timestamp=d.get("timestamp", 0),
        )


# ── Conversation ──

@dataclass
class Conversation:
    """Full conversation history with typed messages."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    messages: list[AgentMessage] = field(default_factory=list)
    created_at: float = field(default_factory=_now)
    
    def add_message(self, msg: AgentMessage) -> None:
        self.messages.append(msg)
    
    def new_message(self, role: MessageRole = MessageRole.ASSISTANT) -> AgentMessage:
        msg = AgentMessage(role=role)
        self.messages.append(msg)
        return msg
    
    def get_last_assistant(self) -> Optional[AgentMessage]:
        for m in reversed(self.messages):
            if m.role == MessageRole.ASSISTANT:
                return m
        return None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> "Conversation":
        return cls(
            id=d.get("id", ""),
            messages=[AgentMessage.from_dict(m) for m in d.get("messages", [])],
            created_at=d.get("created_at", 0),
        )
