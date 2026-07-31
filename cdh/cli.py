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
from cdh.validators import run_ears_check, run_fr_check, run_bdd_check, run_dag_check
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
  cdh aidlc [project|phase|gate|sync|update]   AIDLC project management
   cdh session list|load            Session management
   cdh trace list|view|dashboard    Trace management (agenttrace)
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


# --- aidlc group (project / phase / gate / sync / update) ---

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


@cli.group("aidlc", short_help="AIDLC project management", invoke_without_command=True)
@click.pass_context
def aidlc(ctx):
    """Manage AIDLC projects.

    \b
    Sub-commands:
      project list|new|init|check|load    Project management
      phase <phase>                       Set the AI-DLC phase
      gate <name> --status <passed|failed> Record a quality gate result
      validate                            Validate spec quality (EARS/FR/BDD/DAG)
      generators list|search|info|install|init|validate  Manage code-generator plugins
      tools install|status|update         Manage AIDLC tools (generate_shared/contract_diff/deploy_stack)
      status                              Show project health overview
      dashboard [--watch] [--export PATH] Render the AIDLC dashboard TUI
      config show|component|provider      Manage project configuration
      sync                                Regenerate AGENTS.md and CLAUDE.md
      update                              Alias for sync (deprecated)
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@aidlc.command("dashboard")
@click.argument("path", required=False, default=".")
@click.option("--watch", "-w", is_flag=True, default=False, help="Refresh every --interval seconds (Ctrl-C to stop).")
@click.option("--interval", "-n", default=2.0, type=float, show_default=True, help="Refresh interval in seconds (--watch).")
@click.option("--export", "export_path", default=None, type=click.Path(), help="Write a one-shot snapshot to PATH (.md or .html) instead of TUI.")
def dashboard_cmd(path, watch, interval, export_path):
    """Render the AIDLC dashboard TUI.

    Auto-detects the .cdh/ directory by walking up from PATH (default: cwd)
    and shows six widgets in a 2x3 grid:

      * Phase Progress    - current AI-DLC phase + progress bar
      * Quality Gates     - pass/fail/warn icons for recorded gates
      * Spec Quality      - EARS/FR/BDD/DAG check pass rates
      * AIDLC Tools       - installed vs stub tools
      * FR Coverage       - spec FR -> BDD coverage percentage
      * Deployment        - preview/staging/production env status

    Use --watch for live refresh, or --export PATH to save a snapshot
    (Markdown by default; .html for HTML).

    \b
    Examples:
      cdh aidlc dashboard                       One-shot render
      cdh aidlc dashboard --watch               Live refresh every 2s
      cdh aidlc dashboard --watch --interval 5  Live refresh every 5s
      cdh aidlc dashboard --export report.md    Save Markdown snapshot
      cdh aidlc dashboard --export report.html Save HTML snapshot
    """
    from cdh.tui import run_dashboard

    target = Path(path).expanduser().resolve()
    export = Path(export_path).expanduser().resolve() if export_path else None
    setup_logging("WARNING")
    rc = run_dashboard(
        target,
        watch=watch,
        interval=interval,
        export_path=export,
    )
    if rc:
        raise click.Abort()


@aidlc.group("project", short_help="Project management (list/new/init/check/load)", invoke_without_command=True)
@click.pass_context
def project(ctx):
    """Manage AIDLC projects.

    Without subcommand, opens the project management TUI.

    \b
    Sub-commands:
      list                 List all registered projects
      new <name> [path]    Create a new project
      init [path]          Initialize .cdh in an existing directory
      check [path]         Check whether a directory is a valid AIDLC project
      load <name>          Load a registered project as the current project
    """
    if ctx.invoked_subcommand is None:
        from tui.screens.projects_app import main as projects_main
        projects_main()


@project.command("list")
def project_list():
    """List all registered AIDLC projects."""
    projects_dir = _CDH_DIR / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    project_files = sorted(list(projects_dir.glob("*.yaml")) + list(projects_dir.glob("*.json")))
    if not project_files:
        click.echo("No projects found.")
        return
    click.echo("Projects:")
    for pf in project_files:
        click.echo(f"  {pf.stem}")


@project.command("new")
@click.argument("name", required=False)
@click.argument("path", required=False, default=".")
@click.option("--components", default=None, help="Comma-separated component ids (e.g. 'web,backend') or 'all'. Skips the interactive prompt.")
@click.option("--with-ci", is_flag=True, default=False, help="Generate CI templates (GitHub Actions + pre-commit)")
@click.option("--with-tests", is_flag=True, default=False, help="Generate test templates (conftest.py, pyproject.toml)")
@click.option("--with-local", is_flag=True, default=False, help="Generate local dev templates (docker-compose.yaml, .env.local)")
@click.option("--provider", default=None, help="Cloud provider: tcb (default) or aliyun")
def project_new(name, path, components, with_ci, with_tests, with_local, provider):
    """Create a new AIDLC project with interactive component selection."""
    import yaml
    from cdh.project_loader import CdhProjectLoader
    projects_dir = _CDH_DIR / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
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
        scaffold_dlc_project(
            ws, name, components=selected_components,
            with_ci=with_ci, with_tests=with_tests,
            with_local=with_local, provider=provider,
        )
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


@project.command("init")
@click.argument("path", required=False, default=".")
@click.option("--components", default=None, help="Comma-separated component ids (e.g. 'web,backend') or 'all'. Skips the interactive prompt.")
@click.option("--with-ci", is_flag=True, default=False, help="Generate CI templates (GitHub Actions + pre-commit)")
@click.option("--with-tests", is_flag=True, default=False, help="Generate test templates (conftest.py, pyproject.toml)")
@click.option("--with-local", is_flag=True, default=False, help="Generate local dev templates (docker-compose.yaml, .env.local)")
@click.option("--provider", default=None, help="Cloud provider: tcb (default) or aliyun")
def project_init(path, components, with_ci, with_tests, with_local, provider):
    """Initialize .cdh in an existing directory as an AIDLC project."""
    import yaml
    from cdh.project_loader import CdhProjectLoader
    from cdh.scaffold import _scaffold_ci_templates, _scaffold_test_templates, _scaffold_local_env, _scaffold_provider_templates
    projects_dir = _CDH_DIR / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    target = Path(path).expanduser().resolve()
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
        init_dlc_project(target, project_name, with_ci=with_ci, with_tests=with_tests, with_local=with_local, provider=provider)
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


@project.command("check")
@click.argument("path", required=False, default=".")
def project_check(path):
    """Check whether a directory is a valid AIDLC project."""
    from cdh.scaffold import check_dlc_project
    target = Path(path).expanduser().resolve()
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


@project.command("load")
@click.argument("name", required=False)
def project_load(name):
    """Load a registered AIDLC project as the current project."""
    import yaml
    projects_dir = _CDH_DIR / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    if not name:
        click.echo("Usage: cdh aidlc project load <name>")
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


@aidlc.command("phase")
@click.argument("phase", required=False)
@click.argument("path", required=False, default=".")
def phase_cmd(phase, path):
    """Set the current AI-DLC phase (init|understand|plan|verify|deliver)."""
    from cdh.project_loader import CdhProjectLoader
    valid = {"init", "understand", "plan", "verify", "deliver"}
    if not phase or phase not in valid:
        click.echo(f"Usage: cdh aidlc phase <{'|'.join(sorted(valid))}>")
        raise click.Abort()
    target = Path(path).expanduser().resolve()
    ok = CdhProjectLoader.advance_phase(target, phase)
    if ok:
        click.echo(f"Phase set to: {phase}")
    else:
        click.echo(
            "Error: Invalid phase transition. "
            "Phases must advance one step at a time "
            "(init\u2192understand\u2192plan\u2192verify\u2192deliver). "
            "Use 'init' to reset."
        )
        raise click.Abort()


@aidlc.command("gate")
@click.argument("name", required=False)
@click.argument("path", required=False, default=".")
@click.option("--status", required=True, help="Gate status: passed or failed")
def gate_cmd(name, path, status):
    """Record a quality gate result (requires --status passed|failed)."""
    from cdh.project_loader import CdhProjectLoader
    if not name or status not in ("passed", "failed"):
        click.echo("Usage: cdh aidlc gate <name> --status <passed|failed>")
        raise click.Abort()
    target = Path(path).expanduser().resolve()
    ok = CdhProjectLoader.record_gate_result(target, name, status)
    if ok:
        click.echo(f"Gate '{name}': {status}")
    else:
        click.echo("No .cdh/ directory found. Run 'cdh aidlc init' first.")


@aidlc.command("sync")
@click.argument("path", required=False, default=".")
def sync_cmd(path):
    """Regenerate AGENTS.md and CLAUDE.md from aidlc/project.yaml."""
    from cdh.scaffold import _regenerate_agents_and_claude_md, scaffold_dlc_project
    from cdh.project_loader import CdhProjectLoader
    target = Path(path).expanduser().resolve()
    project_yaml = target / "aidlc" / "project.yaml"
    if project_yaml.exists():
        _regenerate_agents_and_claude_md(target)
        click.echo("Regenerated AGENTS.md and CLAUDE.md")
    else:
        project_name = target.name
        scaffold_dlc_project(target, project_name)
        CdhProjectLoader.init_project(target, project_name)
        click.echo("Initialized AIDC project and regenerated AGENTS.md/CLAUDE.md")


@aidlc.command("update")
@click.argument("path", required=False, default=".")
@click.pass_context
def update_cmd(ctx, path):
    """Alias for sync (deprecated)."""
    ctx.invoke(sync_cmd, path=path)


# ── validate ─────────────────────────────────────────────────


@aidlc.group("validate", short_help="Validate AIDLC spec quality", invoke_without_command=True)
@click.pass_context
def validate_group(ctx):
    """Validate AIDLC spec quality: EARS, FR, BDD, DAG.

    \b
    Sub-commands:
      run                 Run all quality checks (default)
      history             Show recent validate runs
      metrics             Show aggregated validate metrics
    """
    if ctx.invoked_subcommand is None:
        # Default: run all checks with default options
        ctx.invoke(validate_cmd, path=".", ears_only=False, fr_only=False,
                   bdd_only=False, dag_only=False, all_checks=True,
                   output_format="text", record=True, validate_state=True)


@validate_group.command("run")
@click.argument("path", required=False, default=".")
@click.option("--ears", "ears_only", is_flag=True, help="EARS format check only")
@click.option("--fr", "fr_only", is_flag=True, help="FR namespace consistency check only")
@click.option("--bdd", "bdd_only", is_flag=True, help="BDD scenario coverage check only")
@click.option("--dag", "dag_only", is_flag=True, help="Task DAG cycle check only")
@click.option("--all", "all_checks", is_flag=True, default=False, help="Run all checks (default)")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", help="Output format (default: text)")
@click.option("--record/--no-record", "record", default=True, help="Persist run history & metrics (default: record)")
@click.option("--validate-state", is_flag=True, help="Validate .cdh/state.json schema")
@click.pass_context
def validate_cmd(ctx, path, ears_only, fr_only, bdd_only, dag_only, all_checks, output_format, record, validate_state):
    """Run all AIDLC spec quality checks."""
    _validate_impl(ctx, path, ears_only, fr_only, bdd_only, dag_only, all_checks, output_format, record, validate_state)


@validate_group.command("history")
@click.argument("path", required=False, default=".")
@click.option("--last", "n", default=10, show_default=True, help="Show last N runs")
def validate_history_cmd(path, n):
    """Show recent validate runs recorded in .cdh/validate_history.json."""
    from cdh.project_loader import CdhProjectLoader

    target = Path(path).expanduser().resolve()
    cdh_dir = CdhProjectLoader.find_cdh_dir(target)
    if cdh_dir is None:
        click.echo("No .cdh/ directory found.")
        return

    history = CdhProjectLoader.get_validate_history(cdh_dir)
    if not history:
        click.echo("No validate history recorded yet. Run 'cdh aidlc validate' to populate.")
        return

    recent = history[-n:]
    click.echo(f"Last {len(recent)} of {len(history)} runs:\n")
    click.echo(f"  {'TIMESTAMP':<22}  {'PASS':<6}  {'DUR(ms)':<8}  CHECKS")
    click.echo(f"  {'─' * 22}  {'─' * 6}  {'─' * 8}  {'─' * 30}")
    for entry in recent:
        ts = entry.get("timestamp", "?")
        passed = "✓" if entry.get("passed") else "✗"
        dur = entry.get("duration_ms", 0)
        checks = ", ".join(entry.get("checks_run", [])) or "-"
        failed = entry.get("failed_checks", [])
        if failed:
            checks = f"{checks}  (failed: {', '.join(failed)})"
        click.echo(f"  {ts:<22}  {passed:<6}  {dur:<8}  {checks}")


@validate_group.command("metrics")
@click.argument("path", required=False, default=".")
def validate_metrics_cmd(path):
    """Show aggregated metrics across all recorded validate runs."""
    from cdh.project_loader import CdhProjectLoader

    target = Path(path).expanduser().resolve()
    cdh_dir = CdhProjectLoader.find_cdh_dir(target)
    if cdh_dir is None:
        click.echo("No .cdh/ directory found.")
        return

    metrics = CdhProjectLoader.get_metrics(cdh_dir)
    if not metrics:
        click.echo("No metrics recorded yet. Run 'cdh aidlc validate' to populate.")
        return

    click.echo("Validate Metrics:\n")
    click.echo(f"  Total runs:           {metrics.get('total_runs', 0)}")
    click.echo(f"  Avg duration (ms):    {metrics.get('average_duration_ms', 0)}")
    ts = metrics.get("last_run_timestamp", "?")
    click.echo(f"  Last run:             {ts}")

    per_check = metrics.get("per_check", {})
    if per_check:
        click.echo("\n  Per-check pass/fail:")
        click.echo(f"    {'CHECK':<30}  {'RUNS':<6}  {'PASS':<6}  {'FAIL':<6}")
        for name, slot in per_check.items():
            click.echo(
                f"    {name:<30}  {slot.get('runs', 0):<6}  "
                f"{slot.get('passes', 0):<6}  {slot.get('fails', 0):<6}"
            )

    mttd = metrics.get("mttd_per_check", {})
    if mttd:
        click.echo("\n  MTTD per check (ms-to-first-failure):")
        for name, slot in mttd.items():
            click.echo(
                f"    {name:<30}  mttd={slot.get('mttd_ms', '?')}ms "
                f"(samples={slot.get('samples', 0)})"
            )


def _validate_impl(ctx, path, ears_only, fr_only, bdd_only, dag_only, all_checks, output_format, record, validate_state=False):
    """Run all AIDLC spec quality checks.

    Helper used by both `cdh aidlc validate` and `cdh aidlc validate run`.
    """
    import json as json_module
    import time
    from datetime import datetime, timezone
    from cdh.project_loader import CdhProjectLoader

    target = Path(path).expanduser().resolve()

    selected = []
    if ears_only:
        selected = ["ears"]
    elif fr_only:
        selected = ["fr"]
    elif bdd_only:
        selected = ["bdd"]
    elif dag_only:
        selected = ["dag"]
    else:
        selected = ["ears", "fr", "bdd", "dag"]

    runners = {
        "ears": ("EARS Format", run_ears_check),
        "fr": ("FR Namespace", run_fr_check),
        "bdd": ("BDD Coverage", run_bdd_check),
        "dag": ("Task DAG", run_dag_check),
    }

    started_at = time.monotonic()
    started_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # OTLP span instrumentation — wraps the whole validate run in a parent span
    # and each individual check in its own child span. Works with or without the
    # opentelemetry-api package; see cdh.trace.otel_tracer.
    from cdh.trace.otel_tracer import init_tracer, span as otel_span

    init_tracer(service_name="cdh-validate")

    all_passed = True
    results = {}
    run_span_attrs = {
        "cdh.path": str(target),
        "cdh.checks_requested": ",".join(selected),
        "cdh.output_format": output_format,
    }
    with otel_span("aidlc.validate", attributes=run_span_attrs) as run_span:
        for key in selected:
            label, runner = runners[key]
            check_started = time.monotonic()
            with otel_span(
                f"aidlc.validate.{key}",
                attributes={"cdh.check.name": label, "cdh.check.kind": key},
                parent=run_span,
            ) as check_span:
                try:
                    result = runner(target)
                except Exception as exc:
                    check_span.record_exception(exc)
                    check_span.set_status("ERROR", str(exc))
                    raise
                results[key] = result
                check_ms = int((time.monotonic() - check_started) * 1000)
                check_span.set_attribute("cdh.check.passed", bool(result["passed"]))
                check_span.set_attribute("cdh.check.duration_ms", check_ms)
                sub_checks = result.get("checks", [])
                check_span.set_attribute("cdh.check.sub_count", len(sub_checks))
                failed_sub = [
                    c.get("name", "?") for c in sub_checks if c.get("status") == "fail"
                ]
                if failed_sub:
                    check_span.set_attribute(
                        "cdh.check.failed_subs", ",".join(failed_sub)
                    )
                fr_count = sum(
                    int(c.get("fr_count", 0))
                    for c in sub_checks
                    if isinstance(c.get("fr_count"), int)
                )
                if fr_count:
                    check_span.set_attribute("cdh.check.fr_count", fr_count)
                bdd_count = sum(
                    int(c.get("scenario_count", 0))
                    for c in sub_checks
                    if isinstance(c.get("scenario_count"), int)
                )
                if bdd_count:
                    check_span.set_attribute(
                        "cdh.check.bdd_scenario_count", bdd_count
                    )
                check_span.set_status("OK" if result["passed"] else "ERROR")

            if not result["passed"]:
                all_passed = False

            if output_format == "json":
                continue

            click.echo(f"\n── {label} ─{'─' * max(0, 48 - len(label))}")
            click.echo(f"  Result: {'✓ PASS' if result['passed'] else '✗ FAIL'}")

            for check in result.get("checks", []):
                icon = {"pass": "✓", "fail": "✗", "warn": "!"}.get(
                    check["status"], "?"
                )
                click.echo(f"  {icon} {check['name']}: {check['message']}")

            if not result["passed"]:
                all_passed = False

        run_span.set_attribute("cdh.validate.duration_ms", int((time.monotonic() - started_at) * 1000))
        run_span.set_attribute("cdh.validate.passed", all_passed)
        run_span.set_attribute(
            "cdh.validate.checks_run",
            sum(len(results[k].get("checks", [])) for k in selected),
        )
        run_span.set_status("OK" if all_passed else "ERROR")

    if validate_state:
        cdh_dir = CdhProjectLoader.find_cdh_dir(target)
        state_valid, state_errors = (False, ["No .cdh/ directory found."]) if cdh_dir is None else CdhProjectLoader.validate_state_schema(cdh_dir)
        if output_format != "json":
            click.echo(f"\n── State Schema ─────────────────────────────────")
            click.echo(f"  Result: {'✓ PASS' if state_valid else '✗ FAIL'}")
            for error in state_errors:
                click.echo(f"  ✗ {error}")
        if not state_valid:
            all_passed = False


    failed_checks: list[str] = []
    checks_run: list[str] = []
    duration_ms = int((time.monotonic() - started_at) * 1000)
    for key in selected:
        for check in results[key].get("checks", []):
            name = check.get("name", key)
            checks_run.append(name)
            if check.get("status") == "fail":
                failed_checks.append(name)

    if record:
        cdh_dir = CdhProjectLoader.find_cdh_dir(target)
        if cdh_dir is not None:
            history_entry = {
                "timestamp": started_iso,
                "checks_run": checks_run,
                "passed": all_passed,
                "duration_ms": duration_ms,
                "failed_checks": failed_checks,
            }
            try:
                CdhProjectLoader.append_validate_history(cdh_dir, history_entry)
                CdhProjectLoader.record_metrics(cdh_dir, history_entry)
            except Exception as exc:
                click.echo(f"  (warn) failed to persist history/metrics: {exc}", err=True)

    if output_format == "json":
        summary = {
            "passed": all_passed,
            "duration_ms": duration_ms,
            "checks": {
                key: {
                    "passed": results[key]["passed"],
                    "checks": results[key].get("checks", []),
                }
                for key in selected
            },
        }
        click.echo(json_module.dumps(summary, indent=2, ensure_ascii=False))
        if not all_passed:
            raise click.Abort()
        return

    if all_passed:
        click.echo(f"\n{'=' * 52}\n  All checks passed ✓")
    else:
        click.echo(f"\n{'=' * 52}\n  Some checks failed — review the {''}above")
        raise click.Abort()


# ── check (pattern detection) ─────────────────────────────────


@aidlc.group("check", short_help="Pattern detection (Semgrep-style)")
@click.pass_context
def check_group(ctx):
    """Run Semgrep-style pattern detection for brownfield migration and code quality.

    \b
    Sub-commands:
      patterns           Scan for code patterns matching built-in or custom rules
      rules              List available pattern rule categories
    """
    pass


@check_group.command("patterns", short_help="Scan for code patterns")
@click.argument("path", required=False, default=".")
@click.option(
    "--rules",
    "-r",
    "rules_file",
    type=click.Path(),
    default=None,
    help="Path to rules file (YAML/JSON). Default: built-in rules.",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json", "sarif"]),
    default="text",
    help="Output format (default: text). sarif for GitHub/code scanning.",
)
@click.option(
    "--severity",
    "-s",
    "min_severity",
    type=click.Choice(["INFO", "WARNING", "ERROR"]),
    default="INFO",
    help="Minimum severity to report",
)
@click.option(
    "--exclude",
    "-e",
    "exclude_paths",
    multiple=True,
    help="Paths/patterns to exclude (repeatable)",
)
@click.option("--fail-on-error", is_flag=True, help="Exit non-zero if any ERROR finding")
def check_patterns_cmd(path, rules_file, output_format, min_severity, exclude_paths, fail_on_error):
    """Scan source files for pattern matches using Semgrep-style rules.

    \b
    Examples:
      cdh aidlc check patterns src/
      cdh aidlc check patterns --rules my-rules.yaml --format json src/
      cdh aidlc check patterns --severity WARNING --exclude "**/test/**" src/

    Rules are loaded from (in order):
      1. --rules FILE (if specified)
      2. ~/.cdh/rules/patterns.yaml (if exists)
      3. Built-in cdh/rules/patterns.yaml
    """
    import os
    import json as json_module
    from pathlib import Path

    from cdh.tools.pattern_detect import PatternEngine, load_rules, Finding

    target = Path(path).expanduser().resolve()
    if not target.exists():
        click.echo(f"Error: Path not found: {target}", err=True)
        raise click.Abort()

    rules_path = rules_file
    if rules_path is None:
        user_rules = Path.home() / ".cdh" / "rules" / "patterns.yaml"
        if user_rules.is_file():
            rules_path = str(user_rules)
        else:
            rules_path = str(Path(__file__).parent.parent / "rules" / "patterns.yaml")

    rules = load_rules(rules_path) if rules_path else []
    if not rules:
        click.echo("Warning: No rules loaded. Pattern detection skipped.", err=True)
        return

    engine = PatternEngine(rules)
    findings = engine.scan(
        [str(target)],
        exclude_paths=list(exclude_paths),
        gitignore=True,
    )

    severity_order = {"INFO": 0, "WARNING": 1, "ERROR": 2}
    min_level = severity_order.get(min_severity, 0)
    filtered = [f for f in findings if severity_order.get(f.severity, 0) >= min_level]

    if output_format == "json":
        result = {
            "results": [f.to_dict() for f in filtered],
            "total": len(filtered),
            "rules_loaded": len(rules),
        }
        click.echo(json_module.dumps(result, indent=2))
        if fail_on_error and any(f.severity == "ERROR" for f in filtered):
            raise click.Abort()
        return

    if output_format == "sarif":
        sarif = _to_sarif(filtered, rules_path or "built-in")
        click.echo(json_module.dumps(sarif, indent=2))
        if fail_on_error and any(f.severity == "ERROR" for f in filtered):
            raise click.Abort()
        return

    # Text format
    if not filtered:
        click.echo("No findings. Pattern detection passed.")
        return

    error_count = sum(1 for f in filtered if f.severity == "ERROR")
    warn_count = sum(1 for f in filtered if f.severity == "WARNING")
    info_count = sum(1 for f in filtered if f.severity == "INFO")

    click.echo(f"\nPattern Detection Summary:")
    click.echo(f"  Rules loaded: {len(rules)}")
    click.echo(f"  Files scanned: {len(set(f.file for f in filtered))}")
    click.echo(f"  Findings: {error_count} errors, {warn_count} warnings, {info_count} info")
    click.echo(f"\n{'=' * 70}")

    for f in sorted(filtered, key=lambda x: (severity_order.get(x.severity, 0), x.file, x.line)):
        sev_indicator = {"INFO": "I", "WARNING": "W", "ERROR": "E"}.get(f.severity, "?")
        click.echo(f"  [{sev_indicator}] {f.severity:<8} {f.file}:{f.line} {f.message}")
        if f.matched_text and len(f.matched_text) < 80:
            click.echo(f"           matched: {f.matched_text!r}")

    if fail_on_error and error_count > 0:
        raise click.Abort()


def _to_sarif(findings: list[Finding], rules_path: str) -> dict:
    """Convert findings to SARIF format."""
    rules_map = {}
    for f in findings:
        if f.rule_id not in rules_map:
            rules_map[f.rule_id] = {
                "id": f.rule_id,
                "name": f.rule_id,
                "shortDescription": {"text": f.message},
                "properties": {"severity": f.severity.lower()},
            }

    results = []
    for f in findings:
        results.append({
            "ruleId": f.rule_id,
            "level": {"INFO": "note", "WARNING": "warning", "ERROR": "error"}.get(f.severity.lower(), "warning"),
            "message": {"text": f.message},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": f.file},
                    "region": {"startLine": f.line, "startColumn": f.column or 1, "endLine": f.end_line or f.line},
                }
            }],
        })

    return {
        "version": "2.1.0",
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "aidlc",
                    "version": "1.0.0",
                    "rules": list(rules_map.values()),
                }
            },
            "results": results,
        }]
    }


@check_group.command("rules", short_help="List available pattern rules")
@click.option("--category", "-c", help="Filter by rule category prefix")
def check_rules_cmd(category):
    """List all available pattern detection rules.

    \b
    Examples:
      cdh aidlc check rules
      cdh aidlc check rules --category api
    """
    import os
    import yaml
    from pathlib import Path

    rules_path = None
    user_rules = Path.home() / ".cdh" / "rules" / "patterns.yaml"
    if user_rules.is_file():
        rules_path = str(user_rules)
    else:
        default_rules = Path(__file__).parent.parent / "rules" / "patterns.yaml"
        if default_rules.is_file():
            rules_path = str(default_rules)

    if not rules_path or not os.path.isfile(rules_path):
        click.echo("No rules file found.")
        return

    with open(rules_path) as f:
        doc = yaml.safe_load(f)

    click.echo(f"Available rules from: {rules_path}\n")
    click.echo(f"{'RULE ID':<30} {'SEVERITY':<10} DESCRIPTION")
    click.echo("-" * 80)

    count = 0
    for cat_name, cat_rules in (doc or {}).items():
        if not isinstance(cat_rules, dict):
            continue
        for rule_id, rule_def in cat_rules.items():
            if not isinstance(rule_def, dict):
                continue
            full_id = f"{cat_name}.{rule_id}"
            if category and not full_id.startswith(category):
                continue
            sev = rule_def.get("severity", "?").upper()
            msg = rule_def.get("message", "")
            if len(msg) > 50:
                msg = msg[:47] + "..."
            click.echo(f"{full_id:<30} {sev:<10} {msg}")
            count += 1

    click.echo(f"\n{count} rules shown.")


@aidlc.group("generators", short_help="Manage code generators (type generators)")
def generators_group():
    """Manage code generators for OpenAPI/AsyncAPI → typed code.

    \b
    Sub-commands:
      list              List installed plugins (built-in + user + project)
      search [query]    Search the built-in plugin index
      info <name>       Show details about an installed plugin
      install <name>    Install a built-in plugin into current project
      init <name>       Scaffold a new plugin directory
      validate <dir>    Validate a plugin's MANIFEST.toml + template
    """


@generators_group.command("list")
@click.option(
    "--source",
    type=click.Choice(["all", "built-in", "user", "project"]),
    default="all",
    help="Which source to list (default: all, de-duped by name).",
)
@click.option(
    "--path",
    "path",
    type=click.Path(path_type=Path),
    default=None,
    help="Project root for the 'project' source (default: cwd).",
)
def generators_list(source, path):
    """List all discovered generator plugins."""
    from cdh.generators.cli import (
        discover_all_plugins,
        discover_all_plugins_merged,
        filter_by_source,
    )

    project_root = Path(path).expanduser().resolve() if path else Path.cwd()
    discovered = discover_all_plugins(project_root=project_root)

    if source == "all":
        merged = discover_all_plugins_merged(project_root=project_root)
        if not merged:
            click.echo("No plugins found.")
            return
        click.echo(f"{'NAME':<16} {'SOURCE':<10} {'DISPLAY':<20} {'EXT':<8} FEATURES")
        click.echo("-" * 76)
        for name, (src, plugin) in sorted(merged.items()):
            features = ",".join(plugin.supports) or "-"
            click.echo(
                f"{name:<16} {src:<10} {plugin.display_name:<20} "
                f"{plugin.file_extension:<8} {features}"
            )
        return

    filtered = filter_by_source(discovered, source)
    if not filtered:
        click.echo(f"No plugins found in source '{source}'.")
        return
    click.echo(f"{'NAME':<16} {'DISPLAY':<20} {'EXT':<8} FEATURES")
    click.echo("-" * 60)
    for _src, plugin in filtered:
        features = ",".join(plugin.supports) or "-"
        click.echo(
            f"{plugin.name:<16} {plugin.display_name:<20} "
            f"{plugin.file_extension:<8} {features}"
        )


@generators_group.command("search")
@click.argument("query", required=False)
@click.option("--tag", help="Filter by tag")
@click.option("--language-family", help="Filter by language family")
def generators_search(query, tag, language_family):
    """Search the built-in plugin index for community-available generators."""
    from cdh.generators.cli import search_index

    entries = search_index(query)

    if tag:
        entries = [
            e for e in entries
            if tag.lower() in [str(t).lower() for t in e.get("tags", []) or []]
        ]
    if language_family:
        entries = [
            e for e in entries
            if str(e.get("language_family", "")).lower() == language_family.lower()
        ]

    if not entries:
        if query:
            click.echo(f"No plugins matched '{query}'.")
        else:
            click.echo("No plugins found in the built-in index.")
        return

    click.echo(f"{'NAME':<16} {'LANG':<12} {'VERSION':<8} DESCRIPTION")
    click.echo("-" * 80)
    for entry in entries:
        name = entry.get("name", "?")
        lang = entry.get("language_family", "?")
        version = entry.get("version", "?")
        description = entry.get("description", "")
        if len(description) > 50:
            description = description[:47] + "..."
        click.echo(f"{name:<16} {lang:<12} {version:<8} {description}")


@generators_group.command("info")
@click.argument("name")
@click.option(
    "--path",
    "path",
    type=click.Path(path_type=Path),
    default=None,
    help="Project root for the 'project' source (default: cwd).",
)
def generators_info(name, path):
    """Show details about an installed or indexed plugin."""
    from cdh.generators.cli import (
        discover_all_plugins_merged,
        search_index,
    )

    project_root = Path(path).expanduser().resolve() if path else Path.cwd()
    merged = discover_all_plugins_merged(project_root=project_root)
    if name in merged:
        source, plugin = merged[name]
        click.echo(f"Plugin: {plugin.name}")
        click.echo(f"  Source:        {source}")
        click.echo(f"  Display name:  {plugin.display_name}")
        click.echo(f"  File ext:      {plugin.file_extension}")
        click.echo(f"  MIME type:     {plugin.mime_type}")
        click.echo(f"  Outdir:        {plugin.default_outdir}")
        click.echo(f"  Filename tmpl: {plugin.output_filename_template}")
        click.echo(f"  Package:       {plugin.package_name_default}")
        click.echo(f"  Features:      {', '.join(plugin.supports) or '-'}")
        if plugin.format_hints:
            click.echo(f"  Format hints:  {', '.join(plugin.format_hints)}")
        if plugin.imports:
            click.echo(f"  Imports:       {plugin.imports}")
        click.echo(f"  Directory:     {plugin.directory}")
        click.echo(f"  Template:      {plugin.template_path}")
        if plugin.imports_template_path:
            click.echo(f"  Imports tmpl:  {plugin.imports_template_path}")
        return

    index_entries = search_index(name)
    matches = [e for e in index_entries if e.get("name") == name]
    if matches:
        _print_index_entry(matches[0])
        return

    click.echo(f"Plugin '{name}' not found locally or in the built-in index.")
    click.echo("Try `cdh aidlc generators search` to look it up.")
    raise click.Abort()


def _print_index_entry(entry: dict) -> None:
    click.echo(f"Plugin: {entry.get('name', '?')}")
    click.echo(f"  Display name:  {entry.get('display_name', '?')}")
    click.echo(f"  Version:       {entry.get('version', '?')}")
    click.echo(f"  Author:        {entry.get('author', '?')}")
    click.echo(f"  Language:      {entry.get('language_family', '?')}")
    description = entry.get("description", "")
    if description:
        click.echo(f"  Description:   {description}")
    tags = entry.get("tags") or []
    if tags:
        click.echo(f"  Tags:          {', '.join(str(tag) for tag in tags)}")
    tested_with = entry.get("tested_with") or []
    if tested_with:
        click.echo(f"  Tested with:   {', '.join(str(name) for name in tested_with)}")
    download_url = entry.get("download_url", "")
    if download_url:
        click.echo(f"  Download URL:  {download_url}")


@generators_group.command("install")
@click.argument("name")
@click.option(
    "--target-dir",
    default="./aidlc/generators",
    help="Where to install (default: ./aidlc/generators)",
)
def generators_install(name, target_dir):
    """Install a built-in plugin into current project (aidlc/generators/)."""
    from cdh.generators.cli import install_plugin

    target = Path(target_dir).expanduser().resolve()
    try:
        installed = install_plugin(name, target)
    except ValueError as exc:
        click.echo(f"Error: {exc}")
        raise click.Abort()
    except (FileNotFoundError, FileExistsError) as exc:
        click.echo(f"Error: {exc}")
        raise click.Abort()
    click.echo(f"Installed '{name}' to {installed}")


@generators_group.command("init")
@click.argument("name")
@click.option(
    "--target-dir",
    default="./aidlc/generators",
    help="Where to scaffold (default: ./aidlc/generators)",
)
def generators_init(name, target_dir):
    """Scaffold a new plugin directory with MANIFEST.toml + template stub."""
    from cdh.generators.cli import create_plugin_scaffold

    target = Path(target_dir).expanduser().resolve()
    try:
        created = create_plugin_scaffold(name, target)
    except (ValueError, FileExistsError) as exc:
        click.echo(f"Error: {exc}")
        raise click.Abort()
    click.echo(f"Scaffolded plugin '{name}' at {created}")
    click.echo(f"  - {created / 'MANIFEST.toml'}")
    click.echo(f"  - {created / f'template.{name}.tmpl'}")
    click.echo("Next: edit the template, then run")
    click.echo(f"  cdh aidlc generators validate {created}")


@generators_group.command("validate")
@click.argument("path")
def generators_validate(path):
    """Validate a plugin's MANIFEST.toml + template (run smoke test)."""
    from cdh.generators.cli import validate_plugin

    target = Path(path).expanduser().resolve()
    ok, errors = validate_plugin(target)
    if ok:
        click.echo(f"✓ Plugin at {target} is valid.")
        return
    click.echo(f"✗ Plugin at {target} is invalid:")
    for error in errors:
        click.echo(f"  - {error}")
    raise click.Abort()


