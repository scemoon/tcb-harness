"""Trace dashboard API — all SQL queries."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def _connect(db_path: Path) -> sqlite3.Connection | None:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("SELECT COUNT(*) FROM traces")
    except sqlite3.OperationalError:
        conn.close()
        return None
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _require_db(db_path: Path):
    """Return a connection or raise a clear error about empty DB."""
    conn = _connect(db_path)
    if conn is None:
        raise EmptyTraceDB("No traces yet. Run an agent session to collect data.")
    return conn


class EmptyTraceDB(Exception):
    pass


def _json_val(column: str) -> str:
    """Return a SQLite expression to extract a value from the data JSON column.

    Checks both top-level and nested kwargs paths.
    """
    return (
        f"COALESCE(JSON_EXTRACT(data, '$.{column}'), "
        f"JSON_EXTRACT(data, '$.kwargs.{column}'))"
    )


def _tags_val(key: str) -> str:
    """Return a SQLite expression to extract a tag from the tags JSON column."""
    return f"JSON_EXTRACT(tags, '$.{key}')"


def _parse_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    if isinstance(d.get("tags"), str):
        try:
            d["tags"] = json.loads(d["tags"])
        except (json.JSONDecodeError, TypeError):
            d["tags"] = {}
    if isinstance(d.get("data"), str):
        try:
            data = json.loads(d["data"])
            d["data"] = data
            for k, v in data.items():
                if k not in d or d[k] is None:
                    d[k] = v
            if isinstance(data.get("kwargs"), dict):
                for k, v in data["kwargs"].items():
                    if k not in d or d[k] is None:
                        d[k] = v
        except (json.JSONDecodeError, TypeError):
            d["data"] = {}
    d["type"] = d.pop("trace_type", d.get("type", ""))
    d["function"] = d.pop("function_name", d.get("function", ""))
    return d


def get_overview(db_path: Path) -> dict:
    conn = _connect(db_path)
    if conn is None:
        return {"total": 0, "total_today": 0, "sessions": 0, "agents": 0,
                "avg_duration": 0, "p95_duration": 0, "error_count": 0,
                "error_rate": 0, "total_tokens": 0, "lines_added": 0,
                "tokens_per_kloc": 0, "type_distribution": {},
                "hourly": [], "agent_breakdown": []}
    try:
        now = datetime.utcnow()
        today_start = now.strftime("%Y-%m-%dT00:00:00")

        total = conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
        total_today = conn.execute(
            "SELECT COUNT(*) FROM traces WHERE timestamp >= ?", (today_start,)
        ).fetchone()[0]
        sessions = conn.execute(
            "SELECT COUNT(DISTINCT session_id) FROM traces"
        ).fetchone()[0]
        agents = conn.execute(
            "SELECT COUNT(DISTINCT {}) FROM traces WHERE {} IS NOT NULL".format(
                _tags_val("agent"), _tags_val("agent")
            )
        ).fetchone()[0]

        # Duration stats (from data->duration_ms)
        durations = [
            r[0]
            for r in conn.execute(
                "SELECT {} FROM traces WHERE {} IS NOT NULL".format(
                    _json_val("duration_ms"), _json_val("duration_ms")
                )
            ).fetchall()
            if r[0] is not None
        ]
        # The duration_ms column stores seconds (agenttrace stores the duration value
        # verbatim), so the raw value is already in seconds — do NOT divide by 1000.
        durations_s = [float(d) for d in durations]
        avg_duration = sum(durations_s) / len(durations_s) if durations_s else 0
        sorted_d = sorted(durations_s)
        p95 = sorted_d[int(len(sorted_d) * 0.95)] if sorted_d else 0

        # Type distribution
        type_dist = {
            r["trace_type"]: r["cnt"]
            for r in conn.execute(
                "SELECT trace_type, COUNT(*) as cnt FROM traces GROUP BY trace_type ORDER BY cnt DESC"
            ).fetchall()
        }

        # Time series (hourly, last 7 days)
        week_ago = (now - timedelta(days=7)).isoformat()
        hourly = [
            {"bucket": r["bucket"], "count": r["cnt"]}
            for r in conn.execute(
                """SELECT strftime('%Y-%m-%dT%H:00:00', timestamp) as bucket,
                          COUNT(*) as cnt
                   FROM traces WHERE timestamp >= ?
                   GROUP BY bucket ORDER BY bucket""",
                (week_ago,),
            ).fetchall()
        ]

        # Error rate
        errors = conn.execute(
            "SELECT COUNT(*) FROM traces WHERE {} IS NOT NULL AND {} != ''".format(
                _json_val("error"), _json_val("error")
            )
        ).fetchone()[0]

        # Cost estimate (sum of token_count)
        total_tokens = conn.execute(
            "SELECT COALESCE(SUM({}), 0) FROM traces".format(_json_val("token_count"))
        ).fetchone()[0]

        # Lines of code added (Edit/Write tool calls at the collection layer)
        total_lines_added = conn.execute(
            "SELECT COALESCE(SUM({}), 0) FROM traces".format(_json_val("lines_added"))
        ).fetchone()[0]
        tokens_per_kloc = (
            round(total_tokens / (total_lines_added / 1000), 2)
            if total_lines_added else 0
        )

        # Agent breakdown for bar chart (case-insensitive grouping)
        agent_breakdown = [
            {"agent": r["agent"], "count": r["cnt"]}
            for r in conn.execute(
                "SELECT MAX({0}) as agent, COUNT(*) as cnt FROM traces WHERE {1} IS NOT NULL GROUP BY LOWER({1}) ORDER BY cnt DESC".format(
                    _tags_val("agent"), _tags_val("agent")
                )
            ).fetchall()
        ]

        return {
            "total": total,
            "total_today": total_today,
            "sessions": sessions,
            "agents": agents,
            "avg_duration": round(avg_duration, 2),
            "p95_duration": round(p95, 2),
            "error_count": errors,
            "error_rate": round(errors / total * 100, 2) if total else 0,
            "total_tokens": total_tokens,
            "lines_added": total_lines_added,
            "tokens_per_kloc": tokens_per_kloc,
            "type_distribution": type_dist,
            "hourly": hourly,
            "agent_breakdown": agent_breakdown,
            "db_path": str(db_path),
        }
    finally:
        conn.close()


def get_traces(
    db_path: Path,
    limit: int = 50,
    offset: int = 0,
    trace_type: str | None = None,
    agent: str | None = None,
    model: str | None = None,
    status: str | None = None,
    session_id: str | None = None,
    search: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    conn = _connect(db_path)
    if conn is None:
        return {"traces": [], "total": 0, "limit": limit, "offset": offset}
    try:
        where = ["1=1"]
        params: list[Any] = []

        if trace_type:
            where.append("trace_type = ?")
            params.append(trace_type)
        if agent:
            where.append("{} = ?".format(_tags_val("agent")))
            params.append(agent)
        if model:
            where.append("{} = ?".format(_json_val("model")))
            params.append(model)
        if status:
            where.append("{} = ?".format(_json_val("status")))
            params.append(status)
        if session_id:
            where.append("session_id = ?")
            params.append(session_id)
        if search:
            where.append("function_name LIKE ?")
            params.append(f"%{search}%")
        if start:
            where.append("timestamp >= ?")
            params.append(start)
        if end:
            where.append("timestamp <= ?")
            params.append(end)

        where_clause = " AND ".join(where)

        # Count total matching
        count_row = conn.execute(
            f"SELECT COUNT(*) FROM traces WHERE {where_clause}", params
        ).fetchone()[0]

        # Fetch rows
        rows = conn.execute(
            f"SELECT * FROM traces WHERE {where_clause} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()

        traces = [_parse_row(r) for r in rows]
        return {"traces": traces, "total": count_row, "limit": limit, "offset": offset}
    finally:
        conn.close()


def get_sessions(db_path: Path, limit: int = 100, offset: int = 0) -> dict:
    conn = _connect(db_path)
    if conn is None:
        return {"sessions": [], "total": 0, "limit": limit, "offset": offset}
    try:
        count_row = conn.execute(
            "SELECT COUNT(DISTINCT session_id) FROM traces"
        ).fetchone()[0]

        rows = conn.execute(
            f"""SELECT session_id,
                       COUNT(*) as span_count,
                       MIN(timestamp) as first_ts,
                       MAX(timestamp) as last_ts,
                       COUNT(DISTINCT {_tags_val('agent')}) as agent_count,
                       COUNT(DISTINCT {_json_val('model')}) as model_count,
                       MAX({_json_val('error')}) as last_error,
                        SUM(CASE WHEN {_json_val('status')} IN ('error','failed') THEN 1 ELSE 0 END) as error_spans,
                        SUM(COALESCE({_json_val('token_count')}, 0)) as total_tokens,
                        SUM(COALESCE({_json_val('lines_added')}, 0)) as lines_added
                 FROM traces
                GROUP BY session_id
                ORDER BY last_ts DESC
                LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()

        sessions_list = []
        for r in rows:
            d = dict(r)
            agents = conn.execute(
                "SELECT DISTINCT {} FROM traces WHERE session_id = ? AND {} IS NOT NULL".format(
                    _tags_val("agent"), _tags_val("agent")
                ),
                (d["session_id"],),
            ).fetchall()
            d["agents"] = [a[0] for a in agents if a[0]]
            sessions_list.append(d)

        return {"sessions": sessions_list, "total": count_row, "limit": limit, "offset": offset}
    finally:
        conn.close()


