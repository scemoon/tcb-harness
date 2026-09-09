"""CDH Trace — centralized agenttrace integration at the ACP protocol layer.

Usage:
    from cdh.trace import add_trace
    add_trace("ACP", "agent_message_chunk", session_id=sid, tags={...})
"""

from __future__ import annotations

from pathlib import Path

from agenttrace import TraceManager

_TRACER: TraceManager | None = None


def get_tracer() -> TraceManager:
    global _TRACER
    if _TRACER is None:
        db_path = _get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _TRACER = TraceManager(db_path=str(db_path))
    return _TRACER


def get_db_path() -> Path:
    return _get_db_path()


def _get_db_path() -> Path:
    return Path.home() / ".cdh" / "traces" / "traces.db"


def add_trace(
    trace_type: str,
    func_name: str,
    session_id: str | None = None,
    duration: float | None = None,
    parent_span_id: str | None = None,
    note: str | None = None,
    tags: dict | None = None,
    model: str | None = None,
    token_count: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cached_input_tokens: int | None = None,
    status: str | None = None,
    error: str | None = None,
    tool_name: str | None = None,
    tool_kind: str | None = None,
    agent_type: str | None = None,
    cost_amount: float | None = None,
    cost_currency: str | None = None,
    lines_added: int | None = None,
    extra_data: dict | None = None,
) -> None:
    data = {}
    if model is not None:
        data["model"] = model
    if token_count is not None:
        data["token_count"] = token_count
    if input_tokens is not None:
        data["input_tokens"] = input_tokens
    if output_tokens is not None:
        data["output_tokens"] = output_tokens
    if cached_input_tokens is not None:
        data["cached_input_tokens"] = cached_input_tokens
    if status is not None:
        data["status"] = status
    if error is not None:
        data["error"] = error
    if tool_name is not None:
        data["tool_name"] = tool_name
    if tool_kind is not None:
        data["tool_kind"] = tool_kind
    if agent_type is not None:
        data["agent_type"] = agent_type
    if parent_span_id is not None:
        data["parent_span_id"] = parent_span_id
    if note is not None:
        data["note"] = note
    if cost_amount is not None:
        data["cost_amount"] = cost_amount
    if cost_currency is not None:
        data["cost_currency"] = cost_currency
    if lines_added is not None:
        data["lines_added"] = lines_added
    if extra_data:
        data.update(extra_data)

    try:
        get_tracer().add_trace(
            trace_type=trace_type,
            func_name=func_name,
            kwargs=data if data else None,
            tags=tags,
            session_id=session_id,
            duration=duration,
        )
    except Exception:
        pass