@generators_group.command("version")
@click.argument("name", required=False)
@click.option("--path", "project_path", type=click.Path(path_type=Path), default=None, help="Project root")
def generators_version(name, project_path):
    """Show plugin version info (SemVer 2.0.0).

    Without args: show all installed plugins and their versions.
    With <name>: show detailed version info for a specific plugin.

    \b
    Examples:
      cdh aidlc generators version
      cdh aidlc generators version typescript
    """
    from cdh.generators.cli import discover_all_plugins_merged
    from cdh.generators.version import SemVer

    project_root = Path(project_path).expanduser().resolve() if project_path else Path.cwd()
    merged = discover_all_plugins_merged(project_root=project_root)

    if not merged:
        click.echo("No plugins found.")
        return

    if not name:
        click.echo(f"{'NAME':<16} {'SOURCE':<10} {'VERSION':<12} STATUS")
        click.echo("-" * 50)
        for n, (source, plugin) in sorted(merged.items()):
            version = plugin.directory.name if hasattr(plugin, 'directory') else "?"
            click.echo(f"{n:<16} {source:<10} {version:<12} OK")
        return

    if name in merged:
        source, plugin = merged[name]
        click.echo(f"Plugin: {name}")
        click.echo(f"  Source:     {source}")
        click.echo(f"  Directory:  {plugin.directory}")
        click.echo(f"  Template:   {plugin.template_path.name}")
        click.echo(f"  Features:  {', '.join(plugin.supports) or '-'}")
        try:
            index_entry = None
            from cdh.generators.cli import search_index
            for e in search_index(name):
                if e.get("name") == name:
                    index_entry = e
                    break
            if index_entry:
                click.echo(f"  Index ver: {index_entry.get('version', '?')}")
                click.echo(f"  Author:    {index_entry.get('author', '?')}")
        except Exception:
            pass
        return

    click.echo(f"Plugin '{name}' not found.")
    raise click.Abort()


