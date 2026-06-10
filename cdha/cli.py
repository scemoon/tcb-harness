import click
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

from cdha.config import ensure_dirs, load_config, save_config

LOG_DIR = Path.home() / ".cdh" / "logs"
LOG_FILE = LOG_DIR / "cdh.log"
LOG_BACKUP_COUNT = 7  # keep 7 days of history

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure root logging to write to a daily-rotated ``cdh.log`` file.

    The active log is always ``~/.cdh/logs/cdh.log``; at midnight it is
    rolled to ``cdh.log.YYYY-MM-DD`` and a fresh file is started.  Up to
    :data:`LOG_BACKUP_COUNT` days of history are retained.

    Returns the root logger so callers can attach additional handlers (e.g.
    a console handler) without re-running ``basicConfig``.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = log_level.upper()
    if level not in _VALID_LOG_LEVELS:
        level = "INFO"
    numeric_level = getattr(logging, level)

    handler = TimedRotatingFileHandler(
        LOG_FILE,
        when="midnight",
        interval=1,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
        utc=False,
    )
    handler.suffix = "%Y-%m-%d"
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    )

    root = logging.getLogger()
    root.setLevel(numeric_level)
    # Avoid stacking handlers if setup_logging() is called twice (e.g. by
    # tests importing both the CLI and a sub-process entry point).
    for h in list(root.handlers):
        if isinstance(h, TimedRotatingFileHandler) and getattr(h, "baseFilename", "") == str(LOG_FILE):
            root.removeHandler(h)
    root.addHandler(handler)

    # Silence chatty third-party loggers; keep the rest at the requested level.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # Engine / provider / adapter loggers — leave at the requested level
    # (do NOT cap the entire ``cdha`` namespace at WARNING any more, that
    # was the bug which kept ``cdh.log`` empty).
    return root


@click.group()
@click.option(
    "--log-level",
    type=click.Choice(sorted(_VALID_LOG_LEVELS), case_sensitive=False),
    default="INFO",
    show_default=True,
    envvar="CDH_LOG_LEVEL",
    help="Root logger verbosity. Defaults to INFO; daily-rotated to ~/.cdh/logs/cdh.log.",
)
def cli(log_level: str):
    """CDH Agent CLI - Cloud Dev Harness Agent commands."""
    setup_logging(log_level)


@cli.group(invoke_without_command=True)
def config():
    """Manage CDH configuration (mode, model, provider, cloud, skill, mcp)."""
    pass


# --- config mode sub-command ---

@config.group("mode")
def config_mode():
    """Manage default agent mode (build, plan, solo)."""
    pass


@config_mode.command("get")
def config_mode_get():
    """Show current mode."""
    cfg = load_config()
    click.echo(f"mode = {cfg.default_mode}  (build | plan | solo)")


@config_mode.command("set")
@click.argument("value", default="build")
def config_mode_set(value):
    """Set default agent mode."""
    cfg = load_config()
    cfg.default_mode = value
    save_config(cfg)
    click.echo(f"mode = {value}")


# --- config model sub-command ---

@config.group("model")
def config_model():
    """Manage default LLM model."""
    pass


@config_model.command("get")
def config_model_get():
    """Show current model."""
    cfg = load_config()
    click.echo(f"model = {cfg.default_model}")


@config_model.command("set")
@click.argument("value")
def config_model_set(value):
    """Set default LLM model."""
    cfg = load_config()
    cfg.default_model = value
    save_config(cfg)
    click.echo(f"model = {value}")


# --- config provider sub-command ---

@config.group("provider")
def config_provider():
    """Manage default LLM provider."""
    pass


@config_provider.command("get")
def config_provider_get():
    """Show current provider."""
    cfg = load_config()
    click.echo(f"provider = {cfg.default_provider}")


@config_provider.command("set")
@click.argument("value")
def config_provider_set(value):
    """Set default LLM provider."""
    cfg = load_config()
    cfg.default_provider = value
    save_config(cfg)
    click.echo(f"provider = {value}")


# --- config log-level sub-command ---

@config.group("log-level")
def config_log_level():
    """Manage log level."""
    pass