def get_session_detail(db_path: Path, session_id: str) -> dict | None:
    conn = _connect(db_path)
    if conn is None:
        return None
    try:
        rows = conn.execute(
            "SELECT * FROM traces WHERE session_id = ? ORDER BY timestamp ASC",
            (session_id,),
        ).fetchall()

        if not rows:
            return None

        spans = [_parse_row(r) for r in rows]

        # Build call tree from parent_span_id
        span_map: dict[str, dict] = {}
        root_spans: list[dict] = []
        orphan_spans: list[dict] = []

        for s in spans:
            s["children"] = []
            span_id = s.get("id", "")
            if span_id:
                span_map[span_id] = s

        # Build tree
        subagent_parents: dict[str, dict] = {}
        for s in spans:
            pid = s.get("parent_span_id", "") or ""
            if pid == "session_root" or not pid:
                root_spans.append(s)
            elif pid.startswith("subagent:"):
                sa_id = pid[len("subagent:"):]
                if sa_id not in subagent_parents:
                    subagent_parents[sa_id] = []
                subagent_parents[sa_id].append(s)
            else:
                parent = span_map.get(pid)
                if parent:
                    parent.setdefault("children", []).append(s)
                else:
                    orphan_spans.append(s)

        # Attach subagent children to their parent span.
        # Preferred: match by explicit subagent_id (recorded on subagent_start since the fix).
        # Fallback: pair remaining subagent children with subagent_start roots in emission order.
        matched_ids: set[str] = set()
        for s in root_spans:
            s_data = s.get("data") or {}
            if isinstance(s_data, str):
                try:
                    s_data = json.loads(s_data)
                except Exception:
                    s_data = {}
            s_tags = s.get("tags") or {}
            if isinstance(s_tags, str):
                try:
                    s_tags = json.loads(s_tags)
                except Exception:
                    s_tags = {}
            sa_id = s_data.get("subagent_id") or s_tags.get("subagent_id")
            if sa_id and sa_id in subagent_parents:
                s.setdefault("children", []).extend(subagent_parents[sa_id])
                matched_ids.add(sa_id)

        # Sequential fallback for data without an explicit subagent_id link:
        # subagent_start spans carry agent_type and appear in the same order as their children.
        if subagent_parents:
            subagent_roots = [
                s for s in root_spans
                if not (s.get("data") or {}).get("children") and (
                    s.get("function") == "subagent_start"
                    or (s.get("data") or {}).get("agent_type")
                )
            ]
            remaining = [sid for sid in subagent_parents if sid not in matched_ids]
            for i, sa_id in enumerate(remaining):
                if i < len(subagent_roots):
                    subagent_roots[i].setdefault("children", []).extend(subagent_parents[sa_id])

        # Never drop data: attach any still-orphaned spans to the root level.
        if orphan_spans:
            root_spans.extend(orphan_spans)

        stats = _compute_session_stats(spans)

        return {"session_id": session_id, "spans": spans, "tree": root_spans, "stats": stats}
    finally:
        conn.close()