@generators_group.command("deps")
@click.argument("name")
@click.option("--path", "project_path", type=click.Path(path_type=Path), default=None)
def generators_deps(name, project_path):
    """Show dependencies and reverse-dependencies for a plugin.

    \b
    Examples:
      cdh aidlc generators deps typescript
    """
    from cdh.generators.cli import discover_all_plugins_merged

    project_root = Path(project_path).expanduser().resolve() if project_path else Path.cwd()
    merged = discover_all_plugins_merged(project_root=project_root)

    if name not in merged:
        click.echo(f"Plugin '{name}' not found.")
        raise click.Abort()

    source, plugin = merged[name]
    click.echo(f"Plugin: {name} (from {source})")

    manifest_file = plugin.directory / "MANIFEST.toml"
    if manifest_file.is_file():
        import tomllib
        try:
            doc = tomllib.loads(manifest_file.read_text(encoding="utf-8"))
            deps = doc.get("dependencies", [])
            if deps:
                click.echo(f"  Dependencies ({len(deps)}):")
                for dep in deps:
                    dep_name = dep.get("name", "?")
                    dep_ver = dep.get("version", "*")
                    click.echo(f"    {dep_name} {dep_ver}")
            else:
                click.echo("  No dependencies declared.")
        except Exception as e:
            click.echo(f"  (Could not parse dependencies: {e})")

    click.echo("  Reverse dependencies (plugins that depend on this):")
    reverse_deps = []
    for other_name, (other_src, other_plugin) in merged.items():
        if other_name == name:
            continue
        other_manifest = other_plugin.directory / "MANIFEST.toml"
        if other_manifest.is_file():
            import tomllib
            try:
                doc = tomllib.loads(other_manifest.read_text(encoding="utf-8"))
                for dep in doc.get("dependencies", []):
                    if dep.get("name") == name:
                        reverse_deps.append(other_name)
                        break
            except Exception:
                pass

    if reverse_deps:
        for rd in reverse_deps:
            click.echo(f"    {rd}")
    else:
        click.echo("    (none)")


