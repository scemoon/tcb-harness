from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from cdh.config import CLOUD_DEV_HARNESS_DIR


class Span:
    def __init__(self, name: str, trace_id: str, parent_id: Optional[str] = None):
        self.span_id = str(uuid.uuid4())[:16]
        self.trace_id = trace_id
        self.parent_id = parent_id
        self.name = name
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.attributes: dict[str, Any] = {}
        self.events: list[dict] = []

    def finish(self):
        self.end_time = time.time()

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": round((self.end_time - self.start_time) * 1000, 2) if self.end_time else None,
            "attributes": self.attributes,
            "events": self.events,
        }

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def add_event(self, name: str, attributes: Optional[dict] = None) -> None:
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })


class Tracer:
    def __init__(self):
        self.trace_id: Optional[str] = None
        self.recording: bool = False
        self.spans: list[Span] = []
        self.stack: list[str] = []
        self.trace_dir = CLOUD_DEV_HARNESS_DIR / "traces"
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self._otlp_endpoint: Optional[str] = None

    def start(self):
        self.trace_id = str(uuid.uuid4())
        self.recording = True
        self.spans = []
        self.stack = []

    def stop(self):
        self.recording = False
        self._export()
        if self._otlp_endpoint:
            self._export_otlp()

    def set_otlp_endpoint(self, endpoint: str) -> None:
        self._otlp_endpoint = endpoint

    @contextmanager
    def span(self, name: str, attributes: Optional[dict] = None):
        span = self.start_span(name, attributes)
        try:
            yield span
        except Exception as e:
            span.add_event("exception", {"message": str(e), "type": type(e).__name__})
            raise
        finally:
            self.end_span(span)

    def start_span(self, name: str, attributes: Optional[dict] = None) -> Span:
        if not self.recording:
            span = Span(name, "no-trace")
            span.finish()
            return span
        parent_id = self.stack[-1] if self.stack else None
        span = Span(name, self.trace_id or "", parent_id)
        if attributes:
            span.attributes.update(attributes)
        self.spans.append(span)
        self.stack.append(span.span_id)
        return span

    def end_span(self, span: Span):
        span.finish()
        if self.stack and self.stack[-1] == span.span_id:
            self.stack.pop()

    def record_event(self, name: str, attributes: Optional[dict] = None, span: Optional[Span] = None) -> None:
        target = span or (self.spans[-1] if self.spans else None)
        if target:
            target.add_event(name, attributes)

    def add_event(self, span: Span, name: str, attributes: Optional[dict] = None):
        span.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })

    def _export(self):
        if not self.trace_id:
            return
        data = {
            "trace_id": self.trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "spans": [s.to_dict() for s in self.spans],
        }
        path = self.trace_dir / f"{self.trace_id}.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def _export_otlp(self):
        if not self._otlp_endpoint or not self.trace_id:
            return
        try:
            import httpx
            payload = {
                "resourceSpans": [{
                    "traceId": self.trace_id,
                    "spans": [{
                        "spanId": s.span_id,
                        "parentSpanId": s.parent_id or "",
                        "name": s.name,
                        "startTimeUnixNano": int(s.start_time * 1e9),
                        "endTimeUnixNano": int(s.end_time * 1e9) if s.end_time else 0,
                        "attributes": [{"key": k, "value": {"stringValue": str(v)}} for k, v in s.attributes.items()],
                        "events": [{"name": e["name"], "timeUnixNano": int(e["timestamp"] * 1e9)} for e in s.events],
                    } for s in self.spans],
                }]
            }
            httpx.post(self._otlp_endpoint, json=payload, timeout=5)
        except Exception:
            pass

    def view(self, trace_id: Optional[str] = None) -> list[dict]:
        if trace_id:
            path = self.trace_dir / f"{trace_id}.json"
            if path.exists():
                data = json.loads(path.read_text())
                return data.get("spans", [])
        return [s.to_dict() for s in self.spans]

    def list_traces(self) -> list[dict]:
        if not self.trace_dir.exists():
            return []
        traces = []
        for f in self.trace_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                traces.append({
                    "trace_id": data.get("trace_id"),
                    "timestamp": data.get("timestamp"),
                    "span_count": len(data.get("spans", [])),
                })
            except Exception:
                continue
        return sorted(traces, key=lambda x: x.get("timestamp", ""), reverse=True)