def _matches_subagent(span: dict, subagent_id: str, _children: list) -> bool:
    tags = span.get("tags") or {}
    data = span.get("data") or {}
    # Check various places where subagent_id could be stored
    if isinstance(tags, dict) and tags.get("subagent_id") == subagent_id:
        return True
    if isinstance(data, dict) and data.get("subagent_id") == subagent_id:
        return True
    if subagent_id in (span.get("agent_type") or ""):
        return True
    return False


def _compute_session_stats(spans: list[dict]) -> dict:
    if not spans:
        return {}

    first = spans[0]
    last = spans[-1]
    total_dur = 0
    total_tokens = 0
    total_lines = 0
    errors = []
    agents = set()
    models = set()
    tool_calls = 0
    tools: dict[str, int] = {}

    for s in spans:
        d = s.get("data") or {}
        if isinstance(d, str):
            try:
                d = json.loads(d)
            except Exception:
                d = {}
        tags = s.get("tags") or {}
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = {}

        dur = float(d.get("duration_ms") or s.get("duration_ms") or 0)
        total_dur += dur

        tok = int(d.get("token_count") or s.get("token_count") or 0)
        total_tokens += tok

        loc = int(d.get("lines_added") or s.get("lines_added") or 0)
        total_lines += loc

        if isinstance(tags, dict) and tags.get("agent"):
            agents.add(tags["agent"])

        model = d.get("model") or s.get("model")
        if model:
            models.add(model)

        if s.get("function") == "tool_call":
            tool_calls += 1
            tname = d.get("tool_name") or s.get("tool_name", "")
            if tname:
                tools[tname] = tools.get(tname, 0) + 1

        err = d.get("error") or s.get("error")
        if err:
            errors.append({"span_id": s.get("id", ""), "function": s.get("function", ""), "error": err})

    tokens_per_kloc = round(total_tokens / (total_lines / 1000), 2) if total_lines else 0
    return {
        "first_ts": first.get("timestamp"),
        "last_ts": last.get("timestamp"),
        "duration_ms": total_dur,
        "total_tokens": total_tokens,
        "lines_added": total_lines,
        "tokens_per_kloc": tokens_per_kloc,
        "agents": list(agents),
        "models": list(models),
        "tool_calls": tool_calls,
        "tools": tools,
        "errors": errors,
        "error_count": len(errors),
    }