# ── tools ────────────────────────────────────────────────────


@aidlc.group("tools", short_help="Manage AIDLC tools (install/status/update)")
def tools_group():
    """Manage AIDLC core tools: generate_shared, contract_diff, deploy_stack.

    Sub-commands:
      install              Install real tool implementations (replaces stubs)
      status               Show installation status of each tool
      update               Update installed tools to latest version
    """


@aidlc.group("trace", short_help="Manage and export AIDLC traces (OTLP)")
def trace_group():
    """Manage AIDLC trace data — list, view, export via OTLP/HTTP.

    The ``export`` subcommand converts agenttrace SQLite rows to OTLP/HTTP
    JSON and ships them to a collector (Jaeger, Tempo, Honeycomb, etc.).

    \b
    Sub-commands:
      export [--endpoint URL] [--since DATE] [--service-name NAME]
    """


@trace_group.command("export", short_help="Export traces to OTLP/HTTP collector")
@click.option(
    "--endpoint",
    default=None,
    help="OTLP/HTTP base endpoint (default: $OTEL_EXPORTER_OTLP_ENDPOINT or http://localhost:4318)",
)
@click.option(
    "--db-path",
    type=click.Path(),
    default=None,
    help="Path to the agenttrace sqlite DB (default: ~/.cdh/traces/traces.db)",
)
@click.option(
    "--service-name",
    default=None,
    help="Value of service.name resource attribute (default: $OTEL_SERVICE_NAME or 'cdh')",
)
@click.option(
    "--since",
    default=None,
    help="Only export rows with timestamp >= this ISO date/datetime",
)
@click.option(
    "--session",
    default=None,
    help="Restrict export to a single session_id",
)
@click.option("--batch-size", type=int, default=256, show_default=True, help="Spans per HTTP POST")
@click.option("--timeout", type=float, default=10.0, show_default=True, help="Per-request HTTP timeout (s)")
@click.option("--dry-run", is_flag=True, help="Build payloads but don't POST")
@click.option(
    "--header",
    "headers",
    multiple=True,
    metavar="K=V",
    help="Extra HTTP header (repeatable), e.g. --header 'Authorization=Bearer xxx'",
)
def trace_export_cmd(
    endpoint, db_path, service_name, since, session, batch_size, timeout, dry_run, headers
):
    """Export agenttrace spans from the local SQLite DB to an OTLP/HTTP collector.

    \b
    Examples:
      cdh aidlc trace export
      cdh aidlc trace export --endpoint http://tempo:4318 --since 2026-07-01
      cdh aidlc trace export --service-name cdh-prod --dry-run
      cdh aidlc trace export --header "Authorization=Bearer xxx"

    Honors the OTEL_EXPORTER_OTLP_ENDPOINT and OTEL_EXPORTER_OTLP_HEADERS
    environment variables when --endpoint / --header are not supplied.
    """
    import os as _os
    from cdh.trace.otel_exporter import DEFAULT_DB_PATH, OtlpExporter

    eff_endpoint = endpoint or _os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
    )
    eff_service = service_name or _os.environ.get("OTEL_SERVICE_NAME", "cdh")
    eff_db_path = Path(db_path).expanduser() if db_path else DEFAULT_DB_PATH

    hdrs: dict[str, str] = {}
    for h in headers:
        if "=" in h:
            k, v = h.split("=", 1)
            hdrs[k.strip()] = v.strip()
    env_hdrs = _os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")
    for part in env_hdrs.split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip()
        if k:
            hdrs[k] = v.strip()

    exporter = OtlpExporter(
        db_path=eff_db_path,
        endpoint=eff_endpoint,
        service_name=eff_service,
        headers=hdrs,
        batch_size=batch_size,
        timeout_s=timeout,
        dry_run=dry_run,
    )

    counters = exporter.export_since(since=since, session_id=session)
    mode = "(dry-run) " if dry_run else ""
    click.echo(
        f"{mode}OTLP export summary: "
        f"read={counters['read']} sent={counters['sent']} "
        f"failed={counters['failed']} batches={counters['batches']}"
    )
    if not dry_run and counters["failed"] > 0:
        raise click.Abort()