@config_log_level.command("get")
def config_log_level_get():
    """Show current log level."""
    cfg = load_config()
    click.echo(f"log-level = {cfg.log_level}  (debug | info | warn | error)")


@config_log_level.command("set")
@click.argument("value", default="info")
def config_log_level_set(value):
    """Set log level."""
    cfg = load_config()
    cfg.log_level = value
    save_config(cfg)
    click.echo(f"log-level = {value}")


# --- config list ---

@config.command("list")
def config_list():
    """Show full YAML configuration."""
    cfg = load_config()
    import yaml
    from cdha.config import _dataclass_to_dict
    click.echo(yaml.dump(_dataclass_to_dict(cfg), default_flow_style=False))


@cli.group(invoke_without_command=True)
def skill():
    """Manage CDH skills (list, add, remove).

    \b
    Skills are instruction sets that extend the agent's capabilities.
    Use `cdh skill list` to see available skills.
    """
    pass


@skill.command("list")
def skill_list():
    """List all skills."""
    from cdha.skills.loader import SkillLoader

    loader = SkillLoader()
    skills = loader.get_all()

    if not skills:
        click.echo("No skills found.")
        return

    click.echo("Skills:")
    for s in skills.values():
        status = "[enabled]" if s.enabled else "[disabled]"
        click.echo(f"  {status} {s.name}")
        if s.description:
            click.echo(f"           {s.description}")
    click.echo(f"\nTotal: {len(skills)} skill(s)")


@skill.command("add")
@click.argument("path", type=click.Path(exists=True, file_okay=True, dir_okay=True, path_type=Path))
def skill_add(path):
    """Install a skill from a local path.

    \b
    The path should contain a skill.yaml and SKILL.md file.

    \b
    Example:
      cdh skill add /path/to/my-skill
    """
    from cdha.skills.manager import SkillManager

    skill_path = Path(path)
    if skill_path.is_file():
        skill_path = skill_path.parent

    mgr = SkillManager()
    err = mgr.install(skill_path)
    if err:
        click.echo(f"Error: {err}")
    else:
        click.echo(f"Skill installed from {skill_path}")


@skill.command("remove")
@click.argument("name")
def skill_remove(name):
    """Remove an installed skill by name."""
    from cdha.skills.manager import SkillManager

    mgr = SkillManager()
    err = mgr.remove(name)
    if err:
        click.echo(f"Error: {err}")
    else:
        click.echo(f"Skill '{name}' removed.")


@skill.command("enable")
@click.argument("name")
def skill_enable(name):
    """Enable a skill by name."""
    _toggle_skill(name, enabled=True)


@skill.command("disable")
@click.argument("name")
def skill_disable(name):
    """Disable a skill by name."""
    _toggle_skill(name, enabled=False)


def _toggle_skill(name: str, enabled: bool):
    import yaml
    from cdha.skills.loader import SkillLoader

    loader = SkillLoader()
    skill = loader.get(name)
    if not skill or not skill.path:
        click.echo(f"Skill '{name}' not found.")
        return

    skill_yaml = skill.path / "skill.yaml"
    if not skill_yaml.exists():
        click.echo(f"No skill.yaml found at {skill.path}")
        return

    data = yaml.safe_load(skill_yaml.read_text()) or {}
    data["enabled"] = enabled
    skill_yaml.write_text(yaml.dump(data, default_flow_style=False))
    loader.invalidate_cache()
    status = "enabled" if enabled else "disabled"
    click.echo(f"Skill '{name}' {status}.")


@config.group("skill")
def config_skill():
    """Manage CDH skills (alias for cdh skill)."""
    pass


@config_skill.command("list")
def config_skill_list():
    """List all skills."""
    from cdha.skills.loader import SkillLoader

    loader = SkillLoader()
    skills = loader.get_all()

    if not skills:
        click.echo("No skills found.")
        return

    click.echo("Skills:")
    for s in skills.values():
        status = "[enabled]" if s.enabled else "[disabled]"
        click.echo(f"  {status} {s.name}")
        if s.description:
            click.echo(f"           {s.description}")
    click.echo(f"\nTotal: {len(skills)} skill(s)")