def get_agents(db_path: Path) -> list[dict]:
    conn = _connect(db_path)
    if conn is None:
        return []
    try:
        return [
            {
                "agent": r["agent"],
                "span_count": r["span_count"],
                "session_count": r["session_count"],
                "avg_duration": r["avg_dur"] if r["avg_dur"] else 0,
                "error_count": r["error_count"],
            }
            for r in conn.execute(
                f"""SELECT {_tags_val('agent')} as agent,
                          COUNT(*) as span_count,
                          COUNT(DISTINCT session_id) as session_count,
                          AVG({_json_val('duration_ms')}) as avg_dur,
                          SUM(CASE WHEN {_json_val('status')} IN ('error','failed') OR ({_json_val('error')} IS NOT NULL AND {_json_val('error')} != '') THEN 1 ELSE 0 END) as error_count
                   FROM traces
                   WHERE {_tags_val('agent')} IS NOT NULL
                   GROUP BY agent
                   ORDER BY span_count DESC"""
            ).fetchall()
        ]
    finally:
        conn.close()


def get_model_stats(db_path: Path) -> list[dict]:
    conn = _connect(db_path)
    if conn is None:
        return []
    try:
        return [
            {
                "model": r["model"],
                "span_count": r["span_count"],
                "total_tokens": r["total_tokens"],
                "avg_duration": r["avg_dur"] if r["avg_dur"] else 0,
            }
            for r in conn.execute(
                f"""SELECT {_json_val('model')} as model,
                          COUNT(*) as span_count,
                          COALESCE(SUM({_json_val('token_count')}), 0) as total_tokens,
                          AVG({_json_val('duration_ms')}) as avg_dur
                   FROM traces
                   WHERE {_json_val('model')} IS NOT NULL AND {_json_val('model')} != ''
                   GROUP BY model
                   ORDER BY span_count DESC"""
            ).fetchall()
        ]
    finally:
        conn.close()


