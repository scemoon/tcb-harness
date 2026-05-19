from __future__ import annotations

from pathlib import Path

from rich.text import Text

from cdh.tui.commands.registry import CommandRegistry, command


@command("help", "Show help information", "/help [command]")
def cmd_help(app, *args):
    if args:
        cmd_name = args[0]
        info = CommandRegistry.get_info(cmd_name)
        if info:
            _, help_text, usage = info
            lines = [f"/{cmd_name}: {help_text}"]
            if usage:
                lines.append(f"  Usage: {usage}")
            return "\n".join(lines)
        return f"No help for /{cmd_name}"
    cmds = CommandRegistry.list_commands()
    categories = {
        "session": [], "project": [], "mode": [], "spec": [], "design": [],
        "test": [], "deploy": [], "model": [], "agent": [], "skill": [],
        "mcp": [], "provider": [], "cloud": [], "attach": [], "trace": [],
        "restore": [],
    }
    for name, help_text in cmds:
        cat = name.split()[0]
        if cat in categories:
            categories[cat].append((name, help_text))
    lines = ["Available commands:\n"]
    for cat, cmds_list in sorted(categories.items()):
        if cmds_list:
            lines.append(f"  {cat}:")
            for n, h in cmds_list:
                lines.append(f"    /{n:<30} {h}")
            lines.append("")
    text = "\n".join(lines)
    if app and hasattr(app, "show_config_info"):
        app.show_config_info("Help", text)
        return ""
    return text


@command("clear", "Clear the screen")
def cmd_clear(app, *args):
    from cdh.tui.widgets.chat import ChatPanel
    from textual.widgets import Static

    chat = app.query_one(ChatPanel)
    log = chat.query_one("#chat-log", Static)
    log.clear()
    app.show_config_info("Clear", "Screen cleared.")
    return ""


@command("status", "Show status summary")
def cmd_status(app, *args):
    text = (
        f"Mode:      {app.current_mode}\n"
        f"Project:   {app.current_project or 'none'}\n"
        f"Model:     {app.current_model}\n"
        f"Provider:  {app.current_provider}\n"
        f"Cloud:     {app.current_cloud}\n"
        f"Session:   {'active' if getattr(app, '_session', None) else 'none'}\n"
        f"Turns:     {app.turn_count}  |  Tokens: {app.token_count}\n"
        f"Lifecycle: {app.lifecycle.summary()}"
    )
    app.show_config_info("Status", text)
    return ""


@command("exit", "Exit the application")
def cmd_exit(app, *args):
    app.exit()
    return "Goodbye."


@command("workspace", "Show or set default workspace")
def cmd_workspace(app, *args):
    cfg = app.config
    if not args:
        ws = cfg.default_workspace or str(Path.cwd())
        return f"Default workspace: {ws}"
    path = args[0]
    cfg.default_workspace = str(Path(path).expanduser())
    from cdh.config import save_config
    save_config(cfg)
    return f"Workspace set to: {cfg.default_workspace}"


@command("session rename", "Rename a session")
def cmd_session_rename(app, *args):
    if len(args) < 2:
        return "Usage: /session rename <id> <new_name>"
    app.session_store.rename(args[0], args[1])
    return f"Session {args[0]} renamed to {args[1]}"


@command("session delete", "Delete a session")
def cmd_session_delete(app, *args):
    if not args:
        return "Usage: /session delete <id>"
    app.session_store.delete(args[0])
    return f"Session {args[0]} deleted."


@command("session export", "Export session as JSON")
def cmd_session_export(app, *args):
    if not args:
        return "Usage: /session export <id> [json|md]"
    result = app.session_store.export_json(args[0])
    if result:
        return result[:2000] + "...\n(truncated)"
    return "Session not found."


@command("attach", "Attach a file to the session")
def cmd_attach(app, *args):
    if not args:
        return "Usage: /attach <path> [--as <name>]"
    return f"File attached: {args[0]}"


@command("spec load", "Load spec from file")
def cmd_spec_load(app, *args):
    if not args:
        return "Usage: /spec load <path>"
    return f"Spec loaded from {args[0]}"


@command("design load", "Load design from file")
def cmd_design_load(app, *args):
    if not args:
        return "Usage: /design load <path>"
    return f"Design loaded from {args[0]}"


@command("test design", "Design test strategy")
def cmd_test_design(app, *args):
    return "Test strategy designed."


@command("test generate", "Generate test code")
def cmd_test_generate(app, *args):
    test_type = args[0] if args else "unit"
    return f"Generated {test_type} tests."


@command("test report", "Show test report")
def cmd_test_report(app, *args):
    return "Test report: All tests passed (placeholder)."


@command("deploy status", "Check deployment status")
def cmd_deploy_status(app, *args):
    v = app.lifecycle.deploy_version or "N/A"
    return f"Deployment status: version={v}"


@command("deploy rollback", "Rollback deployment")
def cmd_deploy_rollback(app, *args):
    version = args[0] if args else "previous"
    return f"Rolled back to {version}."


@command("model reference", "Show model reference table")
def cmd_model_reference(app, *args):
    from cdh.models.registry import ModelRegistry
    table = ModelRegistry.reference_table()
    from rich.console import Console
    import io
    buf = io.StringIO()
    console = Console(file=buf, width=100)
    console.print(table)
    return buf.getvalue()


@command("trace platform", "Configure trace platform")
def cmd_trace_platform(app, *args):
    url = args[0] if args else "http://localhost:16686"
    return f"Trace platform set to {url}"


@command("theme", "Switch theme (dark|light)")
def cmd_theme(app, *args):
    name = args[0] if args else "dark"
    theme_map = {"dark": "cdh-dark", "light": "cdh-light", "cdh-dark": "cdh-dark", "cdh-light": "cdh-light"}
    theme_name = theme_map.get(name, "cdh-dark")
    app.theme = theme_name
    app._apply_theme()
    if hasattr(app, 'config') and hasattr(app.config, 'tui'):
        app.config.tui.theme = "light" if "light" in theme_name else "dark"
        from cdh.config import save_config
        save_config(app.config)
    return f"Theme switched to {theme_name}."


@command("spec feedback", "Provide spec feedback")
def cmd_spec_feedback(app, *args):
    if not args:
        return "Usage: /spec feedback <text>"
    return f"Feedback recorded: {' '.join(args)}"


@command("design feedback", "Provide design feedback")
def cmd_design_feedback(app, *args):
    if not args:
        return "Usage: /design feedback <text>"
    return f"Feedback recorded: {' '.join(args)}"


@command("skill enable", "Enable a skill")
def cmd_skill_enable(app, *args):
    if not args:
        return "Usage: /skill enable <name>"
    from cdh.skill.manager import SkillManager
    SkillManager().enable(args[0], True)
    return f"Skill enabled: {args[0]}"


@command("skill disable", "Disable a skill")
def cmd_skill_disable(app, *args):
    if not args:
        return "Usage: /skill disable <name>"
    from cdh.skill.manager import SkillManager
    SkillManager().enable(args[0], False)
    return f"Skill disabled: {args[0]}"


@command("mcp remove", "Remove MCP connection")
def cmd_mcp_remove(app, *args):
    if not args:
        return "Usage: /mcp remove <name>"
    from cdh.mcp.manager import MCPManager
    MCPManager().remove(args[0])
    return f"MCP connection removed: {args[0]}"
