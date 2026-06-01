import pytest
from cdha.trace.tracer import Tracer


def test_tracer_start_stop():
    t = Tracer()
    assert t.recording is False
    t.start()
    assert t.recording is True
    assert t.trace_id is not None
    t.stop()
    assert t.recording is False


def test_tracer_span():
    t = Tracer()
    t.start()
    span = t.start_span("test-span")
    assert span.name == "test-span"
    assert span.trace_id == t.trace_id
    assert span.end_time is None
    t.end_span(span)
    assert span.end_time is not None


def test_tracer_nested_spans():
    t = Tracer()
    t.start()
    parent = t.start_span("parent")
    child = t.start_span("child")
    assert child.parent_id == parent.span_id
    t.end_span(child)
    t.end_span(parent)
    assert len(t.spans) == 2


def test_tracer_no_recording():
    t = Tracer()
    span = t.start_span("no-record")
    assert span.trace_id == "no-trace"
    assert span.end_time is not None


def test_tracer_events():
    t = Tracer()
    t.start()
    span = t.start_span("event-test")
    t.add_event(span, "test-event", {"key": "value"})
    assert len(span.events) == 1
    assert span.events[0]["name"] == "test-event"
    t.end_span(span)
