from pathlib import Path
from typing import Optional

import click

from cdh.scaffold import (
    COMPONENTS,
    add_component,
    init_dlc_project,
    scaffold_dlc_project,
    check_dlc_project,
)
from cdh.cli_logging import setup_logging
from cdh.config import write_active_project
from onecode.cli import cli as onecode_cli
from onecode import __version__ as _VERSION


_CDH_DIR = Path.home() / ".cdh"

_COMMON_HELP = """
\b
Usage:
  cdh                              Launch TUI (agent store)
  cdh tui                          Launch TUI (agent store)
  cdh onecode <sub>                onecode CLI surface (config / codebase / skill / mcp / help)
  cdh aidc                         AIDC project management
  cdh session list|load            Session management
  cdh uninstall                    Remove ~/.cdh/ global state
  cdh version                      Show version information

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
@click.version_option(version=_VERSION, prog_name="cdh")
@click.pass_context
def cli(ctx):
    """
    CDH (Cloud Dev Harness) is an AI agent framework with LLM provider
    integration, session management, and a Textual-based TUI.

    Run without arguments to open the agent store, where you can pick
    a launcher agent.

    All onecode-specific commands live under `cdh onecode <sub>` — e.g.
    `cdh onecode config`, `cdh onecode codebase`, `cdh onecode skill`.
    """
    if ctx.invoked_subcommand is None:
        setup_logging("INFO")
        from tui.app import A2TUIApp
        A2TUIApp().run()


# --- onecode sub-namespace ---
#
# `cdh onecode <sub>` exposes the onecode CLI surface under the cdh
# namespace. The onecode group owns the canonical subcommands
# (config / codebase / skill / mcp / help); running
# `cdh onecode config` with no subcommand opens the same interactive
# TUI editor as before, while `cdh onecode config <sub>` dispatches
# straight to the onecode implementation.

@cli.group(
    "onecode",
    invoke_without_command=True,
    short_help="onecode CLI surface (config / codebase / skill / mcp / help)",
)
@click.pass_context
def onecode_group(ctx):
    """The onecode command surface.

    onecode is the agent framework that powers the TUI. This group
    exposes its full CLI: configuration, codebase indexing, skills,
    MCP servers, and help.

    \b
    Sub-commands:
      config       Manage onecode configuration (mode, model, provider, log-level, list)
      codebase     Build, search, and inspect the onecode codebase index
      skill        Install, enable, disable, or remove onecode skills
      mcp          Configure MCP servers that onecode connects to at runtime
      help         Print the onecode help screen
      version      Print the onecode version string

    \b
    Examples:
      cdh onecode config                  Open the onecode configuration editor
      cdh onecode config model get        Show the current default model
      cdh onecode config list             Dump the full YAML configuration
      cdh onecode config provider set openai
      cdh onecode codebase index          Build the onecode codebase index
      cdh onecode codebase search "auth flow"
      cdh onecode skill list              List installed onecode skills
      cdh onecode skill add my-skill      Scaffold a new onecode skill
      cdh onecode mcp list                List onecode MCP servers
      cdh onecode mcp add my-server https://example.com/mcp
    """
    if ctx.invoked_subcommand is None:
        # No subcommand: show the onecode help screen (matches
        # `onecode --help` so the user can browse what's available).
        click.echo(onecode_cli.get_help(click.Context(onecode_cli)))


# Mount every onecode top-level command (codebase / skill / mcp /
# help / version) under `cdh onecode <sub>`.  We deliberately skip
# `config` because the onecode CLI's bare `onecode config` only prints
# `--help`; the user-facing behaviour for `cdh onecode config` is to
# open the TUI editor, so we install our own config sub-group below.
_ONECODE_SKIP_AS_CDH_ONECODE = {"tui", "config"}
for _cmd_name in onecode_cli.commands:
    if _cmd_name in _ONECODE_SKIP_AS_CDH_ONECODE:
        continue
    _cmd = onecode_cli.get_command(None, _cmd_name)
    if _cmd is not None and _cmd_name not in onecode_group.commands:
        onecode_group.add_command(_cmd)


# Override the onecode CLI's CDH-flavoured help text so users see
# onecode-centric descriptions when they run `cdh onecode --help` or
# `cdh help onecode`.  The onecode CLI itself still ships its own copy
# (used by `onecode --help`); we don't mutate it.

_ONECODE_HELP_OVERRIDES: dict[str, tuple[str, str]] = {
    "config": (
        "Open the onecode configuration editor",
        "Manage onecode configuration: agent mode, default model, LLM "
        "provider, log level, skills, MCP servers. With no subcommand, "
        "launches the interactive Textual editor.",
    ),
    "codebase": (
        "Manage the onecode codebase index",
        "Build and query onecode's local codebase index. Used by the "
        "agent to ground answers in the project's own source files. "
        "Index stored at ~/.onecode/codebase/indexes/. "
        "Sub-commands: index, reindex, status, search.",
    ),
    "memory": (
        "Manage onecode long-term memory",
        "View and manage onecode's long-term conversation memory. "
        "Memory stored at ~/.onecode/memory/ with BM25 recall. "
        "Sub-commands: status, clear, count.",
    ),
    "skill": (
        "Manage onecode skills",
        "Install, enable, disable, or remove onecode skills. Skills are "
        "reusable instruction sets the agent loads on demand to extend "
        "its behaviour. Sub-commands: list, add, remove, enable, disable.",
    ),
    "mcp": (
        "Manage onecode MCP servers",
        "Configure Model Context Protocol servers that onecode connects "
        "to at runtime to expose additional tools and resources. "
        "Sub-commands: list, add, remove, enable, disable.",
    ),
    "help": (
        "Show onecode CLI help",
        "Print the onecode CLI help screen with every available command.",
    ),
    "version": (
        "Show onecode version",
        "Print the onecode version string.",
    ),
}

for _cmd_name, (_sh, _doc) in _ONECODE_HELP_OVERRIDES.items():
    _mounted = onecode_group.commands.get(_cmd_name)
    if _mounted is not None:
        _mounted.short_help = _sh
        _mounted.help = _doc


# `cdh onecode config` — wrapper around `onecode config` that opens the
# interactive TUI editor when invoked with no subcommand, and forwards
# every subcommand (mode / model / provider / skill / mcp / log-level /
# list) verbatim to onecode.

@onecode_group.group(
    "config",
    invoke_without_command=True,
    short_help="Open the onecode configuration editor (or run `cdh onecode config <sub>`)",
)
@click.pass_context
def onecode_config(ctx):
    """Open the onecode configuration editor.

    With a subcommand, get or set the corresponding onecode setting
    directly from the shell. With no subcommand, launch the interactive
    Textual editor for all onecode settings.

    \b
    Sub-commands:
      mode         Get or set onecode's default agent mode (build / plan / solo)
      model        Get or set onecode's default LLM model
      provider     Get or set onecode's default LLM provider
      log-level    Get or set onecode's root logger verbosity
      skill        Manage onecode skills (alias for `cdh onecode skill`)
      mcp          Manage onecode MCP servers (alias for `cdh onecode mcp`)
      list         Dump the full onecode YAML configuration

    \b
    Examples:
      cdh onecode config                  Open the interactive editor
      cdh onecode config model get        Show the current default model
      cdh onecode config provider set openai
      cdh onecode config list             Dump the full YAML configuration
    """
    if ctx.invoked_subcommand is None:
        from onecode.config_screen import main as config_main
        config_main()


_onecode_config_group = onecode_cli.get_command(None, "config")
if _onecode_config_group is not None:
    for _cfg_cmd in _onecode_config_group.commands.values():
        if _cfg_cmd.name not in onecode_config.commands and _cfg_cmd.name != "tui":
            onecode_config.add_command(_cfg_cmd)
            # Override the sub-command help to be onecode-centric, not
            # CDH-centric, since users reach these via
            # `cdh onecode config <sub>`.
            _sub_overrides = {
                "mode": (
                    "Manage onecode agent mode",
                    "Get or set onecode's default agent mode "
                    "(build / plan / solo).",
                ),
                "model": (
                    "Manage onecode's default LLM model",
                    "Get or set the default LLM model onecode uses when "
                    "starting a new agent session.",
                ),
                "provider": (
                    "Manage onecode's default LLM provider",
                    "Get or set the default LLM provider onecode routes "
                    "chat-completions requests to.",
                ),
                "log-level": (
                    "Manage onecode log level",
                    "Get or set onecode's root logger verbosity "
                    "(debug / info / warn / error).",
                ),
                "skill": (
                    "Manage onecode skills (alias for `cdh onecode skill`)",
                    "Same skill-management surface as `cdh onecode skill`.",
                ),
                "mcp": (
                    "Manage onecode MCP servers (alias for `cdh onecode mcp`)",
                    "Same MCP server surface as `cdh onecode mcp`.",
                ),
                "list": (
                    "Show onecode's full YAML configuration",
                    "Print every onecode setting currently in effect, "
                    "as YAML.",
                ),
            }
            if _cfg_cmd.name in _sub_overrides:
                _sh, _doc = _sub_overrides[_cfg_cmd.name]
                _cfg_cmd.short_help = _sh
                _cfg_cmd.help = _doc


# --- (removed) backward-compatible aliases ---
#
# Earlier versions exposed `cdh config` and `cdh codebase` at the top
# level. Those aliases were removed — use `cdh onecode config` and
# `cdh onecode codebase` instead. The behaviour is identical:
# - `cdh onecode config` (no subcommand) opens the same TUI editor.
# - `cdh onecode config <sub>` is the same as the old `cdh config <sub>`.
# - `cdh onecode codebase <sub>` is the same as the old `cdh codebase <sub>`.


# --- aidc (AIDC project) command ---

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


def _parse_component_selection(text: str, valid_ids: list[str]) -> list[str]:
    valid_ids = list(valid_ids)
    text = text.strip().lower()
    if not text:
        return []
    if text in ("all", "*"):
        return valid_ids
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


@cli.command("aidc", short_help="AIDC project management")
@click.argument("action", type=click.Choice(["new", "init", "check", "list", "load"]))
@click.argument("name", required=False)
@click.argument("path", required=False, default=".")
@click.option("--components", default=None, help="Comma-separated component ids (e.g. 'web,backend') or 'all'. Skips the interactive prompt.")
def aidc(action, name, path, components):
    """Manage AIDC projects.

    \b
    Actions:
      new <name> [path]    Create a new AIDC project (interactive component selection)
      init [path]          Initialize .cdh in an existing directory as an AIDC project
      check [path]         Check whether a directory is a valid AIDC project
      list                 List all registered AIDC projects
      load <name>          Load a registered AIDC project as the current project
    """
    import yaml
    projects_dir = _CDH_DIR / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)

    if action == "list":
        project_files = sorted(list(projects_dir.glob("*.yaml")) + list(projects_dir.glob("*.json")))
        if not project_files:
            click.echo("No projects found.")
            return
        click.echo("Projects:")
        for pf in project_files:
            click.echo(f"  {pf.stem}")
        return

    if action == "new":
        from cdh.project_loader import CdhProjectLoader
        if not name:
            name = click.prompt("Project name", default="").strip()
        if not name:
            click.echo("Project name is required.")
            raise click.Abort()
        ws = Path(path).expanduser().resolve()
        project_file = projects_dir / f"{name}.yaml"
        if project_file.exists():
            click.echo(f"Error: project '{name}' already exists in the project list.")
            raise click.Abort()
        if components is not None:
            selected_components = _resolve_components_flag(components)
        else:
            selected_components = _prompt_components(
                "application components", COMPONENTS, allow_empty=False
            )
        try:
            scaffold_dlc_project(ws, name, components=selected_components)
        except (ValueError, RuntimeError) as e:
            click.echo(f"Error: {str(e) or type(e).__name__}")
            raise click.Abort()
        CdhProjectLoader.init_project(ws, name)
        proj_data = {"name": name, "path": str(ws), "description": ""}
        project_file.write_text(yaml.dump(proj_data))
        write_active_project(name, str(ws))
        click.echo(
            f"Created AIDC project '{name}' at {ws} "
            f"(components: {', '.join(selected_components)})"
        )
        return

    if action == "init":
        from cdh.project_loader import CdhProjectLoader
        target = Path(name or ".").expanduser().resolve()
        project_name = target.name
        proj_file = projects_dir / f"{project_name}.yaml"
        if proj_file.exists():
            click.echo(f"Error: project '{project_name}' already exists in the project list.")
            raise click.Abort()
        if components is not None:
            selected_components = _resolve_components_flag(components)
        else:
            selected_components = _prompt_components(
                "application components", COMPONENTS, allow_empty=True
            )
        try:
            init_dlc_project(target, project_name)
        except (ValueError, RuntimeError) as e:
            click.echo(f"Error: {str(e) or type(e).__name__}")
            raise click.Abort()
        for cid in selected_components:
            try:
                add_component(target, cid)
            except (ValueError, FileNotFoundError) as e:
                click.echo(f"Error: {str(e) or type(e).__name__}")
        CdhProjectLoader.init_project(target, project_name)
        proj_data = {"name": project_name, "path": str(target), "description": ""}
        proj_file.write_text(yaml.dump(proj_data))
        suffix = (
            f" (components: {', '.join(selected_components)})"
            if selected_components
            else ""
        )
        click.echo(f"Initialized AIDC project in {target}{suffix}")
        return

    if action == "check":
        from cdh.scaffold import check_dlc_project
        target = Path(name or ".").expanduser().resolve()
        result = check_dlc_project(target)
        if result["valid"]:
            click.echo(f"\u2713 Valid AIDC project: {result['name']}")
            click.echo(f"  Location: {result['path']}")
            if result["components"]:
                click.echo(f"  Components: {', '.join(result['components'])}")
            else:
                click.echo("  Components: (none)")
            click.echo(
                f"  CDH state: \u2713 initialized" if result["has_cdh"]
                else "  CDH state: \u2717 not initialized"
            )
        else:
            click.echo(f"\u2717 Not a valid AIDC project: {target}")
        for s in result["suggestions"]:
            click.echo(f"  \u2022 {s}")
        return

    if action == "load":
        if not name:
            click.echo("Usage: cdh aidc load <name>")
            return
        for ext in ["yaml", "yml", "json"]:
            pf = projects_dir / f"{name}.{ext}"
            if pf.exists():
                proj_data = yaml.safe_load(pf.read_text()) if ext in ["yaml", "yml"] else __import__("json").loads(pf.read_text())
                project_path = proj_data.get("path", ".")
                write_active_project(name, project_path)
                click.echo(f"Loaded project '{name}' (path: {project_path})")
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
            s = None
            try:
                s = await db.session_get(int(session_id))
            except (ValueError, TypeError):
                pass
            if s is None:
                s = await db.session_get_by_agent_session_id(session_id)
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
@click.pass_context
def tui(ctx, project_dir):
    """Launch the CDH TUI (Textual User Interface).

    By default opens the agent store, showing your configured launcher
    agents. Pick an agent from the store to launch it.
    """
    setup_logging("INFO")

    ws = Path(project_dir).expanduser().resolve()

    from tui.app import A2TUIApp
    app = A2TUIApp(project_dir=str(ws))
    app.run()


# --- help command ---

@cli.command(short_help="Show help for commands")
@click.argument("command", required=False)
def help_cmd(command):
    """Show help for cdh commands and usage information.

    \b
    Examples:
      cdh help                       Show top-level help
      cdh help onecode               Show `cdh onecode` sub-commands
      cdh help onecode config        Show config sub-commands
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