@trace_group.command("logs", short_help="Export logs to OTLP/HTTP collector")
@click.option(
    "--endpoint",
    default=None,
    help="OTLP/HTTP endpoint (default: $OTEL_EXPORTER_OTLP_ENDPOINT or http://localhost:4318)",
)
@click.option(
    "--log-file",
    type=click.Path(),
    default=None,
    help="Path to the NDJSON log file (default: ~/.cdh/logs/app.jsonl)",
)
@click.option(
    "--since",
    default=None,
    help="ISO date/datetime; only export logs after this timestamp",
)
@click.option(
    "--min-level",
    type=click.Choice(["DEBUG", "INFO", "WARN", "ERROR", "FATAL"]),
    default="DEBUG",
    help="Minimum log level to export",
)
@click.option("--dry-run", is_flag=True, help="Show what would be exported without sending")
def trace_logs_cmd(endpoint, log_file, since, min_level, dry_run):
    """Export structured CDH logs to an OTLP/HTTP collector.

    Logs are written as NDJSON to ~/.cdh/logs/app.jsonl. This command
    converts them to OTLP logs format and ships them to a collector.

    \b
    Examples:
      cdh aidlc trace logs
      cdh aidlc trace logs --endpoint http://tempo:4318 --min-level WARN
      cdh aidlc trace logs --dry-run
    """
    import os as _os
    from datetime import datetime, timezone as _tz
    from pathlib import Path as _Path

    from cdh.logging import LogLevel, export_logs

    eff_endpoint = endpoint or _os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    log_path = _Path(log_file).expanduser() if log_file else None

    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            since_dt = None

    level = LogLevel[min_level.upper()]

    counters = export_logs(
        log_file=log_path,
        since=since_dt,
        min_level=level,
        endpoint=eff_endpoint,
        dry_run=dry_run,
    )

    mode = "(dry-run) " if dry_run else ""
    click.echo(
        f"{mode}Log export summary: "
        f"read={counters['read']} exported={counters['exported']} "
        f"failed={counters['failed']}"
    )
    if not dry_run and counters["failed"] > 0:
        raise click.Abort()


@trace_group.command("tail", short_help="Tail live CDH log stream")
@click.option("--lines", "-n", type=int, default=50, help="Number of recent lines to show")
@click.option("--follow", "-f", is_flag=True, help="Follow log file (like tail -f)")
@click.option("--level", type=click.Choice(["DEBUG", "INFO", "WARN", "ERROR"]), default="INFO", help="Minimum level")
def trace_tail_cmd(lines, follow, level):
    """Tail recent CDH log entries or follow live.

    \b
    Examples:
      cdh aidlc trace tail
      cdh aidlc trace tail -n 100 -f
      cdh aidlc trace tail --level ERROR
    """
    import os as _os
    from pathlib import Path as _Path

    from cdh.logging import DEFAULT_LOG_DIR, DEFAULT_LOG_FILE, LogLevel

    log_path = _Path(os.environ.get("CDH_LOG_DIR", str(DEFAULT_LOG_DIR))) / DEFAULT_LOG_FILE

    if not log_path.exists():
        click.echo(f"No log file found at {log_path}", err=True)
        return

    import threading
    import time

    min_level = LogLevel[level.upper()].python_level

    def _tail():
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            if not follow:
                # Show last N lines
                all_lines = fh.readlines()
                for line in all_lines[-lines:]:
                    _print_line(line, min_level)
                return

            # Follow mode
            fh.seek(0, 2)
            while True:
                line = fh.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                _print_line(line, min_level)

    def _print_line(line, min_level):
        import logging
        try:
            import json
            rec = json.loads(line.strip())
            level_str = rec.get("severityText", "INFO")
            level_map = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARN": logging.WARNING, "ERROR": logging.ERROR, "FATAL": logging.CRITICAL}
            if level_map.get(level_str, logging.INFO) < min_level:
                return
            ts = rec.get("timeUnixNano", "")
            if ts:
                try:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(int(ts[:10]) / 1e9, tz=_tz.utc)
                    ts = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                except Exception:
                    ts = ts[:10]
            body = rec.get("body", "")
            attrs = {a["key"]: _attr_value(a["value"]) for a in rec.get("attributes", []) if a["key"].startswith("cdh.")}
            fr_id = attrs.get("cdh.fr_id", "")
            session = attrs.get("cdh.session_id", "")
            extra = []
            if fr_id:
                extra.append(fr_id)
            if session:
                extra.append(session[:8])
            extra_str = f" [{', '.join(extra)}]" if extra else ""
            click.echo(f"{ts} {level_str:5} {body}{extra_str}")
        except Exception:
            pass

    def _attr_value(v):
        for k in ("stringValue", "intValue", "doubleValue", "boolValue"):
            if k in v:
                return v[k]
        return str(v)

    if follow:
        t = threading.Thread(target=_tail, daemon=True)
        t.start()
        t.join()
    else:
        _tail()


