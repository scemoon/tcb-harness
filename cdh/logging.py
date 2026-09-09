"""Structured JSON logging for CDH observability.

Provides a third observability signal (Logs) alongside Traces and Metrics.
Logs are written as NDJSON (newline-delimited JSON) to ~/.cdh/logs/app.jsonl
and can be exported in OTLP format.

Usage::

    from cdh.logging import get_logger, LogLevel
    log = get_logger("cdh.validate")
    log.info("Running EARS checks", fr_id="WEB-FR-001", passed=True)
    log.error("Validation failed", error="missing_frontmatter")
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

__all__ = ["get_logger", "LogLevel", "JSONLogHandler", "export_logs"]

DEFAULT_LOG_DIR = Path.home() / ".cdh" / "logs"
DEFAULT_LOG_FILE = "app.jsonl"
_OTEL_VERSION = "1.5.0"


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"

    @property
    def otel_severity(self) -> int:
        """Convert to OTLP severity number."""
        return {
            "DEBUG": 5,
            "INFO": 9,
            "WARN": 13,
            "ERROR": 17,
            "FATAL": 21,
        }[self.value]

    @property
    def python_level(self) -> int:
        return {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARN": logging.WARNING,
            "ERROR": logging.ERROR,
            "FATAL": logging.CRITICAL,
        }[self.value]


_loggers: dict[str, "JSONLogger"] = {}
_log_dir_initialized = False


def _ensure_log_dir() -> Path:
    global _log_dir_initialized
    log_dir = Path(os.environ.get("CDH_LOG_DIR", str(DEFAULT_LOG_DIR)))
    log_dir.mkdir(parents=True, exist_ok=True)
    _log_dir_initialized = True
    return log_dir


class JSONLogHandler(logging.Handler):
    """logging.Handler that emits NDJSON records to a file."""

    def __init__(self, log_file: Path | None = None, rotation_hours: int = 24):
        super().__init__()
        self._log_file = log_file or (_ensure_log_dir() / DEFAULT_LOG_FILE)
        self._rotation_hours = rotation_hours
        self._last_rotation = time.time()
        self._lock = __import__("threading").Lock()

    def _maybe_rotate(self) -> None:
        now = time.time()
        if now - self._last_rotation > self._rotation_hours * 3600:
            self._rotate()

    def _rotate(self) -> None:
        if not self._log_file.exists():
            return
        ts = datetime.fromtimestamp(self._last_rotation, tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
        rotated = self._log_file.parent / f"{self._log_file.stem}.{ts}.jsonl"
        try:
            self._log_file.rename(rotated)
        except OSError:
            pass
        self._last_rotation = time.time()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._maybe_rotate()
            log_entry = self._format_entry(record)
            with self._lock:
                with open(self._log_file, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(log_entry, default=str) + "\n")
        except Exception:
            pass

    def _format_entry(self, record: logging.LogRecord) -> dict[str, Any]:
        ts_ns = int(record.created * 1e9)
        trace_id = getattr(record, "cdh_trace_id", "") or ""
        span_id = getattr(record, "cdh_span_id", "") or ""

        entry: dict[str, Any] = {
            "timeUnixNano": str(ts_ns),
            "observedTimeUnixNano": str(int(time.time() * 1e9)),
            "severityNumber": _OTEL_SEVERITY.get(record.levelno, 9),
            "severityText": record.levelname,
            "body": record.getMessage(),
            "attributes": [
                {"key": "logger.name", "value": {"stringValue": record.name}},
                {"key": "process.pid", "value": {"intValue": str(record.process)}},
                {"key": "thread.id", "value": {"intValue": str(record.thread)}},
            ],
        }
        if trace_id:
            entry["traceId"] = trace_id
        if span_id:
            entry["spanId"] = span_id

        if record.exc_info:
            entry["attributes"].append({
                "key": "exception.type",
                "value": {"stringValue": str(record.exc_info[0].__name__)},
            })
            entry["attributes"].append({
                "key": "exception.message",
                "value": {"stringValue": str(record.exc_info[1])},
            })

        if hasattr(record, "fr_id"):
            entry["attributes"].append({"key": "cdh.fr_id", "value": {"stringValue": str(record.fr_id)}})
        if hasattr(record, "session_id"):
            entry["attributes"].append({"key": "cdh.session_id", "value": {"stringValue": str(record.session_id)}})
        if hasattr(record, "tags"):
            for k, v in (record.tags or {}).items():
                entry["attributes"].append({f"cdh.tag.{k}": _otlp_value(v)})

        return entry


_OTEL_SEVERITY = {
    logging.DEBUG: 5,
    logging.INFO: 9,
    logging.WARNING: 13,
    logging.ERROR: 17,
    logging.CRITICAL: 21,
}


def _otlp_value(v: Any) -> dict[str, Any]:
    if v is None:
        return {"stringValue": ""}
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    return {"stringValue": str(v)}


class JSONLogger:
    """Structured logger that writes NDJSON and supports trace correlation."""

    def __init__(self, name: str, level: LogLevel = LogLevel.INFO):
        self.name = name
        self._level = level
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level.python_level)
        self._logger.propagate = False
        if not self._logger.handlers:
            self._logger.addHandler(JSONLogHandler())

    def _log(self, level: LogLevel, msg: str, **kwargs: Any) -> None:
        record = self._logger.makeRecord(
            self.name,
            level.python_level,
            "(unknown)",
            0,
            msg,
            (),
            None,
        )
        for k, v in kwargs.items():
            setattr(record, k, v)
        self._logger.handle(record)

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._log(LogLevel.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        self._log(LogLevel.INFO, msg, **kwargs)

    def warn(self, msg: str, **kwargs: Any) -> None:
        self._log(LogLevel.WARN, msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._log(LogLevel.ERROR, msg, **kwargs)

    def fatal(self, msg: str, **kwargs: Any) -> None:
        self._log(LogLevel.FATAL, msg, **kwargs)


def get_logger(name: str, level: LogLevel = LogLevel.INFO) -> JSONLogger:
    """Get or create a structured JSON logger."""
    if name not in _loggers:
        _loggers[name] = JSONLogger(name, level)
    return _loggers[name]


def export_logs(
    log_file: Path | None = None,
    since: datetime | None = None,
    session_id: str | None = None,
    min_level: LogLevel = LogLevel.DEBUG,
    endpoint: str | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Export logs in OTLP format.

    Returns counters: read, exported, failed.
    """
    counters = {"read": 0, "exported": 0, "failed": 0}
    path = log_file or (_ensure_log_dir() / DEFAULT_LOG_FILE)

    if not path.exists():
        return counters

    if endpoint is None:
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

    records: list[dict[str, Any]] = []
    cutoff_ns = int(since.timestamp() * 1e9) if since else 0

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_ns = int(record.get("timeUnixNano", 0))
            if cutoff_ns and ts_ns < cutoff_ns:
                continue
            counters["read"] += 1
            records.append(record)

    if not records:
        return counters

    if dry_run or not endpoint:
        counters["exported"] = len(records)
        return counters

    payload = _build_otlp_payload(records)
    status, body = _http_post(endpoint, payload)
    if 200 <= status < 300:
        counters["exported"] = len(records)
    else:
        counters["failed"] = len(records)

    return counters


def _build_otlp_payload(records: list[dict[str, Any]]) -> bytes:
    resource_logs = [{
        "resource": {
            "attributes": [
                {"key": "service.name", "value": {"stringValue": "cdh"}},
                {"key": "telemetry.sdk.language", "value": {"stringValue": "python"}},
                {"key": "telemetry.sdk.version", "value": {"stringValue": _OTEL_VERSION}},
            ]
        },
        "scopeLogs": [{
            "scope": {"name": "cdh.logging", "version": "1.0.0"},
            "logRecords": records,
        }],
    }]
    return json.dumps(resource_logs).encode("utf-8")


def _http_post(url: str, payload: bytes, timeout: float = 10.0) -> tuple[int, str]:
    headers = {
        "Content-Type": "application/json",
    }
    env_hdrs = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")
    for part in env_hdrs.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            headers[k.strip()] = v.strip()

    try:
        import urllib.request
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0, str(e)