@config_skill.command("add")
@click.argument("path", type=click.Path(exists=True, file_okay=True, dir_okay=True, path_type=Path))
def config_skill_add(path):
    """Install a skill from a local path."""
    from cdha.skills.manager import SkillManager

    skill_path = Path(path)
    if skill_path.is_file():
        skill_path = skill_path.parent

    mgr = SkillManager()
    err = mgr.install(skill_path)
    if err:
        click.echo(f"Error: {err}")
    else:
        click.echo(f"Skill installed from {skill_path}")


@config_skill.command("remove")
@click.argument("name")
def config_skill_remove(name):
    """Remove an installed skill by name."""
    from cdha.skills.manager import SkillManager

    mgr = SkillManager()
    err = mgr.remove(name)
    if err:
        click.echo(f"Error: {err}")
    else:
        click.echo(f"Skill '{name}' removed.")


@config_skill.command("enable")
@click.argument("name")
def config_skill_enable(name):
    """Enable a skill by name."""
    _toggle_skill(name, enabled=True)


@config_skill.command("disable")
@click.argument("name")
def config_skill_disable(name):
    """Disable a skill by name."""
    _toggle_skill(name, enabled=False)


@cli.group(invoke_without_command=True)
def mcp():
    """Manage MCP (Model Context Protocol) servers.

    \b
    MCP servers expose tools and resources to the agent.
    Use `cdh mcp list` to see configured servers.
    """
    pass


@mcp.command("list")
def mcp_list():
    """List all configured MCP servers."""
    from cdha.mcp.manager import MCPManager

    mgr = MCPManager()
    servers = mgr.list()

    if not servers:
        click.echo("No MCP servers configured. Use `cdh mcp add <name> <url>` to add one.")
        return

    click.echo("Configured MCP servers:")
    for s in servers:
        name = s.get("name", "unknown")
        transport = s.get("transport", "sse")
        enabled = s.get("enabled", True)
        status = "[enabled]" if enabled else "[disabled]"
        if transport == "sse":
            url = s.get("url", "")
            click.echo(f"  {status} {name} (SSE)")
            if url:
                click.echo(f"         URL: {url}")
        else:
            cmd = s.get("command", "")
            args = " ".join(s.get("args", []))
            click.echo(f"  {status} {name} (stdio)")
            if cmd:
                click.echo(f"         Command: {cmd} {args}")
    click.echo(f"\nTotal: {len(servers)} server(s)")


@mcp.command("add")
@click.argument("name")
@click.argument("url")
@click.option("--type", "transport", default="sse", help="Transport type: sse or stdio")
@click.option("--command", help="Command for stdio transport")
@click.option("--args", help="Arguments for stdio transport (comma-separated)")
def mcp_add(name, url, transport, command, args):
    """Add an MCP server configuration.

    \b
    For SSE transport (default):
      cdh mcp add my-server https://example.com/mcp

    \b
    For stdio transport:
      cdh mcp add my-server --type stdio --command npx --args "server-name"
    """
    from cdha.mcp.manager import MCPManager

    mgr = MCPManager()
    if mgr.get(name):
        click.echo(f"Error: MCP server '{name}' already exists")
        return

    if transport == "stdio":
        if not command:
            click.echo("Error: --command required for stdio transport")
            return
        cmd_args = [a.strip() for a in args.split(",")] if args else []
        mgr.add_stdio(name, command, cmd_args)
        click.echo(f"MCP server '{name}' added (stdio)")
    else:
        mgr.add(name, url, transport="sse")
        click.echo(f"MCP server '{name}' added (SSE) at {url}")


@mcp.command("remove")
@click.argument("name")
def mcp_remove(name):
    """Remove an MCP server configuration."""
    from cdha.mcp.manager import MCPManager

    mgr = MCPManager()
    err = mgr.remove(name)
    if err:
        click.echo(f"Error: MCP server '{name}' not found")
    else:
        click.echo(f"MCP server '{name}' removed.")


@mcp.command("enable")
@click.argument("name")
def mcp_enable(name):
    """Enable an MCP server."""
    from cdha.mcp.manager import MCPManager

    mgr = MCPManager()
    err = mgr.enable(name, True)
    if err:
        click.echo(f"Error: {err}")
    else:
        click.echo(f"MCP server '{name}' enabled.")


