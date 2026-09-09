"""Standalone OTLP exporter for the agenttrace SQLite database.

Usage::

    python -m cdh.tools.otel_export --endpoint http://localhost:4318 --since 2026-07-01
    python -m cdh.tools.otel_export --service-name cdh-prod --session <sid>
    python -m cdh.tools.otel_export --dry-run --since 2026-07-01

This script is intentionally dependency-free at import time — it uses only the
Python standard library plus the helpers in :mod:`cdh.trace.otel_exporter`.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Make `cdh.trace.otel_exporter` importable when running this file directly
# (i.e. ``python cdh/tools/otel_export.py``).
_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cdh.trace.otel_exporter import DEFAULT_DB_PATH, OtlpExporter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export agenttrace spans from the local sqlite DB to an OTLP/HTTP collector.",
    )
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"),
        help="OTLP/HTTP base endpoint (default: $OTEL_EXPORTER_OTLP_ENDPOINT or http://localhost:4318)",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to the agenttrace sqlite DB (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--service-name",
        default=os.environ.get("OTEL_SERVICE_NAME", "cdh"),
        help="Value of the service.name resource attribute",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Only export rows with timestamp >= this value (ISO date or datetime)",
    )
    parser.add_argument(
        "--session",
        default=None,
        help="Restrict export to a single session_id",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=256,
        help="Spans per HTTP POST (default: 256)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Per-request HTTP timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build payloads but don't POST. Prints the would-be batch count.",
    )
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        metavar="K=V",
        help="Extra HTTP header (repeatable). e.g. --header 'Authorization=Bearer xxx'",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging",
    )

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    headers: dict[str, str] = {}
    for h in args.header:
        if "=" in h:
            k, v = h.split("=", 1)
            headers[k.strip()] = v.strip()

    exporter = OtlpExporter(
        db_path=args.db_path,
        endpoint=args.endpoint,
        service_name=args.service_name,
        headers=headers,
        batch_size=args.batch_size,
        timeout_s=args.timeout,
        dry_run=args.dry_run,
    )

    counters = exporter.export_since(since=args.since, session_id=args.session)

    mode = "(dry-run) " if args.dry_run else ""
    print(
        f"{mode}OTLP export summary: "
        f"read={counters['read']} sent={counters['sent']} "
        f"failed={counters['failed']} batches={counters['batches']}"
    )
    if not args.dry_run and counters["failed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())