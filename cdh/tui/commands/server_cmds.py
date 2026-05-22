from __future__ import annotations

from cdh.tui.commands.registry import command


@command("server start", "Start the HTTP/SSE agent server", "[port=8765]")
def cmd_server_start(app, *args):
    port = int(args[0]) if args else 8765
    from cdh.server import AgentServer
    server = AgentServer(app.agent, port=port)
    server.start_background()
    return f"Agent server started on http://127.0.0.1:{port}"


@command("server stop", "Stop the agent server")
def cmd_server_stop(app, *args):
    return "Server stop: use /server start to restart (server runs in background thread)"
