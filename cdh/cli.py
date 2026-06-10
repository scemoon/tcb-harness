from pathlib import Path
from typing import Optional

import click

from cdha.cli import cli as cdha_cli
from cdha.cli import setup_logging
from cdha.config import ensure_dirs, load_config, save_config


_CDH_DIR = Path.home() / ".cdh"

_COMMON_HELP = """
\b
Usage:
  cdh                         Launch TUI (agent store)
  cdh tui                     Launch TUI (agent store)
  cdh tui --agent cdh.cloud-dev-harness   Launch TUI with agent
  cdh help                    Show this help message
  cdh config                  Configuration editor (TUI)
  cdh logs                    View application logs
  cdh project                 Project management
  cdh version                 Show version information

\b
Paths:
  Config   ~/.cdh/cdh.config.yaml
  Logs     ~/.cdh/logs/
  Projects ~/.cdh/projects/
"""


@click.group(
    invoke_without_command=True,
    cls=type(cdha_cli),
    context_settings=dict(max_content_width=100),
    short_help="Cloud Dev Harness - AI agent framework with TUI.",
    epilog=_COMMON_HELP,
)
@click.version_option(version="1.4.0", prog_name="cdh")
@click.pass_context
def cli(ctx):
    """
    CDH (Cloud Dev Harness) is an AI agent framework with LLM provider
    integration, session management, and a Textual-based TUI.

    Run without arguments to open the agent store. Use cdh tui --agent
    <identity> to launch a specific agent directly.
    """
    if ctx.invoked_subcommand is None:
        ensure_dirs()
        cfg = load_config()
        setup_logging(cfg.log_level)
        from tui.app import A2TUIApp
        A2TUIApp().run()


# --- config group ---

@cli.group(
    invoke_without_command=True,
    short_help="Open configuration editor",
)
@click.pass_context
def config(ctx):
    """Open the interactive TUI configuration editor.

    Launches a Textual-based UI for editing all CDH settings
    including providers, models, cloud platforms, agent parameters.
    """
    if ctx.invoked_subcommand is None:
        from cdha.config_screen import main as config_main
        config_main()


# Reuse subcommands from cdha's config group (mode, model, provider, cloud, log-level, skill, mcp, list)
for _cfg_cmd in cdha_cli.get_command(None, "config").commands.values():
    if _cfg_cmd.name not in config.commands and _cfg_cmd.name not in ("tui",):
        config.add_command(_cfg_cmd)


# --- logs command ---

@cli.command(short_help="View application logs")
@click.option("--tail", "-t", default=20, help="Number of recent log lines to show")
@click.option("--follow", "-f", is_flag=True, help="Follow log output")
def logs(tail, follow):
    """View CDH application logs.

    \b
    Examples:
      cdh logs              Show last 20 log lines
      cdh logs --tail 100   Show last 100 lines
      cdh logs --follow     Follow log output
    """
    log_file = _CDH_DIR / "logs" / "cdh.log"
    if not log_file.exists():
        click.echo("No log file found.")
        return
    if follow:
        click.echo(f"Following {log_file}...")
        import subprocess
        subprocess.run(["tail", "-f", str(log_file)])
    else:
        import subprocess
        subprocess.run(["tail", "-n", str(tail), str(log_file)])


# --- project command ---

def _get_projects():
    projects_dir = _CDH_DIR / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    return sorted(list(projects_dir.glob("*.yaml")) + list(projects_dir.glob("*.json")))


def _load_project_by_name(name: str) -> Optional[tuple]:
    projects_dir = _CDH_DIR / "projects"
    for ext in ["yaml", "yml", "json"]:
        pf = projects_dir / f"{name}.{ext}"
        if pf.exists():
            import yaml
            proj_data = yaml.safe_load(pf.read_text()) if ext in ["yaml", "yml"] else __import__("json").loads(pf.read_text())
            return name, proj_data.get("path", ".")
    return None


def _interactive_select_project():
    project_files = _get_projects()
    if not project_files:
        return None
    click.echo("Projects:")
    for i, pf in enumerate(project_files, 1):
        click.echo(f"  {i}) {pf.stem}")
    choice = click.prompt("Select project", type=str, default="").strip().lower()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(project_files):
            return ("load", project_files[idx].stem)
    except ValueError:
        pass
    return None


