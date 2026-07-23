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
      tools install|status|update         Manage AIDLC tools (generate_shared/contract_diff/deploy_stack)
      status                              Show project health overview
      config show|component|provider      Manage project configuration
      sync                                Regenerate AGENTS.md and CLAUDE.md
      update                              Alias for sync (deprecated)
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


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


@aidlc.command("validate")
@click.argument("path", required=False, default=".")
@click.option("--ears", "ears_only", is_flag=True, help="EARS format check only")
@click.option("--fr", "fr_only", is_flag=True, help="FR namespace consistency check only")
@click.option("--bdd", "bdd_only", is_flag=True, help="BDD scenario coverage check only")
@click.option("--dag", "dag_only", is_flag=True, help="Task DAG cycle check only")
@click.option("--all", "all_checks", is_flag=True, default=False, help="Run all checks (default)")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", help="Output format (default: text)")
def validate_cmd(path, ears_only, fr_only, bdd_only, dag_only, all_checks, output_format):
    """Validate AIDLC spec quality: EARS format, FR namespaces, BDD coverage, DAG cycles.

    Runs all checks by default. Use --ears/--fr/--bdd/--dag to run specific checks.
    """
    import json as json_module
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

    all_passed = True
    results = {}
    for key in selected:
        label, runner = runners[key]
        result = runner(target)
        results[key] = result
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

    if output_format == "json":
        summary = {
            "passed": all_passed,
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


# ── tools ────────────────────────────────────────────────────


@aidlc.group("tools", short_help="Manage AIDLC tools (install/status/update)")
def tools_group():
    """Manage AIDLC core tools: generate_shared, contract_diff, deploy_stack.

    Sub-commands:
      install              Install real tool implementations (replaces stubs)
      status               Show installation status of each tool
      update               Update installed tools to latest version
    """


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


# ── status ───────────────────────────────────────────────────


@aidlc.command("status")
@click.argument("path", required=False, default=".")
def status_cmd(path):
    """Show AIDLC project health overview.

    Aggregates phase, gates, tools status, and basic project info.
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


# ── config ───────────────────────────────────────────────────


@aidlc.group("config", short_help="Manage project configuration")
def config_group():
    """Manage AIDLC project configuration (project.yaml).

    Sub-commands:
      show              Display current configuration
      component <id>    Add a component to the project
      provider <name>   Set the cloud provider (tcb|aliyun)
    """


@config_group.command("show")
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