def get_tool_stats(db_path: Path) -> list[dict]:
    conn = _connect(db_path)
    if conn is None:
        return []
    try:
        return [
            {
                "tool": r["tool"],
                "call_count": r["call_count"],
                "avg_duration": r["avg_dur"] if r["avg_dur"] else 0,
                "error_count": r["error_count"],
            }
            for r in conn.execute(
                f"""SELECT {_json_val('tool_name')} as tool,
                          COUNT(*) as call_count,
                          AVG({_json_val('duration_ms')}) as avg_dur,
                          SUM(CASE WHEN {_json_val('status')} IN ('error','failed') THEN 1 ELSE 0 END) as error_count
                   FROM traces
                   WHERE {_json_val('tool_name')} IS NOT NULL AND {_json_val('tool_name')} != ''
                   GROUP BY tool
                   ORDER BY call_count DESC"""
            ).fetchall()
        ]
    finally:
        conn.close()


def get_error_stats(db_path: Path) -> list[dict]:
    conn = _connect(db_path)
    if conn is None:
        return []
    try:
        return [
            {
                "error": r["error"],
                "count": r["cnt"],
                "latest": r["latest"],
                "latest_session": r["latest_session"],
            }
            for r in conn.execute(
                f"""SELECT {_json_val('error')} as error,
                          COUNT(*) as cnt,
                          MAX(timestamp) as latest,
                          (SELECT session_id FROM traces WHERE {_json_val('error')} IS NOT NULL AND {_json_val('error')} != '' ORDER BY timestamp DESC LIMIT 1) as latest_session
                   FROM traces
                   WHERE {_json_val('error')} IS NOT NULL AND {_json_val('error')} != ''
                   GROUP BY error
                   ORDER BY cnt DESC"""
            ).fetchall()
        ]
    finally:
        conn.close()


def get_cost_stats(db_path: Path, model_prices: dict[str, float] | None = None) -> dict:
    conn = _connect(db_path)
    if conn is None:
        return {"total_tokens": 0, "total_input": 0, "total_output": 0, "daily": [], "by_model": []}
    try:
        # Only treat prices as real when the caller supplied a non-empty map.
        # Otherwise we must NOT fabricate a cost (no prices => estimated=false, cost=0).
        prices = model_prices or {}
        has_real_prices = bool(prices)

        # By day
        daily = []
        for r in conn.execute(
            f"""SELECT strftime('%%Y-%%m-%%d', timestamp) as day,
                      SUM(COALESCE({_json_val('token_count')}, 0)) as total_tokens,
                      SUM(COALESCE({_json_val('input_tokens')}, 0)) as total_input,
                      SUM(COALESCE({_json_val('output_tokens')}, 0)) as total_output
               FROM traces
               WHERE {_json_val('token_count')} IS NOT NULL
               GROUP BY day
               ORDER BY day ASC"""
        ).fetchall():
            entry = dict(r)
            entry["cost"] = 0
            entry["cost_details"] = {}
            daily.append(entry)

        # Total
        total_tokens = conn.execute(
            "SELECT COALESCE(SUM({}), 0) FROM traces".format(_json_val("token_count"))
        ).fetchone()[0]
        total_input = conn.execute(
            "SELECT COALESCE(SUM({}), 0) FROM traces".format(_json_val("input_tokens"))
        ).fetchone()[0]
        total_output = conn.execute(
            "SELECT COALESCE(SUM({}), 0) FROM traces".format(_json_val("output_tokens"))
        ).fetchone()[0]

        # By model
        by_model = [
            {
                "model": r["model"],
                "tokens": r["tokens"],
                "cost": round(r["tokens"] / 1000 * prices[r["model"]], 4) if has_real_prices else 0,
            }
            for r in conn.execute(
                f"""SELECT {_json_val('model')} as model,
                           SUM(COALESCE({_json_val('token_count')}, 0)) as tokens
                    FROM traces
                    WHERE {_json_val('model')} IS NOT NULL AND {_json_val('model')} != ''
                    GROUP BY model
                    ORDER BY tokens DESC"""
            ).fetchall()
        ]

        return {
            "total_tokens": total_tokens,
            "total_input": total_input,
            "total_output": total_output,
            "daily": daily,
            "by_model": by_model,
            "prices": prices,
            "estimated": not has_real_prices,
        }
    finally:
        conn.close()