@mcp.command("disable")
@click.argument("name")
def mcp_disable(name):
    """Disable an MCP server."""
    from cdha.mcp.manager import MCPManager

    mgr = MCPManager()
    err = mgr.enable(name, False)
    if err:
        click.echo(f"Error: {err}")
    else:
        click.echo(f"MCP server '{name}' disabled.")


@config.group("mcp")
def config_mcp():
    """Manage MCP servers (alias for cdh mcp)."""
    pass


@config_mcp.command("list")
def config_mcp_list():
    """List all configured MCP servers."""
    from cdha.mcp.manager import MCPManager

    mgr = MCPManager()
    servers = mgr.list()

    if not servers:
        click.echo("No MCP servers configured. Use `cdh mcp add <name> <url>` to add one.")
        return

    click.echo("Configured MCP servers:")
    for s in servers:
        name = s.get("name", "unknown")
        transport = s.get("transport", "sse")
        enabled = s.get("enabled", True)
        status = "[enabled]" if enabled else "[disabled]"
        if transport == "sse":
            url = s.get("url", "")
            click.echo(f"  {status} {name} (SSE)")
            if url:
                click.echo(f"         URL: {url}")
        else:
            cmd = s.get("command", "")
            args = " ".join(s.get("args", []))
            click.echo(f"  {status} {name} (stdio)")
            if cmd:
                click.echo(f"         Command: {cmd} {args}")
    click.echo(f"\nTotal: {len(servers)} server(s)")


@config_mcp.command("add")
@click.argument("name")
@click.argument("url")
@click.option("--type", "transport", default="sse", help="Transport type: sse or stdio")
@click.option("--command", help="Command for stdio transport")
@click.option("--args", help="Arguments for stdio transport (comma-separated)")
def config_mcp_add(name, url, transport, command, args):
    """Add an MCP server configuration."""
    from cdha.mcp.manager import MCPManager

    mgr = MCPManager()
    if mgr.get(name):
        click.echo(f"Error: MCP server '{name}' already exists")
        return

    if transport == "stdio":
        if not command:
            click.echo("Error: --command required for stdio transport")
            return
        cmd_args = [a.strip() for a in args.split(",")] if args else []
        mgr.add_stdio(name, command, cmd_args)
        click.echo(f"MCP server '{name}' added (stdio)")
    else:
        mgr.add(name, url, transport="sse")
        click.echo(f"MCP server '{name}' added (SSE) at {url}")


@config_mcp.command("remove")
@click.argument("name")
def config_mcp_remove(name):
    """Remove an MCP server configuration."""
    from cdha.mcp.manager import MCPManager

    mgr = MCPManager()
    err = mgr.remove(name)
    if err:
        click.echo(f"Error: MCP server '{name}' not found")
    else:
        click.echo(f"MCP server '{name}' removed.")


@config_mcp.command("enable")
@click.argument("name")
def config_mcp_enable(name):
    """Enable an MCP server."""
    from cdha.mcp.manager import MCPManager

    mgr = MCPManager()
    err = mgr.enable(name, True)
    if err:
        click.echo(f"Error: {err}")
    else:
        click.echo(f"MCP server '{name}' enabled.")


@config_mcp.command("disable")
@click.argument("name")
def config_mcp_disable(name):
    """Disable an MCP server."""
    from cdha.mcp.manager import MCPManager

    mgr = MCPManager()
    err = mgr.enable(name, False)
    if err:
        click.echo(f"Error: {err}")
    else:
        click.echo(f"MCP server '{name}' disabled.")


@cli.group(invoke_without_command=True)
def codebase():
    """Manage codebase index and search.

    \b
    The codebase index enables semantic and keyword search over project files.
    Use `cdh codebase index` to build or update the index, then the agent
    can automatically retrieve relevant code when answering questions.
    """
    pass