@cli.command(short_help="Remove ~/.cdh/ global state")
def uninstall():
    """Remove CDH global state (~/.cdh/) and Python environment.

    \b
    After running this, uninstall the package itself:
      pip uninstall cloud-dev-harness   (if installed via pip)
      pnpm remove -g @scemoon/cdh       (if installed via pnpm)
      npm uninstall -g @scemoon/cdh     (if installed via npm)

    \b
    Also check your shell config (~/.zshrc, ~/.bashrc, etc.) for
    PATH entries pointing to ~/.cdh/python/bin and remove them.
    """
    import shutil

    cdh_dir = Path.home() / ".cdh"

    removed_anything = False

    python_dir = cdh_dir / "python"
    if python_dir.exists():
        click.echo(f"Removing Python environment at {python_dir}...")
        shutil.rmtree(python_dir, ignore_errors=True)
        removed_anything = True

    if cdh_dir.exists():
        click.echo(f"Removing global state at {cdh_dir}...")
        shutil.rmtree(cdh_dir, ignore_errors=True)
        removed_anything = True

    if not removed_anything:
        click.echo("Nothing to remove (~/.cdh/ not found).")
    else:
        click.echo("")
        click.echo("Cleanup complete. To finish uninstall:")
        click.echo("")
        click.echo("  1. Remove the package:")
        click.echo("     pip uninstall cloud-dev-harness")
        click.echo("     # or: pnpm remove -g @scemoon/cdh")
        click.echo("     # or: npm uninstall -g @scemoon/cdh")
        click.echo("")
        click.echo("  2. Check your shell config (~/.zshrc, ~/.bashrc, etc.) for:")
        click.echo('     export PATH="$HOME/.cdh/python/bin:$PATH"')
        click.echo("     Remove this line if present.")


@cli.command(short_help="Show version info")
def version():
    """Show CDH version and build information."""
    from onecode import __version__
    click.echo(f"cdh version {__version__}")


# All onecode subcommands are reachable through `cdh onecode <sub>`
# (see the onecode_group defined above). The cdh top-level command
# surface is intentionally limited to: tui, onecode, project, session,
# help, and version.


def main():
    cli()


if __name__ == "__main__":
    main()
