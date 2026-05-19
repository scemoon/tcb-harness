from __future__ import annotations

from cdh.tui.commands.registry import command


@command("mode", "Show or switch mode (plan|agent|solo)")
def cmd_mode(app, *args):
    if not args:
        current = app.current_mode
        modes = ["plan", "agent", "solo"]
        items = []
        for m in modes:
            active = "[active] " if m == current else ""
            items.append((f"{active}{m}", f"mode {m}"))
        app.show_config_panel("Mode", items, "", execute=True)
        return ""
    mode = args[0].lower()
    if mode not in ("plan", "agent", "solo"):
        return "Mode must be plan, agent, or solo."
    app.current_mode = mode
    if mode == "plan":
        app.agent.set_agent("plan")
    else:
        app.agent.set_agent("build")
    app.query_one("HeaderBar").sync(app)
    return f"Switched to {mode} mode."