@tools_group.command("install")
@click.argument("path", required=False, default=".")
def tools_install(path):
    """Install real AIDLC tool implementations into aidlc/tools/.

    Replaces stub files generated by 'cdh aidlc project init' with
    working implementations (generate_shared, contract_diff, deploy_stack).
    """
    from cdh.tools import install_tools as _do_install
    target = Path(path).expanduser().resolve()
    installed = _do_install(target)
    if installed:
        click.echo(f"Installed {len(installed)} tools:")
        for t in installed:
            click.echo(f"  ✓ {t}")
    else:
        click.echo("No tools needed installation (all up to date)")


@tools_group.command("status")
@click.argument("path", required=False, default=".")
def tools_status(path):
    """Show installation status of each AIDLC tool."""
    from cdh.tools import tools_status as _do_status
    target = Path(path).expanduser().resolve()
    results = _do_status(target)
    click.echo("Tool Status:")
    for name, status in results.items():
        icon = "✓" if status == "installed" else "!" if status == "stub" else "✗"
        click.echo(f"  {icon} {name}: {status}")
    if any(s == "stub" for s in results.values()):
        click.echo("\nRun 'cdh aidlc tools install' to replace stubs with real implementations.")


@tools_group.command("update")
@click.argument("path", required=False, default=".")
def tools_update(path):
    """Update installed AIDLC tools to the latest version."""
    from cdh.tools import update_tools as _do_update
    target = Path(path).expanduser().resolve()
    updated = _do_update(target)
    if updated:
        click.echo(f"Updated: {', '.join(updated)}")
    else:
        click.echo("All tools are up to date")