@cli.command(short_help="Project management (TUI)")
@click.argument("action", type=click.Choice(["list", "show", "new", "init", "load", "select"]), default="select")
@click.argument("name", required=False)
@click.argument("path", required=False, default=".")
def project(action, name, path):
    """Manage CDH projects.

    \b
    Without arguments, opens the project management TUI.
    Use subcommands for quick CLI operations.

    \b
    Actions:
      select         Open project management TUI (default)
      list           List all projects
      show <name>    Show project details
      new <name> [path]   Create a new project
      init [path]    Initialize .cdh in an existing directory (no registration)
      load <name>    Load a project (set as current)
    """
    import yaml
    projects_dir = _CDH_DIR / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)

    if action == "select":
        from tui.screens.projects_app import main as projects_main
        result = projects_main()
        if result == "loaded":
            from tui.app import A2TUIApp
            A2TUIApp().run()
        return

    if action == "list":
        project_files = sorted(list(projects_dir.glob("*.yaml")) + list(projects_dir.glob("*.json")))
        if not project_files:
            click.echo("No projects found.")
            return
        click.echo("Projects:")
        for pf in project_files:
            click.echo(f"  {pf.stem}")
    elif action == "show":
        if not name:
            click.echo("Usage: cdh project show <name>")
            return
        for ext in ["yaml", "yml", "json"]:
            pf = projects_dir / f"{name}.{ext}"
            if pf.exists():
                click.echo(pf.read_text())
                return
        click.echo(f"Project '{name}' not found.")
    elif action == "new":
        if not name:
            click.echo("Usage: cdh project new <name> [path]")
            return
        from cdha.agent.cdh_loader import CdhProjectLoader
        ws = Path(path).expanduser().resolve()
        CdhProjectLoader.init_project(ws, name)
        proj_data = {"name": name, "path": str(ws), "description": ""}
        project_file = projects_dir / f"{name}.yaml"
        project_file.write_text(yaml.dump(proj_data))
        cfg = load_config()
        cfg.current_project = name
        cfg.current_project_path = str(ws)
        save_config(cfg)
        click.echo(f"Created project '{name}' at {ws}")
    elif action == "init":
        from cdha.agent.cdh_loader import CdhProjectLoader
        target = Path(name or ".").expanduser().resolve()
        project_name = target.name
        CdhProjectLoader.init_project(target, project_name)
        click.echo(f"Initialized .cdh in {target}")
    elif action == "load":
        if not name:
            click.echo("Usage: cdh project load <name>")
            return
        for ext in ["yaml", "yml", "json"]:
            pf = projects_dir / f"{name}.{ext}"
            if pf.exists():
                proj_data = yaml.safe_load(pf.read_text()) if ext in ["yaml", "yml"] else __import__("json").loads(pf.read_text())
                cfg = load_config()
                cfg.current_project = name
                cfg.current_project_path = proj_data.get("path", ".")
                save_config(cfg)
                click.echo(f"Loaded project '{name}' (path: {cfg.current_project_path})")
                return
        click.echo(f"Project '{name}' not found.")


# --- session command ---

@cli.command(short_help="Session management")
@click.argument("action", type=click.Choice(["list", "load"]), default="list")
@click.argument("session_id", required=False, type=int)
def session(action, session_id):
    """Manage CDH sessions.

    \b
    Actions:
      list           List recent sessions
      load <id>      Load a session by ID

    \b
    Examples:
      cdh session          List recent sessions
      cdh session list     List recent sessions
      cdh session load 5   Load session with ID 5
    """
    import asyncio
    from tui.db import DB

    async def run():
        db = DB()
        if action == "list":
            recent = await db.session_get_recent(max_results=20)
            if not recent:
                click.echo("No sessions found.")
                return
            click.echo("Recent sessions:")
            for s in recent:
                title = s.get("title", "Untitled") or "Untitled"
                aid = s.get("agent_identity", "unknown")
                sid = s.get("agent_session_id", "")[:8]
                click.echo(f"  session-{s['id']}: {title} ({aid[:30]}... {sid})")
        elif action == "load":
            if session_id is None:
                click.echo("Usage: cdh session load <id>")
                return
            s = await db.session_get(session_id)
            if s is None:
                click.echo(f"Session {session_id} not found.")
                return
            click.echo(f"Session {session_id}:")
            click.echo(f"  Title: {s.get('title', 'Untitled')}")
            click.echo(f"  Agent: {s.get('agent_identity', 'unknown')}")
            click.echo(f"  Agent Session ID: {s.get('agent_session_id', 'N/A')}")

    asyncio.run(run())


# --- help command ---

# --- tui command ---

@cli.command(short_help="Launch the TUI")
@click.option("--project-dir", "-d", default=".", help="Project directory")
@click.option("--agent", "agent_identity", default=None, help="Agent identity to auto-launch (e.g. cdh.cloud-dev-harness)")
@click.pass_context
def tui(ctx, project_dir, agent_identity):
    """Launch the CDH TUI (Textual User Interface).

    By default opens the agent store, showing your configured launcher
    agents. Use --agent to skip the store and directly launch an agent.
    """
    ensure_dirs()
    cfg = load_config()
    setup_logging(cfg.log_level)

    ws = Path(project_dir).expanduser().resolve()

    from tui.app import A2TUIApp
    app = A2TUIApp(
        project_dir=str(ws),
        launch_agent_identity=agent_identity,
    )
    app.run()


# --- help command ---

@cli.command(short_help="Show help for commands")
@click.argument("command", required=False)
def help_cmd(command):
    """Show help for cdh commands and usage information.

    \b
    Examples:
      cdh help          Show top-level help
      cdh help config   Show config subcommand help
      cdh help logs     Show logs command help
    """
    if command:
        cmd = cli.commands.get(command)
        if cmd:
            click.echo(cmd.get_help(click.Context(cmd)))
        else:
            click.echo(f"Unknown command: {command}")
    else:
        click.echo(cli.get_help(click.Context(cli)))


# --- version command ---

@cli.command(short_help="Show version info")
def version():
    """Show CDH version and build information."""
    from cdha import __version__
    click.echo(f"cdh version {__version__}")


# Attach remaining cdha subcommands selectively
_skip = {"config", "init", "set", "list", "tui", "help", "version", "mcp"}
for cmd_name in cdha_cli.commands:
    if cmd_name in _skip:
        continue
    cli.add_command(cdha_cli.get_command(None, cmd_name))


def main():
    cli()


if __name__ == "__main__":
    main()
