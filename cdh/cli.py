from pathlib import Path
from typing import Optional

import click

from cdh.scaffold import (
    COMPONENTS,
    COMPONENT_BY_ID,
    CROSS_CUTTING,
    CROSS_CUTTING_BY_ID,
    add_component,
    add_cross_cutting,
    init_dlc_project,
    scaffold_dlc_project,
)
from onecode.cli import cli as onecode_cli
from onecode.cli import setup_logging
from onecode.config import ensure_dirs, load_config, save_config


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
  Config   ~/.cdh/onecode.config.yaml
  Logs     ~/.cdh/logs/
  Projects ~/.cdh/projects/
"""


@click.group(
    invoke_without_command=True,
    cls=type(onecode_cli),
    context_settings=dict(max_content_width=100),
    short_help="Cloud Dev Harness - AI agent framework with TUI.",
    epilog=_COMMON_HELP,
)
@click.version_option(version="1.0.0", prog_name="cdh")
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
        from onecode.config_screen import main as config_main
        config_main()


# Reuse subcommands from onecode's config group (mode, model, provider, cloud, log-level, skill, mcp, list)
for _cfg_cmd in onecode_cli.get_command(None, "config").commands.values():
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


def _parse_component_selection(text: str, valid_ids: list[str]) -> list[str]:
    """Parse '1,2,5' / '1-3' / 'all' / 'web,backend' / '' into a list of ids.

    Accepts either numeric tokens (positional, 1-based) or raw id names.
    Returns an empty list if no valid tokens are found.
    """
    text = text.strip().lower()
    if not text:
        return []
    if text in ("all", "*"):
        return list(valid_ids)
    tokens = [t.strip() for t in text.replace(" ", "").split(",") if t.strip()]
    selected: list[str] = []
    for tok in tokens:
        if tok in valid_ids:
            if tok not in selected:
                selected.append(tok)
            continue
        if "-" in tok:
            try:
                a, b = tok.split("-", 1)
                lo, hi = int(a), int(b)
            except ValueError:
                continue
            if lo > hi:
                lo, hi = hi, lo
            for i in range(lo, hi + 1):
                if 1 <= i <= len(valid_ids) and valid_ids[i - 1] not in selected:
                    selected.append(valid_ids[i - 1])
        else:
            try:
                idx = int(tok)
            except ValueError:
                continue
            if 1 <= idx <= len(valid_ids) and valid_ids[idx - 1] not in selected:
                selected.append(valid_ids[idx - 1])
    return selected


def _prompt_components(
    spec_label: str,
    specs: tuple,
    allow_empty: bool = False,
) -> list[str]:
    """Interactively prompt the user to choose from a list of specs.

    Args:
        spec_label: title describing what is being selected
                    (e.g. "application components").
        specs: a tuple of ComponentSpec or CrossCutSpec.
        allow_empty: if False, the user must select at least one and
                     the prompt will reject empty input.

    Returns a list of selected spec ids. Raises click.Abort if the user
    fails to provide a valid selection after the retry.
    """
    valid_ids = [s.id for s in specs]
    click.echo(f"Select {spec_label} for the project:")
    for i, s in enumerate(specs, 1):
        click.echo(f"  {i}) {s.label:<22s} \u2014 {s.description}")
    if allow_empty:
        hint = "[optional, e.g. 1,2 or 'all' or <Enter> to skip]"
    else:
        hint = "[required, e.g. 1,2 or 'all']"
    click.echo("")
    prompt_text = f"{spec_label.capitalize()} {hint}: "

    for attempt in range(2):
        raw = click.prompt(prompt_text, default="", show_default=False)
        selected = _parse_component_selection(raw, valid_ids)
        if selected:
            return selected
        if allow_empty and not raw.strip():
            return []
        if attempt == 0:
            if allow_empty:
                click.echo(
                    "No valid selection parsed. Try again (or press Enter to skip)."
                )
            else:
                click.echo(
                    "At least one selection is required. Try again."
                )
    raise click.Abort()


def _resolve_components_flag(components: Optional[str]) -> list[str]:
    """Resolve a --components flag value to a list of component ids.

    Empty/None means the caller will run the interactive prompt.
    'all' expands to every component id.
    """
    if not components:
        return []
    valid_ids = [c.id for c in COMPONENTS]
    selected = _parse_component_selection(components, valid_ids)
    if not selected:
        raise click.BadParameter(
            f"No valid component ids in '{components}'. "
            f"Valid ids: {', '.join(valid_ids)}."
        )
    return selected


def _load_project_record(name: str) -> Optional[dict]:
    """Read a project record from ~/.cdh/projects/{name}.{yaml,yml,json}."""
    import yaml as _yaml
    import json as _json
    projects_dir = _CDH_DIR / "projects"
    for ext in ("yaml", "yml", "json"):
        pf = projects_dir / f"{name}.{ext}"
        if pf.exists():
            text = pf.read_text(encoding="utf-8")
            if ext in ("yaml", "yml"):
                return _yaml.safe_load(text) or {}
            return _json.loads(text)
    return None


@cli.command(short_help="Project management (TUI)")
@click.argument("action", type=click.Choice(["list", "show", "new", "init", "load", "select", "add-component", "add-cross-cutting"]), default="select")
@click.argument("name", required=False)
@click.argument("path", required=False, default=".")
@click.option("--components", default=None, help="Comma-separated component ids (e.g. 'web,backend') or 'all'. Skips the interactive prompt.")
@click.option("--component", "component_id", default=None, help="Component id for add-component (e.g. 'native').")
@click.option("--id", "cross_id", default=None, help="Cross-cutting id for add-cross-cutting (e.g. 'contracts').")
def project(action, name, path, components, component_id, cross_id):
    """Manage CDH projects.

    \b
    Without arguments, opens the project management TUI.
    Use subcommands for quick CLI operations.

    \b
    Actions:
      select                          Open project management TUI (default)
      list                            List all projects
      show <name>                     Show project details
      new <name> [path]               Create a new project (interactive component selection)
      init [path]                     Initialize .cdh in an existing directory (interactive, allows empty)
      load <name>                     Load a project (set as current)
      add-component <name>            Add an application component to an existing project
      add-cross-cutting <name>        Add a cross-cutting item to an existing project
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
        return

    if action == "show":
        if not name:
            click.echo("Usage: cdh project show <name>")
            return
        for ext in ["yaml", "yml", "json"]:
            pf = projects_dir / f"{name}.{ext}"
            if pf.exists():
                click.echo(pf.read_text())
                return
        click.echo(f"Project '{name}' not found.")
        return

    if action == "new":
        from onecode.agent.cdh_loader import CdhProjectLoader
        if not name:
            name = click.prompt("Project name", default="").strip()
        if not name:
            click.echo("Project name is required.")
            raise click.Abort()
        ws = Path(path).expanduser().resolve()
        if components is not None:
            selected_components = _resolve_components_flag(components)
        else:
            selected_components = _prompt_components(
                "application components", COMPONENTS, allow_empty=False
            )
        try:
            scaffold_dlc_project(ws, name, components=selected_components)
        except ValueError as e:
            click.echo(f"Error: {e}")
            raise click.Abort()
        CdhProjectLoader.init_project(ws, name)
        proj_data = {"name": name, "path": str(ws), "description": ""}
        project_file = projects_dir / f"{name}.yaml"
        project_file.write_text(yaml.dump(proj_data))
        cfg = load_config()
        cfg.current_project = name
        cfg.current_project_path = str(ws)
        save_config(cfg)
        click.echo(
            f"Created project '{name}' at {ws} "
            f"(components: {', '.join(selected_components)})"
        )
        return

    if action == "init":
        from onecode.agent.cdh_loader import CdhProjectLoader
        target = Path(name or ".").expanduser().resolve()
        project_name = target.name
        if components is not None:
            selected_components = _resolve_components_flag(components)
        else:
            selected_components = _prompt_components(
                "application components", COMPONENTS, allow_empty=True
            )
        try:
            init_dlc_project(target, project_name)
        except ValueError as e:
            click.echo(f"Error: {e}")
            raise click.Abort()
        for cid in selected_components:
            add_component(target, cid)
        CdhProjectLoader.init_project(target, project_name)
        proj_data = {"name": project_name, "path": str(target), "description": ""}
        (projects_dir / f"{project_name}.yaml").write_text(yaml.dump(proj_data))
        suffix = (
            f" (components: {', '.join(selected_components)})"
            if selected_components
            else ""
        )
        click.echo(f"Initialized .cdh in {target}{suffix}")
        return

    if action == "add-component":
        if not name:
            click.echo("Usage: cdh project add-component <name> --component <id>")
            return
        if not component_id:
            click.echo("Usage: cdh project add-component <name> --component <id>")
            click.echo(f"Valid ids: {', '.join(c.id for c in COMPONENTS)}")
            return
        record = _load_project_record(name)
        if record is None:
            click.echo(f"Project '{name}' not found.")
            return
        ws = Path(record.get("path", ".")).expanduser().resolve()
        try:
            added = add_component(ws, component_id)
        except (ValueError, FileNotFoundError) as e:
            click.echo(f"Error: {e}")
            raise click.Abort()
        if added:
            click.echo(f"Added component '{component_id}' to '{name}'.")
        else:
            click.echo(f"Component '{component_id}' already present in '{name}'.")
        return

    if action == "add-cross-cutting":
        if not name:
            click.echo("Usage: cdh project add-cross-cutting <name> --id <id>")
            return
        if not cross_id:
            click.echo("Usage: cdh project add-cross-cutting <name> --id <id>")
            click.echo(f"Valid ids: {', '.join(c.id for c in CROSS_CUTTING)}")
            return
        record = _load_project_record(name)
        if record is None:
            click.echo(f"Project '{name}' not found.")
            return
        ws = Path(record.get("path", ".")).expanduser().resolve()
        try:
            added = add_cross_cutting(ws, cross_id)
        except (ValueError, FileNotFoundError) as e:
            click.echo(f"Error: {e}")
            raise click.Abort()
        if added:
            click.echo(f"Added cross-cutting '{cross_id}' to '{name}'.")
        else:
            click.echo(f"Cross-cutting '{cross_id}' already present in '{name}'.")
        return

    if action == "load":
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
    from onecode import __version__
    click.echo(f"cdh version {__version__}")


# Attach remaining onecode subcommands selectively
_skip = {"config", "init", "set", "list", "tui", "help", "version", "mcp"}
for cmd_name in onecode_cli.commands:
    if cmd_name in _skip:
        continue
    cli.add_command(onecode_cli.get_command(None, cmd_name))


def main():
    cli()


if __name__ == "__main__":
    main()