@tools_group.command("test")
@click.argument("path", required=False, default=".")
@click.option("--tool", default=None, help="Test specific tool: generate_shared, contract_diff, deploy_stack")
def tools_test(path, tool):
    """Run self-tests for installed AIDLC tools."""
    import subprocess
    import sys
    target = Path(path).expanduser().resolve()
    tools_dir = target / "aidlc" / "tools"
    if not tools_dir.exists():
        click.echo("No tools directory found. Run 'cdh aidlc tools install' first.")
        raise click.Abort()

    tools_to_test = ["generate_shared", "contract_diff", "deploy_stack"]
    if tool:
        if tool not in tools_to_test:
            click.echo(f"Unknown tool: {tool}")
            raise click.Abort()
        tools_to_test = [tool]

    all_passed = True
    for t in tools_to_test:
        tool_file = tools_dir / f"{t}.py"
        if not tool_file.exists():
            click.echo(f"  ✗ {t}: not installed")
            all_passed = False
            continue
        # Run tool with --self-test or -h to verify it runs
        try:
            result = subprocess.run(
                [sys.executable, str(tool_file), "--help"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                click.echo(f"  ✓ {t}: runs successfully")
            else:
                click.echo(f"  ✗ {t}: failed (exit code {result.returncode})")
                if result.stderr:
                    click.echo(f"    stderr: {result.stderr.decode()[:200]}")
                all_passed = False
        except subprocess.TimeoutExpired:
            click.echo(f"  ✗ {t}: timeout")
            all_passed = False
        except Exception as e:
            click.echo(f"  ✗ {t}: error - {e}")
            all_passed = False

    if not all_passed:
        raise click.Abort()


# ── status ───────────────────────────────────────────────────


@aidlc.command("status")
@click.argument("path", required=False, default=".")
@click.option("--with-history", is_flag=True, help="Include last 5 validate runs")
def status_cmd(path, with_history):
    """Show AIDLC project health overview.

    Aggregates phase, gates, tools status, and basic project info.
    Use --with-history to include the last 5 validate runs.
    """
    from cdh.project_loader import CdhProjectLoader

    target = Path(path).expanduser().resolve()
    cdh_dir = CdhProjectLoader.find_cdh_dir(target)
    if cdh_dir is None:
        click.echo("No .cdh/ directory found. Run 'cdh aidlc project init' first.")
        return

    state = CdhProjectLoader.load_project_state(cdh_dir)
    config_data = CdhProjectLoader.load_project_config(cdh_dir)

    click.echo("╔══════════════════════════════════════════╗")
    click.echo("║        AIDLC Project Status             ║")
    click.echo("╚══════════════════════════════════════════╝")
    click.echo(f"  Name:   {config_data.get('name', target.name)}")
    click.echo(f"  Path:   {target}")

    phase = state.get("current_phase", "?")
    click.echo(f"  Phase:  {phase}")
    completed = state.get("completed_phases", [])
    if completed:
        click.echo(f"  Done:   {', '.join(completed)}")

    gates = state.get("gate_results", {})
    if gates:
        click.echo(f"  Gates:  {len(gates)} recorded")
        for name, g in list(gates.items())[:5]:
            icon = "✓" if g.get("status") == "passed" else "✗"
            click.echo(f"    {icon} {name}: {g.get('status', '?')}")
    else:
        click.echo("  Gates:  (none)")

    project_yaml = target / "aidlc" / "project.yaml"
    if project_yaml.exists():
        import yaml
        data = yaml.safe_load(project_yaml.read_text(encoding="utf-8")) or {}
        comps = data.get("stack", {}).get("components", [])
        click.echo(f"  Components: {len(comps)} defined")
        for c in comps:
            click.echo(f"    - {c.get('id', '?')} ({c.get('fr_prefix', '?')})")

    tools_dir = target / "aidlc" / "tools"
    if tools_dir.exists():
        tool_files = list(tools_dir.glob("*.py"))
        click.echo(f"  Tools:  {len(tool_files)} files in aidlc/tools/")
        stub_count = 0
        for tf in tool_files:
            content = tf.read_text(encoding="utf-8")
            if "not yet implemented" in content:
                stub_count += 1
        if stub_count:
            click.echo(f"  ⚠ {stub_count} tool(s) are still stubs — run 'cdh aidlc tools install'")
    else:
        click.echo("  Tools:  aidlc/tools/ not found")

    if with_history:
        history = CdhProjectLoader.get_validate_history(cdh_dir)
        if history:
            recent = history[-5:]
            click.echo("\n  Validate history (last 5):")
            click.echo(f"    {'TIMESTAMP':<22}  {'PASS':<6}  {'DUR(ms)':<8}")
            for entry in recent:
                ts = entry.get("timestamp", "?")
                passed = "✓" if entry.get("passed") else "✗"
                dur = entry.get("duration_ms", 0)
                click.echo(f"    {ts:<22}  {passed:<6}  {dur:<8}")
        else:
            click.echo("\n  Validate history: (none recorded)")


# ── config ───────────────────────────────────────────────────


@aidlc.group("config", short_help="Manage project configuration")
def config_group():
    """Manage AIDLC project configuration (project.yaml).

    \b
    Sub-commands:
      show                Display current configuration
      component <id>      Add a component to the project
      provider <name>     Set the cloud provider (tcb|aliyun)
      list                List all components (kind/tech/owns/fr_prefix)
      rm <component-id>   Remove a component and delete apps/<owns>/
      diff <other-path>   Show diff of components/configs vs another project
      validate            Validate project.yaml schema & FR prefix consistency
      export <file>       Export effective config as JSON
      import <file>       Import config from JSON
      provider aliyun     Generate aidlc/providers/aliyun/ templates if missing
    """


@config_group.command("validate-state")
@click.argument("path", required=False, default=".")
def config_validate_state(path):
    """Validate .cdh/state.json against its JSON Schema."""
    from cdh.project_loader import CdhProjectLoader
    target = Path(path).expanduser().resolve()
    cdh_dir = CdhProjectLoader.find_cdh_dir(target)
    if cdh_dir is None:
        click.echo("No .cdh/ directory found.")
        raise click.Abort()
    valid, errors = CdhProjectLoader.validate_state_schema(cdh_dir)
    if valid:
        click.echo("state.json: valid")
        return
    click.echo("state.json: invalid")
    for error in errors:
        click.echo(f"- {error}")
    raise click.Abort()


@click.argument("path", required=False, default=".")
def config_show(path):
    """Display the current AIDLC project configuration."""
    target = Path(path).expanduser().resolve()
    yaml_path = target / "aidlc" / "project.yaml"
    if not yaml_path.exists():
        click.echo("aidlc/project.yaml not found")
        return
    import yaml
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    click.echo(yaml.dump(data, default_flow_style=False).strip())


@config_group.command("component")
@click.argument("component_id")
@click.argument("path", required=False, default=".")
def config_component(component_id, path):
    """Add a component to the project (e.g. web, backend, wxa)."""
    target = Path(path).expanduser().resolve()
    try:
        added = add_component(target, component_id)
    except (ValueError, FileNotFoundError) as e:
        click.echo(f"Error: {str(e) or type(e).__name__}")
        raise click.Abort()
    if added:
        click.echo(f"Component '{component_id}' added")
    else:
        click.echo(f"Component '{component_id}' already exists")


@config_group.command("provider")
@click.argument("provider", type=click.Choice(["tcb", "aliyun"]))
@click.argument("path", required=False, default=".")
def config_provider(provider, path):
    """Set the cloud provider (tcb or aliyun)."""
    target = Path(path).expanduser().resolve()
    yaml_path = target / "aidlc" / "project.yaml"
    if not yaml_path.exists():
        click.echo("aidlc/project.yaml not found. Run 'cdh aidlc project init' first.")
        return
    import yaml
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    cross = data.setdefault("stack", {}).setdefault("cross_cutting", {})
    cross["provider"] = provider
    yaml_path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")

    providers_dir = target / "aidlc" / "providers"
    if providers_dir.exists():
        click.echo(f"Provider set to: {provider}")
        click.echo(f"  Provider config at: aidlc/providers/{provider}/")
        for pf in (providers_dir / provider).glob("*.yaml"):
            click.echo(f"    - {pf.name}")
    else:
        click.echo(f"Provider set to: {provider}")
        click.echo("  (aidlc/providers/ directory not scaffolded — run init with --with-ci)")


@config_group.command("list")
@click.argument("path", required=False, default=".")
def config_list(path):
    """List all components with kind/tech/owns/fr_prefix."""
    target = Path(path).expanduser().resolve()
    yaml_path = target / "aidlc" / "project.yaml"
    if not yaml_path.exists():
        click.echo("aidlc/project.yaml not found")
        return
    import yaml
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    comps = data.get("stack", {}).get("components", []) or []
    if not comps:
        click.echo("(no components defined)")
        return
    click.echo(f"{'ID':<10} {'KIND':<14} {'TECH':<10} {'OWNS':<22} {'FR_PREFIX'}")
    click.echo("-" * 70)
    for c in comps:
        click.echo(
            f"{c.get('id', '?'):<10} "
            f"{c.get('kind', '?'):<14} "
            f"{c.get('tech', '?'):<10} "
            f"{c.get('owns', '?'):<22} "
            f"{c.get('fr_prefix', '?')}"
        )


@config_group.command("rm")
@click.argument("component_id")
@click.argument("path", required=False, default=".")
@click.option("--keep-files", is_flag=True, help="Don't delete apps/<owns>/ on disk")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def config_rm(component_id, path, keep_files, yes):
    """Remove a component from project.yaml and delete apps/<owns>/."""
    target = Path(path).expanduser().resolve()
    yaml_path = target / "aidlc" / "project.yaml"
    if not yaml_path.exists():
        click.echo("aidlc/project.yaml not found")
        raise click.Abort()
    import yaml
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    comps = data.get("stack", {}).get("components", []) or []

    match = next((c for c in comps if c.get("id") == component_id), None)
    if match is None:
        click.echo(f"Component '{component_id}' not found in project.yaml")
        raise click.Abort()

    owns = match.get("owns", "")
    if owns and (target / owns).exists() and not keep_files:
        if not yes:
            click.confirm(
                f"Delete directory '{owns}/' and all its contents?",
                abort=True,
            )

    comps = [c for c in comps if c.get("id") != component_id]
    data["stack"]["components"] = comps
    yaml_path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")

    deleted = False
    if owns and not keep_files:
        import shutil
        target_dir = target / owns
        if target_dir.exists():
            shutil.rmtree(target_dir)
            deleted = True

    click.echo(f"Component '{component_id}' removed from project.yaml")
    if deleted:
        click.echo(f"  Deleted directory: {owns}/")
    elif keep_files and owns:
        click.echo(f"  Kept directory: {owns}/ (--keep-files)")


@config_group.command("diff")
@click.argument("other_path")
@click.argument("path", required=False, default=".")
def config_diff(other_path, path):
    """Show difference of components/configs between two AIDLC projects."""
    left = Path(path).expanduser().resolve()
    right = Path(other_path).expanduser().resolve()

    left_yaml = left / "aidlc" / "project.yaml"
    right_yaml = right / "aidlc" / "project.yaml"

    if not left_yaml.exists():
        click.echo(f"Left project missing: {left_yaml}")
        raise click.Abort()
    if not right_yaml.exists():
        click.echo(f"Right project missing: {right_yaml}")
        raise click.Abort()

    import yaml
    left_data = yaml.safe_load(left_yaml.read_text(encoding="utf-8")) or {}
    right_data = yaml.safe_load(right_yaml.read_text(encoding="utf-8")) or {}

    left_comps = {c.get("id"): c for c in left_data.get("stack", {}).get("components", []) or []}
    right_comps = {c.get("id"): c for c in right_data.get("stack", {}).get("components", []) or []}

    click.echo(f"Diff: {left} vs {right}")
    click.echo("=" * 70)

    only_left = sorted(set(left_comps) - set(right_comps))
    only_right = sorted(set(right_comps) - set(left_comps))
    common = sorted(set(left_comps) & set(right_comps))

    if only_left:
        click.echo(f"Only in {left.name}:")
        for cid in only_left:
            click.echo(f"  - {cid}")
    if only_right:
        click.echo(f"Only in {right.name}:")
        for cid in only_right:
            click.echo(f"  + {cid}")

    changed_comps = [cid for cid in common if left_comps[cid] != right_comps[cid]]
    if changed_comps:
        click.echo("Changed components:")
        for cid in changed_comps:
            click.echo(f"  ~ {cid}")
            l, r = left_comps[cid], right_comps[cid]
            for key in sorted(set(l) | set(r)):
                if l.get(key) != r.get(key):
                    click.echo(f"      {key}: {l.get(key)!r} -> {r.get(key)!r}")

    left_cross = left_data.get("stack", {}).get("cross_cutting", {}) or {}
    right_cross = right_data.get("stack", {}).get("cross_cutting", {}) or {}
    cross_changed = [
        k for k in (set(left_cross) | set(right_cross))
        if left_cross.get(k) != right_cross.get(k)
    ]
    if cross_changed:
        click.echo("Cross-cutting changed:")
        for key in cross_changed:
            click.echo(f"  ~ {key}: {left_cross.get(key)!r} -> {right_cross.get(key)!r}")

    if not (only_left or only_right or changed_comps or cross_changed):
        click.echo("(no differences — projects are equivalent)")


@config_group.command("validate")
@click.argument("path", required=False, default=".")
def config_validate(path):
    """Validate project.yaml schema and FR prefix consistency."""
    target = Path(path).expanduser().resolve()
    yaml_path = target / "aidlc" / "project.yaml"
    if not yaml_path.exists():
        click.echo("aidlc/project.yaml not found")
        raise click.Abort()

    errors: list[str] = []
    warnings: list[str] = []

    import yaml
    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        click.echo(f"YAML parse error: {e}")
        raise click.Abort()

    if not isinstance(data, dict):
        errors.append("top-level must be a mapping")
        data = {}

    if "name" not in data:
        warnings.append("missing top-level 'name'")
    if "stack" not in data:
        errors.append("missing top-level 'stack'")
    else:
        stack = data["stack"]
        if not isinstance(stack, dict):
            errors.append("'stack' must be a mapping")
        else:
            comps = stack.get("components", []) or []
            if not isinstance(comps, list):
                errors.append("'stack.components' must be a list")
            else:
                seen_ids: set[str] = set()
                seen_prefixes: dict[str, str] = {}
                for i, c in enumerate(comps):
                    if not isinstance(c, dict):
                        errors.append(f"components[{i}] must be a mapping")
                        continue
                    cid = c.get("id")
                    fp = c.get("fr_prefix")
                    if not cid:
                        errors.append(f"components[{i}] missing 'id'")
                    elif cid in seen_ids:
                        errors.append(f"duplicate component id: {cid}")
                    else:
                        seen_ids.add(cid)
                    if not fp:
                        errors.append(f"components[{i}] ({cid}) missing 'fr_prefix'")
                    else:
                        if fp in seen_prefixes and seen_prefixes[fp] != cid:
                            warnings.append(
                                f"fr_prefix '{fp}' shared by '{seen_prefixes[fp]}' and '{cid}'"
                            )
                        seen_prefixes[fp] = cid or f"#{i}"
                    for key in ("kind", "owns", "tech"):
                        if not c.get(key):
                            warnings.append(f"components[{i}] ({cid}) missing '{key}'")
            cc = stack.get("cross_cutting", {}) or {}
            if cc and "fr_prefix" in cc:
                cc_fp = cc["fr_prefix"]
                for cid, comp in zip(
                    [c.get("id") for c in comps if isinstance(c, dict)],
                    [c.get("fr_prefix") for c in comps if isinstance(c, dict)],
                ):
                    if comp and comp == cc_fp:
                        errors.append(
                            f"component '{cid}' uses cross-cutting fr_prefix '{cc_fp}'"
                        )

    if errors:
        click.echo("✗ Validation FAILED")
        for e in errors:
            click.echo(f"  ERROR: {e}")
        for w in warnings:
            click.echo(f"  WARN:  {w}")
        raise click.Abort()

    click.echo("✓ Validation passed")
    if warnings:
        click.echo(f"  ({len(warnings)} warning(s))")
        for w in warnings:
            click.echo(f"  WARN:  {w}")


@config_group.command("export")
@click.argument("output_file")
@click.argument("path", required=False, default=".")
def config_export(output_file, path):
    """Export effective config as JSON."""
    import json
    from cdh.project_loader import CdhProjectLoader

    target = Path(path).expanduser().resolve()
    yaml_path = target / "aidlc" / "project.yaml"
    if not yaml_path.exists():
        click.echo("aidlc/project.yaml not found")
        raise click.Abort()

    out = Path(output_file).expanduser().resolve()
    import yaml
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}

    cdh_dir = CdhProjectLoader.find_cdh_dir(target)
    if cdh_dir is not None:
        cdh_config = CdhProjectLoader.load_project_config(cdh_dir)
        if cdh_config:
            data["_cdh"] = cdh_config

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    click.echo(f"Exported config to {out}")


@config_group.command("import")
@click.argument("input_file")
@click.argument("path", required=False, default=".")
@click.option("--merge", is_flag=True, help="Merge into existing project.yaml instead of replacing")
def config_import(input_file, path, merge):
    """Import config from a JSON file produced by `config export`."""
    import json
    target = Path(path).expanduser().resolve()
    src = Path(input_file).expanduser().resolve()
    if not src.exists():
        click.echo(f"Input file not found: {src}")
        raise click.Abort()

    payload = json.loads(src.read_text(encoding="utf-8"))
    payload.pop("_cdh", None)

    yaml_path = target / "aidlc" / "project.yaml"
    if not yaml_path.exists():
        click.echo(f"aidlc/project.yaml not found at {target}")
        raise click.Abort()

    import yaml
    if merge:
        existing = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}

        def deep_merge(dst: dict, src_dict: dict) -> dict:
            for k, v in src_dict.items():
                if isinstance(v, dict) and isinstance(dst.get(k), dict):
                    deep_merge(dst[k], v)
                else:
                    dst[k] = v
            return dst

        existing = deep_merge(existing, payload)
        out_data = existing
    else:
        out_data = payload

    yaml_path.write_text(yaml.dump(out_data, default_flow_style=False), encoding="utf-8")
    click.echo(
        f"Imported config from {src} ({'merged' if merge else 'replaced'}) into {yaml_path}"
    )


