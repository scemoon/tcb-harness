"""Lightweight OTLP span generator used by ``cdh aidlc validate``.

This module is intentionally dependency-free at import time. If the
``opentelemetry-api`` package is available, we will register a tracer that
emits real OTel spans through the user's configured exporter. If not, we fall
back to writing OTLP-compatible JSON to ``OTEL_VALIDATE_STDOUT`` (when set) or
to the Python logger so downstream tooling can still pick up the data.

The validator harness imports this and calls :func:`span` around each check.
Each span carries the check name, status, duration, fr_count, bdd_count, etc.
so collectors (Honeycomb, Tempo, Jaeger) can group/filter on them.

Usage::

    from cdh.trace.otel_tracer import span, init_tracer
    init_tracer(service_name="cdh-validate", service_version="1.0.5")
    with span("ears_check", attributes={"path": "."}) as s:
        result = do_thing()
        s.set_attribute("ears.passed", result["passed"])
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

log = logging.getLogger("cdh.trace.otel_tracer")

_TRACER_NAME = "cdh.validate"
_SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "cdh")
_SERVICE_VERSION = os.environ.get("OTEL_SERVICE_VERSION", "0.0.0")

_otel_api = None
_otel_tracer = None
_use_real_api = False


def _try_load_otel_api() -> bool:
    """Attempt to import opentelemetry-api and obtain a real tracer.

    Returns True if a tracer was successfully obtained. We deliberately do NOT
    install any exporter — we leave it to the host application or env config
    (OTEL_EXPORTER_OTLP_ENDPOINT etc.) to wire one in. We just need a place to
    start/end spans that participates in any active span context.
    """
    global _otel_api, _otel_tracer, _use_real_api
    try:
        from opentelemetry import trace as otel_trace  # type: ignore
    except Exception:
        return False

    try:
        _otel_tracer = otel_trace.get_tracer(_TRACER_NAME, _SERVICE_VERSION)
    except Exception:
        return False

    _otel_api = otel_trace
    _use_real_api = True
    return True


@dataclass
class _StdoutSpan:
    """Minimal stand-in for an OTel span. Collects attributes until close."""

    name: str
    start_ns: int
    end_ns: int = 0
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "UNSET"
    status_message: str | None = None
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:32])
    parent_span_id: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_status(self, status: str, message: str | None = None) -> None:
        self.status = status
        self.status_message = message

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        self.events.append(
            {"name": name, "time_ns": time.time_ns(), "attributes": attributes or {}}
        )

    def record_exception(self, exc: BaseException) -> None:
        self.set_status("ERROR", str(exc))
        self.add_event("exception", {"exception.type": type(exc).__name__, "exception.message": str(exc)})

    def end(self) -> None:
        self.end_ns = time.time_ns()


class SpanLike:
    """Adapter that exposes the same interface whether backed by OTel API or stdout."""

    def __init__(self, real_span: Any | None, stdout_span: _StdoutSpan | None):
        self._real = real_span
        self._stdout = stdout_span

    def set_attribute(self, key: str, value: Any) -> None:
        if self._real is not None:
            try:
                self._real.set_attribute(key, value)
            except Exception:
                pass
        if self._stdout is not None:
            self._stdout.set_attribute(key, value)

    def set_status(self, status: str, message: str | None = None) -> None:
        if self._real is not None:
            try:
                from opentelemetry.trace import Status, StatusCode  # type: ignore
                code = StatusCode.OK if status == "OK" else StatusCode.ERROR if status == "ERROR" else StatusCode.UNSET
                self._real.set_status(Status(code, message))
            except Exception:
                pass
        if self._stdout is not None:
            self._stdout.set_status(status, message)

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        if self._real is not None:
            try:
                self._real.add_event(name, attributes=attributes or {})
            except Exception:
                pass
        if self._stdout is not None:
            self._stdout.add_event(name, attributes)

    def record_exception(self, exc: BaseException) -> None:
        if self._real is not None:
            try:
                self._real.record_exception(exc)
            except Exception:
                pass
        if self._stdout is not None:
            self._stdout.record_exception(exc)

    def end(self) -> None:
        if self._real is not None:
            try:
                self._real.end()
            except Exception:
                pass
        if self._stdout is not None:
            self._stdout.end()
            _maybe_emit_stdout_span(self._stdout)


def init_tracer(service_name: str | None = None, service_version: str | None = None) -> bool:
    """Initialise the tracer. Idempotent.

    Returns True if the real ``opentelemetry-api`` is being used, False if we
    fall back to stdout emission. Callers don't usually need the return value;
    it's mainly exposed for tests.
    """
    global _SERVICE_NAME, _SERVICE_VERSION
    if service_name:
        _SERVICE_NAME = service_name
    if service_version:
        _SERVICE_VERSION = service_version

    if _use_real_api and _otel_tracer is not None:
        return True
    if _try_load_otel_api():
        return True
    return False


@contextmanager
def span(
    name: str,
    *,
    attributes: dict[str, Any] | None = None,
    parent: SpanLike | None = None,
) -> Iterator[SpanLike]:
    """Open a span around a block of work.

    The returned :class:`SpanLike` adapts to whichever backend is available.
    Always call ``span.set_status("OK" / "ERROR")`` before the block exits
    for collectors to render the badge correctly.
    """
    attrs = dict(attributes or {})
    attrs.setdefault("cdh.service.name", _SERVICE_NAME)
    attrs.setdefault("cdh.service.version", _SERVICE_VERSION)

    real_cm = None
    if _use_real_api and _otel_tracer is not None:
        try:
            real_cm = _otel_tracer.start_as_current_span(name, attributes=attrs)
        except Exception:
            real_cm = None

    stdout_span = _StdoutSpan(name=name, start_ns=time.time_ns())
    stdout_span.parent_span_id = parent._stdout.span_id if parent and parent._stdout else None  # type: ignore[union-attr]
    if parent and parent._stdout:
        stdout_span.trace_id = parent._stdout.trace_id
    for k, v in attrs.items():
        stdout_span.attributes.setdefault(k, v)

    adapter = SpanLike(real_span=None, stdout_span=stdout_span)
    entered = False
    try:
        if real_cm is not None:
            try:
                real_cm.__enter__()
                entered = True
                # Replace real_span after entry so set_attribute works on it.
                current = getattr(_otel_api.trace, "get_current_span", None)
                if callable(current):
                    real_obj = current()
                    if real_obj is not None:
                        adapter._real = real_obj  # type: ignore[attr-defined]
            except Exception:
                entered = False
        yield adapter
        if adapter._stdout.status == "UNSET":
            adapter.set_status("OK")
    except BaseException as exc:
        adapter.record_exception(exc)
        adapter.set_status("ERROR", str(exc))
        raise
    finally:
        adapter.end()
        if real_cm is not None and entered:
            try:
                real_cm.__exit__(*sys.exc_info())
            except Exception:
                pass


def _maybe_emit_stdout_span(span_obj: _StdoutSpan) -> None:
    """Emit a single OTLP-compatible JSON line per span to stdout (or skip)."""
    if not _stdout_enabled():
        return

    payload = {
        "traceId": span_obj.trace_id.ljust(32, "0")[:32],
        "spanId": span_obj.span_id.ljust(16, "0")[:16],
        "parentSpanId": span_obj.parent_span_id,
        "name": span_obj.name,
        "kind": 1,
        "startTimeUnixNano": str(span_obj.start_ns),
        "endTimeUnixNano": str(span_obj.end_ns or span_obj.start_ns),
        "attributes": [
            {"key": k, "value": {"stringValue": str(v)}}
            for k, v in span_obj.attributes.items()
        ],
        "status": {"code": {"OK": 1, "ERROR": 2, "UNSET": 0}.get(span_obj.status, 0)},
        "events": span_obj.events,
        "resource": {
            "service.name": _SERVICE_NAME,
            "service.version": _SERVICE_VERSION,
            "telemetry.sdk.name": "cdh.trace.otel_tracer",
        },
    }
    try:
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def _stdout_enabled() -> bool:
    flag = os.environ.get("OTEL_VALIDATE_STDOUT", "").lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    # If no real API and no exporter endpoint is set, default-on so users see data.
    if not _use_real_api and not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return True
    return False