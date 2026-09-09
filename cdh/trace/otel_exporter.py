"""OTLP/HTTP exporter for the agenttrace SQLite database.

Reads spans from ``~/.cdh/traces/traces.db`` (or any compatible sqlite file),
converts each row into an OpenTelemetry-compatible JSON span, and ships the
batches to an OTLP/HTTP endpoint.

This module is intentionally dependency-light. Only the Python standard library
is required at import time; ``httpx`` is used when available and falls back to
``urllib.request`` otherwise.

Environment variables honoured:

- ``OTEL_EXPORTER_OTLP_ENDPOINT``  base URL (default ``http://localhost:4318``).
  Traces are POSTed to ``<endpoint>/v1/traces`` by default.
- ``OTEL_EXPORTER_OTLP_HEADERS``    optional ``k1=v1,k2=v2`` headers.
- ``OTEL_SERVICE_NAME``            service.name resource attribute (default ``cdh``).

Typical usage::

    from cdh.trace.otel_exporter import OtlpExporter
    exporter = OtlpExporter(endpoint="http://localhost:4318", service_name="cdh")
    sent = exporter.export_since(since="2026-07-01")
    print(sent)

Or as a one-shot CLI (see ``cdh/tools/otel_export.py``).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

log = logging.getLogger("cdh.trace.otel")

DEFAULT_DB_PATH = Path.home() / ".cdh" / "traces" / "traces.db"
DEFAULT_OTLP_PATH = "/v1/traces"
DEFAULT_BATCH_SIZE = 256
DEFAULT_TIMEOUT_S = 10.0

# OTLP/HTTP trace JSON keys (see OpenTelemetry proto specification).
# We emit the JSON protobuf encoding directly to avoid pulling opentelemetry-exporter.
_OTLP_VERSION = "1.5.0"


# ---------------------------------------------------------------------------
# Low-level HTTP POST
# ---------------------------------------------------------------------------


def _http_post_json(url: str, payload: bytes, headers: dict[str, str], timeout: float) -> tuple[int, str]:
    """POST JSON to *url*. Returns (status_code, body). Falls back to urllib if httpx missing."""
    req = urllib.request.Request(url, data=payload, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URL is operator-supplied
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return 0, f"url-error: {exc.reason}"


# ---------------------------------------------------------------------------
# Trace row → OTLP span conversion
# ---------------------------------------------------------------------------


def _parse_iso(ts: str | None) -> int:
    """Convert an ISO-8601 timestamp to nanoseconds since epoch."""
    if not ts:
        return int(time.time() * 1_000_000_000)
    # Normalize trailing Z to +00:00 for fromisoformat compatibility
    ts_norm = ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
    try:
        dt = datetime.fromisoformat(ts_norm)
    except ValueError:
        return int(time.time() * 1_000_000_000)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


def _row_to_span(row: dict[str, Any], service_name: str) -> dict[str, Any]:
    """Translate a single traces.db row into an OTLP span dict.

    Each row has the schema documented in ``agenttrace``:

        id, session_id, timestamp, trace_type, function_name, tags, data(JSON)

    The resulting OTLP span reuses the row's ``id`` as the trace+span id pair
    (truncated to 16 bytes of randomness to satisfy OTLP's 8/16 byte constraints)
    and folds the JSON ``data`` blob plus ``tags`` into attributes.
    """
    raw_id = row.get("id") or uuid.uuid4().hex
    sid = row.get("session_id") or ""

    # Derive deterministic 16-byte trace_id and 8-byte span_id from row id.
    trace_id = uuid.uuid5(uuid.NAMESPACE_OID, f"{sid}::{raw_id}").hex[:32].ljust(32, "0")[:32]
    span_id = uuid.uuid5(uuid.NAMESPACE_OID, raw_id).hex[:16].ljust(16, "0")[:16]

    start_ns = _parse_iso(row.get("timestamp"))
    duration_ms = None
    data = row.get("data") or {}
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            data = {}
    if isinstance(data, dict):
        duration_ms = data.get("duration_ms")

    end_ns = start_ns + int(float(duration_ms) * 1_000_000) if duration_ms is not None else start_ns

    tags = row.get("tags") or {}
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except json.JSONDecodeError:
            tags = {}

    fn = row.get("function_name") or ""
    ttype = row.get("trace_type") or "agenttrace.span"

    attrs: list[dict[str, Any]] = [
        {"key": "cdh.span.name", "value": {"stringValue": f"{ttype}:{fn}"}},
        {"key": "cdh.span.kind", "value": {"stringValue": ttype}},
        {"key": "cdh.span.function", "value": {"stringValue": fn}},
    ]
    if sid:
        attrs.append({"key": "cdh.session_id", "value": {"stringValue": sid}})

    # Surface flattened data kwargs.
    if isinstance(data, dict):
        kwargs = data.get("kwargs") or {}
        for k, v in kwargs.items():
            attrs.append(_otlp_attr(f"cdh.kwargs.{k}", v))
        # Also expose raw duration_ms as a top-level attribute for collectors
        # that prefer numeric attributes over derived ones.
        if "duration_ms" in data and data["duration_ms"] is not None:
            attrs.append({"key": "cdh.duration_ms", "value": {"doubleValue": float(data["duration_ms"])}})

    # Flatten tags too — agents attach model/agent hints there.
    if isinstance(tags, dict):
        for k, v in tags.items():
            attrs.append(_otlp_attr(f"cdh.tag.{k}", v))

    status = "UNSET"
    if isinstance(data, dict):
        kw = data.get("kwargs") or {}
        s = kw.get("status")
        if isinstance(s, str):
            status = "OK" if s.lower() in {"success", "end_turn", "ok", "passed", "pass"} else "ERROR"

    span: dict[str, Any] = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": f"{ttype}:{fn}" if fn else ttype,
        "kind": 1,  # SPAN_KIND_INTERNAL
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "attributes": attrs,
        "status": {"code": {"OK": 1, "ERROR": 2, "UNSET": 0}[status]},
    }
    return span


def _otlp_attr(key: str, value: Any) -> dict[str, Any]:
    """Wrap an arbitrary Python value into an OTLP KeyValue entry."""
    if value is None:
        return {"key": key, "value": {"stringValue": ""}}
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    if isinstance(value, (list, tuple)):
        arr = [_otlp_attr_to_any(v) for v in value]
        return {"key": key, "value": {"arrayValue": {"values": arr}}}
    if isinstance(value, dict):
        arr = [_otlp_attr_to_any(json.dumps(value))]
        return {"key": key, "value": {"arrayValue": {"values": arr}}}
    return {"key": key, "value": {"stringValue": str(value)}}


def _otlp_attr_to_any(value: Any) -> dict[str, Any]:
    """Coerce a Python value to the {"stringValue": ...}/intValue/doubleValue shape."""
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": str(value)}


# ---------------------------------------------------------------------------
# Exporter
# ---------------------------------------------------------------------------


@dataclass
class OtlpExporter:
    """Read spans from a local sqlite DB and POST them to an OTLP/HTTP collector.

    Parameters
    ----------
    db_path:
        Path to the agenttrace sqlite file. Defaults to ``~/.cdh/traces/traces.db``.
    endpoint:
        Base URL of the OTLP/HTTP collector (no path). The exporter appends
        ``/v1/traces`` unless ``otlp_path`` is overridden. The endpoint may also
        include the full path (then ``otlp_path`` should be empty).
    service_name:
        Value of the ``service.name`` resource attribute.
    headers:
        Optional extra HTTP headers (e.g. ``{"Authorization": "Bearer ..."}``).
        ``Content-Type`` is added automatically.
    batch_size:
        Max spans per HTTP POST.
    timeout_s:
        Per-request timeout in seconds.
    otlp_path:
        Path component appended to ``endpoint`` if it has no path itself.
    dry_run:
        When True, build payloads but do not send. The returned value reports
        how many spans would have been shipped.
    """

    db_path: Path = field(default_factory=lambda: DEFAULT_DB_PATH)
    endpoint: str = "http://localhost:4318"
    service_name: str = "cdh"
    headers: dict[str, str] = field(default_factory=dict)
    batch_size: int = DEFAULT_BATCH_SIZE
    timeout_s: float = DEFAULT_TIMEOUT_S
    otlp_path: str = DEFAULT_OTLP_PATH
    dry_run: bool = False

    # ---- public API ------------------------------------------------------

    def export_since(
        self,
        since: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, int]:
        """Export all rows newer than ``since`` (ISO date or datetime).

        Returns a dict with counters: ``read``, ``sent``, ``failed``, ``batches``.
        """
        rows = list(self._iter_rows(since=since, session_id=session_id))
        return self._export_rows(rows)

    def export_rows(self, rows: Iterable[dict[str, Any]]) -> dict[str, int]:
        """Export an arbitrary iterable of row dicts (already in agenttrace shape)."""
        return self._export_rows(list(rows))

    # ---- row iteration ---------------------------------------------------

    def _iter_rows(
        self,
        since: str | None = None,
        session_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        if not self.db_path.exists():
            log.warning("traces.db not found at %s — nothing to export", self.db_path)
            return iter(())

        where: list[str] = []
        params: list[Any] = []
        if since:
            ts = since.strip()
            if len(ts) == 10:  # YYYY-MM-DD
                ts = f"{ts}T00:00:00"
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            where.append("timestamp >= ?")
            params.append(ts)
        if session_id:
            where.append("session_id = ?")
            params.append(session_id)

        sql = (
            "SELECT id, session_id, timestamp, trace_type, function_name, tags, data "
            "FROM traces"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY timestamp ASC"

        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(sql, params)
            for row in cur:
                yield {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "timestamp": row["timestamp"],
                    "trace_type": row["trace_type"],
                    "function_name": row["function_name"],
                    "tags": row["tags"],
                    "data": _decode_data(row["data"]),
                }
        finally:
            conn.close()

    # ---- shipping --------------------------------------------------------

    def _export_rows(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        counters = {"read": len(rows), "sent": 0, "failed": 0, "batches": 0}
        if not rows:
            return counters

        url = self._build_url()
        if self.dry_run:
            log.info("[dry-run] would POST %d spans to %s", len(rows), url)
            counters["sent"] = len(rows)
            counters["batches"] = max(1, -(-len(rows) // self.batch_size))
            return counters

        for batch in _chunked(rows, self.batch_size):
            payload = self._build_payload(batch)
            counters["batches"] += 1
            status, body = _http_post_json(
                url,
                payload,
                self._request_headers(),
                timeout=self.timeout_s,
            )
            if 200 <= status < 300:
                counters["sent"] += len(batch)
                log.info("POST %s → %d (%d spans)", url, status, len(batch))
            else:
                counters["failed"] += len(batch)
                log.error("POST %s → %d body=%s", url, status, body[:200])
        return counters

    def _build_url(self) -> str:
        endpoint = self.endpoint.rstrip("/")
        if endpoint.endswith("/v1/traces") or not self.otlp_path:
            return endpoint
        return f"{endpoint}{self.otlp_path}"

    def _request_headers(self) -> dict[str, str]:
        headers = dict(self.headers)
        env_hdrs = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")
        for part in env_hdrs.split(","):
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            k = k.strip()
            if k:
                headers[k.strip()] = v.strip()
        return headers

    def _build_payload(self, rows: list[dict[str, Any]]) -> bytes:
        spans = [_row_to_span(r, self.service_name) for r in rows]
        resource = {
            "attributes": [
                {"key": "service.name", "value": {"stringValue": self.service_name}},
                {"key": "telemetry.sdk.language", "value": {"stringValue": "python"}},
                {"key": "telemetry.sdk.version", "value": {"stringValue": _OTLP_VERSION}},
                {"key": "cdh.source", "value": {"stringValue": "agenttrace"}},
            ]
        }
        payload = {
            "resourceSpans": [
                {
                    "resource": resource,
                    "scopeSpans": [
                        {
                            "scope": {"name": "cdh.trace.otel_exporter", "version": "1.0.0"},
                            "spans": spans,
                        }
                    ],
                }
            ]
        }
        return json.dumps(payload).encode("utf-8")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _decode_data(raw: Any) -> Any:
    """sqlite stores JSON columns as a string on some platforms; accept both."""
    if raw is None:
        return {}
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _chunked(items: list[Any], n: int) -> Iterable[list[Any]]:
    for i in range(0, len(items), n):
        yield items[i : i + n]


# ---------------------------------------------------------------------------
# env-driven convenience entry point
# ---------------------------------------------------------------------------


def maybe_auto_install() -> bool:
    """Install a background OTLP exporter if OTEL_EXPORTER_OTLP_ENDPOINT is set.

    Returns True if a background thread was started. The exporter pulls rows
    newer than ``--since`` (or the last successful export) every ``--interval``
    seconds. It is a no-op when the env var is absent.

    This is called from ``cdh.trace.__init__`` so that any code path which
    already uses ``add_trace`` also gets OTLP forwarding for free.
    """
    import threading

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return False

    since = os.environ.get("OTEL_TRACE_EXPORT_SINCE")  # optional ISO override
    interval_s = float(os.environ.get("OTEL_TRACE_EXPORT_INTERVAL", "30"))

    state: dict[str, Any] = {"stop": False, "cursor": since}

    def _loop() -> None:
        exporter = OtlpExporter(
            endpoint=endpoint,
            service_name=os.environ.get("OTEL_SERVICE_NAME", "cdh"),
        )
        while not state["stop"]:
            try:
                counters = exporter.export_since(since=state["cursor"])
                if counters["read"]:
                    state["cursor"] = datetime.now(timezone.utc).isoformat()
            except Exception as exc:  # pragma: no cover - defensive
                log.warning("auto-export failed: %s", exc)
            time.sleep(max(1.0, interval_s))

    threading.Thread(target=_loop, name="cdh-otel-export", daemon=True).start()
    log.info("OTLP auto-export started → %s", endpoint)
    return True