@codebase.command("index")
@click.option("--force", is_flag=True, help="Rebuild index from scratch")
@click.option("--path", default=".", help="Project directory", show_default=True)
def codebase_index(force: bool, path: str):
    """Index project files for codebase search."""
    import asyncio
    from cdha.codebase import CodebaseEngine, CodebaseConfig

    project_dir = Path(path).resolve()
    if not project_dir.is_dir():
        click.echo(f"Error: {path} is not a valid directory")
        return

    cfg = load_config()
    engine = CodebaseEngine(project_dir, cfg.codebase)
    result = asyncio.run(engine.ensure_indexed(force=force))

    total = result.total_files if hasattr(result, 'total_files') else 0
    click.echo(
        f"Indexed {project_dir.name}: "
        f"{result.indexed_files} files, "
        f"{result.total_chunks} chunks"
        f"{' (forced rebuild)' if force else ''}"
    )
    if result.failed_files:
        click.echo(f"  Failed: {result.failed_files}")
        for err in result.errors[:5]:
            click.echo(f"    {err}")


@codebase.command("status")
@click.option("--path", default=".", help="Project directory", show_default=True)
def codebase_status(path: str):
    """Show codebase index status."""
    from cdha.codebase import CodebaseStorage

    project_dir = Path(path).resolve()
    if not project_dir.is_dir():
        click.echo(f"Error: {path} is not a valid directory")
        return

    storage = CodebaseStorage(project_dir)
    chunk_count = storage.chunk_count()
    file_count = storage.file_count()

    click.echo(f"Codebase index for {project_dir.name}:")
    click.echo(f"  Files: {file_count}")
    click.echo(f"  Chunks: {chunk_count}")
    if chunk_count == 0:
        click.echo("  (not indexed yet — run `cdh codebase index`)")


@codebase.command("search")
@click.argument("query")
@click.option("--top-k", default=5, help="Number of results", show_default=True)
@click.option("--path", default=".", help="Project directory", show_default=True)
def codebase_search(query: str, top_k: int, path: str):
    """Search indexed codebase."""
    import asyncio
    from cdha.codebase import CodebaseEngine

    project_dir = Path(path).resolve()
    if not project_dir.is_dir():
        click.echo(f"Error: {path} is not a valid directory")
        return

    cfg = load_config()
    engine = CodebaseEngine(project_dir, cfg.codebase)
    chunks = asyncio.run(engine.retrieve(query, top_k=top_k))

    if not chunks:
        click.echo("No results found.")
        return

    click.echo(f"Top {len(chunks)} results for: {query}\n")
    for i, c in enumerate(chunks, 1):
        click.echo(f"[{i}] {c.file_path}:{c.start_line}-{c.end_line}")
        click.echo("```")
        click.echo(c.content[:300])
        if len(c.content) > 300:
            click.echo("...")
        click.echo("```")
        click.echo()


@codebase.command("reindex")
@click.option("--path", default=".", help="Project directory", show_default=True)
def codebase_reindex(path: str):
    """Force rebuild the codebase index (alias for index --force)."""
    import asyncio
    from cdha.codebase import CodebaseEngine

    project_dir = Path(path).resolve()
    if not project_dir.is_dir():
        click.echo(f"Error: {path} is not a valid directory")
        return

    cfg = load_config()
    engine = CodebaseEngine(project_dir, cfg.codebase)
    result = asyncio.run(engine.ensure_indexed(force=True))

    click.echo(
        f"Reindexed {project_dir.name}: "
        f"{result.indexed_files} files, "
        f"{result.total_chunks} chunks"
    )


@cli.command()
@click.argument("command", required=False)
@click.option("--list", "list_commands", is_flag=True, help="List all available commands")
def help_cmd(command, list_commands):
    """Show help for commands."""
    if list_commands:
        click.echo("Available commands:")
        for name, cmd in cli.commands.items():
            click.echo(f"  {name:15} {cmd.help or ''}")
    elif command:
        cmd = cli.commands.get(command)
        if cmd:
            click.echo(cmd.get_help(click.Context(cmd)))
        else:
            click.echo(f"Unknown command: {command}")
    else:
        click.echo(cli.get_help(click.Context(cli)))


@cli.command()
def version():
    """Show version info."""
    from cdha import __version__
    click.echo(f"cdha {__version__}")


def main():
    cli()


if __name__ == "__main__":
    main()