@config_group.command("provider-templates")
@click.argument("provider", type=click.Choice(["aliyun", "tcb"]))
@click.argument("path", required=False, default=".")
def config_provider_templates(provider, path):
    """Generate aidlc/providers/<name>/ templates if missing (e.g. aliyun)."""
    target = Path(path).expanduser().resolve()
    yaml_path = target / "aidlc" / "project.yaml"
    if not yaml_path.exists():
        click.echo("aidlc/project.yaml not found. Run 'cdh aidlc project init' first.")
        raise click.Abort()

    from cdh.scaffold import (
        ALIYUN_PROVIDER_YAML,
        ALIYUN_DEPLOYMENT_YAML,
        ALIYUN_PREVIEW_YAML,
        TCB_PROVIDER_YAML,
        TCB_DEPLOYMENT_YAML,
        TCB_PREVIEW_YAML,
    )

    templates = {
        "aliyun": ("provider.yaml", ALIYUN_PROVIDER_YAML,
                   "deployment.yaml", ALIYUN_DEPLOYMENT_YAML,
                   "preview.yaml", ALIYUN_PREVIEW_YAML),
        "tcb": ("provider.yaml", TCB_PROVIDER_YAML,
                "deployment.yaml", TCB_DEPLOYMENT_YAML,
                "preview.yaml", TCB_PREVIEW_YAML),
    }[provider]

    out_dir = target / "aidlc" / "providers" / provider
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    skipped: list[str] = []
    for fname, content in (
        (templates[0], templates[1]),
        (templates[2], templates[3]),
        (templates[4], templates[5]),
    ):
        target_file = out_dir / fname
        if target_file.exists():
            skipped.append(fname)
            continue
        target_file.write_text(content, encoding="utf-8")
        written.append(fname)

    click.echo(f"aidlc/providers/{provider}/:")
    for f in written:
        click.echo(f"  + {f}  (created)")
    for f in skipped:
        click.echo(f"  = {f}  (already exists, kept)")


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


# --- trace command ---

@cli.group(short_help="Trace management (agenttrace)")
def trace():
    """Manage CDH traces via agenttrace.

    \b
    Commands:
      list                List recent traces
      view <session_id>   View trace spans for a session
      dashboard           Open the agenttrace web dashboard
    """


@trace.command("list", short_help="List recent traces")
@click.option("--limit", "-n", default=20, help="Number of traces to show")
def trace_list(limit):
    """List recent traces from the agenttrace SQLite database."""
    from cdh.trace import get_tracer, get_db_path
    db_path = get_db_path()
    if not db_path.exists():
        click.echo("No traces yet. Start an agent session to collect traces.")
        return
    tracer = get_tracer()
    try:
        traces = tracer.get_traces(limit=limit)
    except Exception as e:
        click.echo(f"Failed to read traces: {e}")
        return
    if not traces:
        click.echo("No traces found.")
        return
    click.echo(f"Recent traces ({len(traces)} spans):")
    click.echo("")
    for t in traces:
        ts = t.get("type", "?")
        fn = t.get("function", "?")
        dur = t.get("duration")
        sid = t.get("session_id", "")[:12]
        dur_str = f"{dur * 1000:.0f}ms" if dur is not None and dur < 1 else (f"{dur:.1f}s" if dur else "")
        tags = t.get("tags", {}) or {}
        agent = tags.get("agent", "") if isinstance(tags, dict) else ""
        click.echo(f"  {ts:<12} {fn:<30} {dur_str:>8}  {agent}  [{sid}]")


@trace.command("view", short_help="View trace spans for a session")
@click.argument("session_id", required=True)
def trace_view(session_id):
    """View all spans for a given session_id."""
    from cdh.trace import get_tracer, get_db_path
    db_path = get_db_path()
    if not db_path.exists():
        click.echo("No traces yet.")
        return
    tracer = get_tracer()
    try:
        traces = tracer.get_traces(limit=500, session_id=session_id)
    except Exception as e:
        click.echo(f"Failed to read traces: {e}")
        return
    if not traces:
        click.echo(f"No traces found for session {session_id}.")
        return
    click.echo(f"Session: {session_id}  |  {len(traces)} spans")
    click.echo("")
    for t in traces:
        ts = t.get("type", "?")
        fn = t.get("function", "?")
        dur = t.get("duration")
        dur_str = f"{dur * 1000:.0f}ms" if dur is not None and dur < 1 else (f"{dur:.1f}s" if dur else "")
        tags = t.get("tags", {}) or {}
        update_type = tags.get("update_type", "") if isinstance(tags, dict) else ""
        click.echo(f"  {ts:<12} {fn:<30} {dur_str:>8}  {update_type}")


@trace.command("prune", short_help="Remove old trace sessions")
@click.option("--session", "-s", "session_id", help="Remove a specific session_id")
@click.option("--keep-days", "-k", type=int, default=0, help="Keep only sessions from the last N days")
@click.option("--before", "-b", "before_date", help="Remove sessions before this date (YYYY-MM-DD)")
@click.option("--dry-run", "-n", is_flag=True, help="Show what would be removed without deleting")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def trace_prune(session_id, keep_days, before_date, dry_run, yes):
    """Remove old trace sessions to clean up stale data.

    Examples:

    \b
      cdh trace prune --keep-days 7          Keep only last 7 days
      cdh trace prune --before 2026-06-01    Remove sessions before June 1
      cdh trace prune --session 6f8e0db6     Remove a specific session
      cdh trace prune --dry-run --keep-days 7  Preview without deleting
    """
    import json
    import sqlite3
    from datetime import datetime, timedelta

    db_path = Path.home() / ".cdh" / "traces" / "traces.db"
    if not db_path.exists():
        click.echo("No traces database found.")
        return

    conn = sqlite3.connect(str(db_path))
    try:
        # Build the WHERE clause
        conditions = []
        params = []

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

        if before_date:
            if len(before_date) == 10:
                before_date += "T23:59:59"
            conditions.append("timestamp < ?")
            params.append(before_date)

        if keep_days > 0:
            cutoff = (datetime.utcnow() - timedelta(days=keep_days)).isoformat()
            conditions.append("timestamp < ?")
            params.append(cutoff)

        if not conditions:
            click.echo("Specify --session, --keep-days, or --before to prune.")
            click.echo("  Use --dry-run to preview without deleting.")
            conn.close()
            return

        where = " AND ".join(conditions)

        # Find matching sessions
        stale = conn.execute(
            f"SELECT DISTINCT session_id FROM traces WHERE {where}", params
        ).fetchall()

        if not stale:
            click.echo("No matching sessions to prune.")
            conn.close()
            return

        stale_ids = [r[0] for r in stale]
        span_count = conn.execute(
            f"SELECT COUNT(*) FROM traces WHERE {where}", params
        ).fetchone()[0]

        click.echo(f"Found {len(stale_ids)} session(s) ({span_count} spans) to remove:")
        for sid in stale_ids:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM traces WHERE session_id = ?", (sid,)
            ).fetchone()[0]
            # Show model info if present
            models = conn.execute(
                "SELECT DISTINCT {} FROM traces WHERE session_id = ? AND {} IS NOT NULL".format(
                    "JSON_EXTRACT(data, '$.kwargs.model')", "JSON_EXTRACT(data, '$.kwargs.model')"
                ),
                (sid,),
            ).fetchall()
            model_str = f"  models: {', '.join(m[0] for m in models if m[0])}" if models else ""
            click.echo(f"  {sid[:20]}...  ({cnt} spans){model_str}")

        if dry_run:
            click.echo("Dry-run mode. No changes made. Pass --yes to actually delete.")
            conn.close()
            return

        if not yes:
            click.confirm("Delete these sessions?", abort=True)

        conn.execute(f"DELETE FROM traces WHERE {where}", params)
        conn.execute("PRAGMA optimize")
        conn.commit()
        click.echo(f"Removed {span_count} spans from {len(stale_ids)} session(s).")
    finally:
        conn.close()


@trace.command("dashboard", short_help="Open the built-in trace web dashboard")
@click.option("--port", "-p", default=5173, help="Port to serve on")
def trace_dashboard(port):
    """Start a built-in trace web dashboard (Python stdlib, no npm needed).

    Opens a self-contained web UI at http://localhost:<port> showing
    all collected trace spans from the agenttrace SQLite database.
    """
    from cdh.trace.dashboard import run_dashboard
    run_dashboard(port=port)


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
# surface is intentionally limited to: tui, onecode, aidlc, session,
# help, and version.


def main():
    cli()


if __name__ == "__main__":
    main()
