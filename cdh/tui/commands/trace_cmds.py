from __future__ import annotations

from cdh.tui.commands.registry import command


@command("trace start", "Start trace recording")
def cmd_trace_start(app, *args):
    app.tracer.start()
    return f"Trace started. ID: {app.tracer.trace_id}"


@command("trace stop", "Stop trace recording")
def cmd_trace_stop(app, *args):
    if not app.tracer.recording:
        return "No active trace."
    app.tracer.stop()
    return f"Trace stopped and saved. ID: {app.tracer.trace_id}"


@command("trace view", "View trace details")
def cmd_trace_view(app, *args):
    trace_id = args[0] if args else None
    spans = app.tracer.view(trace_id)
    if not spans:
        return "No trace data available."
    lines = [f"{'Span':<30} {'Duration (ms)':<15} {'Parent'}"]
    lines.append("-" * 60)
    for s in spans:
        dur = s.get("duration_ms", "N/A")
        parent = s.get("parent_id", "-")[:8] if s.get("parent_id") else "-"
        lines.append(f"{s.get('name', '?'):<30} {str(dur):<15} {parent}")
    return "\n".join(lines)


@command("trace export", "Export trace as JSON")
def cmd_trace_export(app, *args):
    if not app.tracer.trace_id:
        return "No trace to export."
    app.tracer._export()
    return f"Trace exported to ~/.cloud-dev-harness/traces/{app.tracer.trace_id}.json"