def get_loc_stats(db_path: Path) -> dict:
    """Lines-of-code productivity metrics.

    Returns total lines added (Edit/Write), total tokens, and the derived
    "tokens per 1k lines of code" efficiency metric, both overall and broken
    down per model.
    """
    conn = _connect(db_path)
    if conn is None:
        return {
            "total_lines_added": 0,
            "total_tokens": 0,
            "tokens_per_kloc": 0,
            "by_model": [],
        }
    try:
        total_lines = conn.execute(
            "SELECT COALESCE(SUM({}), 0) FROM traces".format(_json_val("lines_added"))
        ).fetchone()[0]
        total_tokens = conn.execute(
            "SELECT COALESCE(SUM({}), 0) FROM traces".format(_json_val("token_count"))
        ).fetchone()[0]

        by_model = [
            {
                "model": r["model"],
                "lines_added": r["lines"],
                "tokens": r["tokens"],
                "tokens_per_kloc": (
                    round(r["tokens"] / (r["lines"] / 1000), 2) if r["lines"] else 0
                ),
            }
            for r in conn.execute(
                f"""SELECT {_json_val('model')} as model,
                           COALESCE(SUM({_json_val('lines_added')}), 0) as lines,
                           COALESCE(SUM({_json_val('token_count')}), 0) as tokens
                    FROM traces
                    WHERE {_json_val('model')} IS NOT NULL AND {_json_val('model')} != ''
                    GROUP BY model
                    ORDER BY tokens DESC"""
            ).fetchall()
        ]

        return {
            "total_lines_added": total_lines,
            "total_tokens": total_tokens,
            "tokens_per_kloc": (
                round(total_tokens / (total_lines / 1000), 2) if total_lines else 0
            ),
            "by_model": by_model,
        }
    finally:
        conn.close()


def export_traces(
    db_path: Path,
    fmt: str = "json",
    trace_type: str | None = None,
    agent: str | None = None,
    session_id: str | None = None,
    limit: int = 500,
) -> Any:
    conn = _connect(db_path)
    if conn is None:
        return [] if fmt == "json" else ""
    conn.close()
    result = get_traces(
        db_path=db_path,
        limit=limit,
        offset=0,
        trace_type=trace_type,
        agent=agent,
        session_id=session_id,
    )
    if fmt == "json":
        return result["traces"]
    elif fmt == "csv":
        import io

        output = io.StringIO()
        traces = result["traces"]
        if traces:
            keys = ["id", "session_id", "timestamp", "type", "function", "agent", "model", "duration_ms"]
            output.write(",".join(keys) + "\n")
            for t in traces:
                tags = t.get("tags") or {}
                data = t.get("data") or {}
                row = [
                    str(t.get("id", "")),
                    str(t.get("session_id", "")),
                    str(t.get("timestamp", "")),
                    str(t.get("type", "")),
                    str(t.get("function", "")),
                    str((tags if isinstance(tags, dict) else {}).get("agent", "")),
                    str(data.get("model", "")),
                    str(data.get("duration_ms", "")),
                ]
                output.write(",".join(row) + "\n")
        return output.getvalue()
    return result["traces"]
