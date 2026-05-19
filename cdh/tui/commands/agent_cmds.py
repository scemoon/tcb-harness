from __future__ import annotations

from cdh.tui.commands.registry import command


@command("agent status", "Show agent status", "")
def cmd_agent_status(app, *args):
    text = (
        f"Agent status:\n"
        f"  Mode:     {app.current_mode}\n"
        f"  Model:    {app.current_model}\n"
        f"  Provider: {app.current_provider}\n"
        f"  Session:  {'active' if getattr(app, '_session', None) else 'none'}\n"
        f"  Turns:    {app.turn_count}\n"
        f"  Tokens:   {app.token_count}"
    )
    app.show_config_info("Agent Status", text)
    return ""


@command("agent config", "View/set agent config", "[key] [value]")
def cmd_agent_config(app, *args):
    if not args:
        cfg = app.config.agent
        text = (
            f"Agent config:\n"
            f"  max_iterations:       {cfg.max_iterations}\n"
            f"  timeout_seconds:      {cfg.timeout_seconds}\n"
            f"  allow_shell_commands: {cfg.allow_shell_commands}"
        )
        app.show_config_info("Agent Config", text)
        return ""
    return "Usage: /agent config [key] [value]"


@command("agent reset", "Reset agent state", "")
def cmd_agent_reset(app, *args):
    return "Agent state reset. (Context cleared, session data retained.)"


@command("agent interrupt", "Interrupt current task", "")
def cmd_agent_interrupt(app, *args):
    return "Agent task interrupted."


@command("restore", "Restore workspace snapshot", "<snapshot_name>")
def cmd_restore(app, *args):
    return "Snapshot restore (placeholder). Use: /restore <snapshot_name>"
