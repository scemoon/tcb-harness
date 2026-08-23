from __future__ import annotations

import click
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

from onecode.config import load_config, save_config

LOG_DIR = Path.home() / ".onecode" / "logs"
LOG_FILE = LOG_DIR / "onecode.log"
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
    # (do NOT cap the entire ``onecode`` namespace at WARNING any more, that
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


@config_provider.command("list")
def config_provider_list():
    """List registered LLM providers (with the current one marked)."""
    from onecode.models.provider import ProviderRegistry
    from onecode.models.registry import ModelRegistry

    # Trigger provider/model registration side-effects.
    try:
        from onecode.models import providers as _providers_mod  # noqa: F401
    except ImportError:
        pass
    try:
        ModelRegistry.initialize()
    except Exception:
        pass

    cfg = load_config()
    current = cfg.default_provider
    registered = sorted(ProviderRegistry.list())
    if not registered:
        click.echo("No providers registered.")
        return

    click.echo(f"Available providers ({len(registered)}):")
    for i, name in enumerate(registered, 1):
        marker = "  ← active" if name == current else ""
        try:
            models = ModelRegistry.list_by_provider(name)
        except Exception:
            models = []
        if models:
            model_names = sorted({m.id for m in models})
            shown = ", ".join(model_names[:5])
            if len(model_names) > 5:
                shown += f", … (+{len(model_names) - 5})"
            model_hint = f"  models: {shown}"
        else:
            model_hint = "  models: (any local)"
        click.echo(f"  {i}) {name}{marker}{model_hint}")
    click.echo("")
    click.echo("Switch with: cdh onecode config provider set <name|n>")


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
    from onecode.config import _dataclass_to_dict
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
    from onecode.skills.loader import SkillLoader

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
    from onecode.skills.manager import SkillManager

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
    from onecode.skills.manager import SkillManager

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


@skill.command("create")
@click.argument("name")
@click.option("--description", "-d", default="", help="Skill description")
def skill_create(name, description):
    """Create a new skill scaffold.

    \b
    Creates SKILL.md and skill.yaml in ~/.onecode/skills/<name>/.
    Edit the generated SKILL.md to add your instructions.

    \b
    Example:
      cdh skill create my-skill -d "My custom skill"
    """
    from onecode.skills.create import create_skill_scaffold
    from onecode.skills.manager import SkillManager
    from onecode.skills.model import Skill as SkillModel

    valid, err = SkillModel.validate_name(name)
    if not valid:
        click.echo(f"Error: Invalid skill name: {err}")
        return
    if description:
        valid, err = SkillModel.validate_description(description)
        if not valid:
            click.echo(f"Error: Invalid description: {err}")
            return

    mgr = SkillManager()
    err = create_skill_scaffold(mgr.skills_dir, name, description or f"A skill for {name}")
    if err:
        click.echo(f"Error: {err}")
    else:
        click.echo(f"Skill '{name}' created at {mgr.skills_dir / name}")
        click.echo(f"  Edit {mgr.skills_dir / name / 'SKILL.md'} to add instructions.")


@skill.command("search")
@click.argument("keyword")
def skill_search(keyword):
    """Search installed skills by keyword.

    Matches against name, description, triggers, and phases.
    Case-insensitive.

    \b
    Example:
      cdh skill search browser
    """
    from onecode.skills.loader import SkillLoader

    loader = SkillLoader()
    results = loader.search(keyword)

    if not results:
        click.echo(f"No skills found matching '{keyword}'.")
        return

    click.echo(f"Skills matching '{keyword}':")
    for s in results:
        status = "[enabled]" if s.enabled else "[disabled]"
        click.echo(f"  {status} {s.name}")
        if s.description:
            click.echo(f"           {s.description}")
    click.echo(f"\nTotal: {len(results)} match(es)")


def _toggle_skill(name: str, enabled: bool):
    import yaml
    from onecode.skills.loader import SkillLoader

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
    from onecode.skills.loader import SkillLoader

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
    from onecode.skills.manager import SkillManager

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
    from onecode.skills.manager import SkillManager

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


@config_skill.command("create")
@click.argument("name")
@click.option("--description", "-d", default="", help="Skill description")
def config_skill_create(name, description):
    """Create a new skill scaffold (alias for cdh skill create)."""
    from onecode.skills.create import create_skill_scaffold
    from onecode.skills.manager import SkillManager
    from onecode.skills.model import Skill as SkillModel

    valid, err = SkillModel.validate_name(name)
    if not valid:
        click.echo(f"Error: Invalid skill name: {err}")
        return
    if description:
        valid, err = SkillModel.validate_description(description)
        if not valid:
            click.echo(f"Error: Invalid description: {err}")
            return

    mgr = SkillManager()
    err = create_skill_scaffold(mgr.skills_dir, name, description or f"A skill for {name}")
    if err:
        click.echo(f"Error: {err}")
    else:
        click.echo(f"Skill '{name}' created at {mgr.skills_dir / name}")
        click.echo(f"  Edit {mgr.skills_dir / name / 'SKILL.md'} to add instructions.")


@config_skill.command("search")
@click.argument("keyword")
def config_skill_search(keyword):
    """Search installed skills by keyword (alias for cdh skill search)."""
    from onecode.skills.loader import SkillLoader

    loader = SkillLoader()
    results = loader.search(keyword)

    if not results:
        click.echo(f"No skills found matching '{keyword}'.")
        return

    click.echo(f"Skills matching '{keyword}':")
    for s in results:
        status = "[enabled]" if s.enabled else "[disabled]"
        click.echo(f"  {status} {s.name}")
        if s.description:
            click.echo(f"           {s.description}")
    click.echo(f"\nTotal: {len(results)} match(es)")


@cli.group(invoke_without_command=True)
def mcp():
    """Manage MCP (Model Context Protocol) servers.

    \b
    MCP servers expose tools and resources to the agent.
    Use `cdh mcp list` to see configured servers.
    """
    pass


_SECRET_HEADER_HINTS = ("auth", "token", "key", "secret", "password", "cookie")


def _is_secret_key(k: str) -> bool:
    kl = k.lower()
    return any(s in kl for s in _SECRET_HEADER_HINTS)


def _mask_value(v: str) -> str:
    if not v:
        return v
    if len(v) <= 4:
        return "***"
    return v[:2] + "***" + v[-2:]


def _format_mcp_servers(servers: list[dict]) -> list[str]:
    lines = []
    if not servers:
        return lines
    for s in servers:
        name = s.get("name", "unknown")
        transport = s.get("transport", "sse")
        enabled = s.get("enabled", True)
        status = "[enabled]" if enabled else "[disabled]"
        if transport == "sse":
            url = s.get("url", "")
            lines.append(f"  {status} {name} (SSE)")
            if url:
                lines.append(f"         URL: {url}")
        elif transport == "http":
            url = s.get("url", "")
            headers = s.get("headers", {})
            lines.append(f"  {status} {name} (HTTP)")
            if url:
                lines.append(f"         URL: {url}")
            if headers:
                hdr_str = ", ".join(
                    f"{k}={_mask_value(v) if _is_secret_key(k) else v}"
                    for k, v in headers.items()
                )
                lines.append(f"         Headers: {hdr_str}")
        else:
            cmd = s.get("command", "")
            cmd_args = " ".join(s.get("args", []))
            env = s.get("env", {})
            lines.append(f"  {status} {name} (stdio)")
            if cmd:
                lines.append(f"         Command: {cmd} {cmd_args}".rstrip())
            if env:
                env_str = ", ".join(f"{k}=***" for k in env)
                lines.append(f"         Env: {env_str}")
    return lines


def _parse_kv_pairs(raw: Optional[str]) -> dict[str, str]:
    """Parse comma-separated KEY=VALUE pairs into a dict."""
    result = {}
    if not raw:
        return result
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            continue
        key, _, val = pair.partition("=")
        result[key.strip()] = val.strip()
    return result


def _mcp_add_impl(name, url, transport, command, args, env, headers, explicit_url):
    """Add an MCP server using either the opencode-style or legacy fields."""
    from onecode.mcp.config import MCPServerConfig
    from onecode.mcp.manager import MCPManager

    mgr = MCPManager()
    if mgr.get_server(name):
        raise click.UsageError(f"MCP server '{name}' already exists")

    # Normalize transport aliases -> opencode "type"
    transport_norm = (transport or "").lower()
    if transport_norm in ("http", "sse"):
        server_type = "remote"
    elif transport_norm in ("stdio", "local", ""):
        server_type = "local"
    else:
        raise click.UsageError(
            f"unknown transport '{transport}' (use stdio|local|http|sse|remote)"
        )

    cfg = MCPServerConfig(name=name, type=server_type, enabled=True)

    if server_type == "local":
        if not command:
            raise click.UsageError("--command required for stdio/local transport")
        if "," in command and not args:
            # Allow `--command npx,-y,pkg` shorthand
            cmd_list = [c.strip() for c in command.split(",") if c.strip()]
        else:
            cmd_list = [command] + ([a.strip() for a in args.split(",")] if args else [])
        cfg.command = cmd_list
        cfg.environment = _parse_kv_pairs(env)
    else:
        final_url = explicit_url or url
        if not final_url:
            raise click.UsageError("--url required for remote transport")
        cfg.url = final_url
        hdrs = _parse_kv_pairs(headers)
        if hdrs:
            cfg.headers = hdrs

    errs = cfg.validate()
    if errs:
        for e in errs:
            click.echo(f"Error: {e}")
        raise click.UsageError("\n".join(errs))

    mgr.add_server(name, cfg)
    if server_type == "local":
        click.echo(f"MCP server '{name}' added (local): {' '.join(cfg.command or [])}")
    else:
        click.echo(f"MCP server '{name}' added (remote): {cfg.url}")


@mcp.command("list")
def mcp_list():
    """List all configured MCP servers."""
    from onecode.mcp.manager import MCPManager

    mgr = MCPManager()
    servers = mgr.list()

    if not servers:
        click.echo("No MCP servers configured. Use `cdh mcp add <name> <url>` to add one.")
        return

    click.echo("Configured MCP servers:")
    for line in _format_mcp_servers(servers):
        click.echo(line)
    click.echo(f"\nTotal: {len(servers)} server(s)")


@mcp.command("add")
@click.argument("name")
@click.argument("url", required=False, default="")
@click.option("--type", "transport", default="sse", help="Transport type: sse, stdio, or http")
@click.option("--command", help="Command for stdio transport")
@click.option("--args", help="Arguments for stdio transport (comma-separated)")
@click.option("--env", help="Environment variables for stdio transport (comma-separated KEY=VALUE pairs)")
@click.option("--headers", help="HTTP headers for http transport (comma-separated Key=Value pairs)")
@click.option("--url", "explicit_url", help="URL for http/sse transport (alternative to positional argument)")
def mcp_add(name, url, transport, command, args, env, headers, explicit_url):
    """Add an MCP server configuration.

    \b
    For SSE transport (default):
      cdh mcp add my-server https://example.com/mcp

    \b
    For stdio transport:
      cdh mcp add my-server --type stdio --command npx --args server-name --env KEY=VAL

    \b
    For HTTP transport:
      cdh mcp add my-server --type http --url https://example.com/mcp --headers Key=Val
    """
    _mcp_add_impl(name, url, transport, command, args, env, headers, explicit_url)


@mcp.command("remove")
@click.argument("name")
def mcp_remove(name):
    """Remove an MCP server configuration."""
    from onecode.mcp.manager import MCPManager

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
    from onecode.mcp.manager import MCPManager

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
    from onecode.mcp.manager import MCPManager

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
    from onecode.mcp.manager import MCPManager

    mgr = MCPManager()
    servers = mgr.list()

    if not servers:
        click.echo("No MCP servers configured. Use `cdh mcp add <name> <url>` to add one.")
        return

    click.echo("Configured MCP servers:")
    for line in _format_mcp_servers(servers):
        click.echo(line)
    click.echo(f"\nTotal: {len(servers)} server(s)")


@config_mcp.command("add")
@click.argument("name")
@click.argument("url", required=False, default="")
@click.option("--type", "transport", default="sse", help="Transport type: sse, stdio, or http")
@click.option("--command", help="Command for stdio transport")
@click.option("--args", help="Arguments for stdio transport (comma-separated)")
@click.option("--env", help="Environment variables for stdio transport (comma-separated KEY=VALUE pairs)")
@click.option("--headers", help="HTTP headers for http transport (comma-separated Key=Value pairs)")
@click.option("--url", "explicit_url", help="URL for http/sse transport (alternative to positional argument)")
def config_mcp_add(name, url, transport, command, args, env, headers, explicit_url):
    """Add an MCP server configuration."""
    _mcp_add_impl(name, url, transport, command, args, env, headers, explicit_url)


@config_mcp.command("remove")
@click.argument("name")
def config_mcp_remove(name):
    """Remove an MCP server configuration."""
    from onecode.mcp.manager import MCPManager

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
    from onecode.mcp.manager import MCPManager

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
    from onecode.mcp.manager import MCPManager

    mgr = MCPManager()
    err = mgr.enable(name, False)
    if err:
        click.echo(f"Error: {err}")
    else:
        click.echo(f"MCP server '{name}' disabled.")


@mcp.command("auth")
@click.argument("name")
def mcp_auth(name):
    """Authenticate a remote MCP server (OAuth / manual token paste)."""
    from onecode.mcp.manager import MCPManager
    from onecode.mcp.oauth import ManualOAuthFlow, OAuthStore

    mgr = MCPManager()
    sc = mgr.get_server(name)
    if not sc:
        raise click.UsageError(f"MCP server '{name}' not found")
    if sc.type != "remote":
        raise click.UsageError(
            f"MCP server '{name}' is type=local (stdio). OAuth is for remote servers."
        )

    oauth_cfg = sc.oauth
    if oauth_cfg is False:
        raise click.UsageError(
            f"OAuth is explicitly disabled for '{name}' (oauth: false in config)."
        )

    flow = ManualOAuthFlow(oauth_cfg)
    bundle = flow.run(server_name=name)
    if not bundle.access_token:
        click.echo("No token provided; aborting.")
        return
    OAuthStore().save(name, bundle)
    click.echo(f"OAuth token saved for '{name}'.")


@mcp.command("logout")
@click.argument("name")
def mcp_logout(name):
    """Remove stored OAuth credentials for a remote MCP server."""
    from onecode.mcp.oauth import OAuthStore

    if OAuthStore().remove(name):
        click.echo(f"OAuth credentials removed for '{name}'.")
    else:
        click.echo(f"No OAuth credentials stored for '{name}'.")


@mcp.command("debug")
@click.argument("name")
def mcp_debug(name):
    """Diagnose an MCP server: presence, auth status, live probe."""
    import asyncio as _asyncio

    from onecode.mcp.config import resolve_mapping
    from onecode.mcp.manager import MCPManager
    from onecode.mcp.oauth import OAuthStore

    mgr = MCPManager()
    sc = mgr.get_server(name)
    if not sc:
        click.echo(f"MCP server '{name}' is not configured.")
        return

    click.echo(f"Type:      {sc.type}")
    click.echo(f"Enabled:   {sc.enabled}")
    if mgr.is_globally_disabled(name):
        click.echo("Globally:  disabled by mcp.disabled in onecode.config.yaml")
    else:
        click.echo("Globally:  enabled")

    if sc.type == "local":
        click.echo(f"Command:   {' '.join(sc.command or [])}")
        env = resolve_mapping(sc.environment)
        if env:
            rendered = ", ".join(f"{k}=***" for k in env)
            click.echo(f"Env:       {rendered}")
    else:
        click.echo(f"URL:       {sc.url}")
        headers = resolve_mapping(sc.headers)
        if headers:
            click.echo("Headers:")
            for k, v in headers.items():
                is_secret = any(s in k.lower() for s in ("auth", "token", "key", "secret"))
                click.echo(f"  {k}: ***" if is_secret else f"  {k}: {v}")

    store = OAuthStore()
    bundle = store.get(name)
    if bundle and bundle.access_token:
        if bundle.is_expired():
            click.echo("OAuth:     token expired — re-run `cdh mcp auth`")
        else:
            click.echo("OAuth:     token present")
    else:
        click.echo("OAuth:     none")

    click.echo("")
    click.echo("Live probe:")
    try:
        ok = _asyncio.run(mgr.connect(name, auto_reconnect=False))
    except Exception as e:
        ok = False
        click.echo(f"  connect raised: {e}")
    if ok:
        try:
            tools = _asyncio.run(mgr.list_tools(name))
            click.echo(f"  connected; {len(tools)} tool(s) available")
        finally:
            _asyncio.run(mgr.disconnect(name))
    else:
        click.echo("  could not connect (check the env / headers above).")


@mcp.command("migrate")
@click.option("--dry-run", is_flag=True, help="Show what would change without modifying anything")
def mcp_migrate(dry_run):
    """Migrate legacy ``mcps.yaml`` to the new ``mcp.json`` format."""
    from onecode.mcp.config import MCPConfigFile

    cfg = MCPConfigFile()
    if not cfg.legacy_path.exists():
        click.echo(f"No legacy file at {cfg.legacy_path}; nothing to migrate.")
        return
    if cfg.path.exists():
        click.echo(f"{cfg.path} already exists; refusing to overwrite.")
        click.echo("Remove it first if you want to re-migrate.")
        return
    if dry_run:
        servers = cfg._load_legacy()
        click.echo(f"Would migrate {len(servers)} server(s) from {cfg.legacy_path} to {cfg.path}:")
        for n, sc in servers.items():
            click.echo(f"  - {n}: type={sc.type}")
        return
    if cfg.migrate_from_legacy():
        click.echo(f"Migrated to {cfg.path}. Legacy file backed up as {cfg.legacy_path}.bak")
    else:
        click.echo("Migration skipped.")


@cli.group(invoke_without_command=True)
def cloudbase():
    """Manage Tencent CloudBase (TCB) MCP integration.

    \b
    CloudBase MCP provides structured access to serverless functions,
    database, hosting, and storage via the @cloudbase/cloudbase-mcp package.
    Use `cdh cloudbase init` to configure credentials and enable the MCP server.
    """
    pass


@cloudbase.command("init")
@click.option("--secret-id", envvar="TENCENTCLOUD_SECRETID", help="Tencent Cloud secret ID")
@click.option("--secret-key", envvar="TENCENTCLOUD_SECRETKEY", help="Tencent Cloud secret key")
@click.option("--env-id", envvar="TCB_ENV_ID", help="Default CloudBase environment ID")
def cloudbase_init(secret_id, secret_key, env_id):
    """Initialize CloudBase MCP server with credentials.

    \b
    Writes the opencode-style ``mcp.json`` entry for ``cloudbase`` and
    persists the credentials in ``~/.cloud-harness-tokens.json`` so
    other CDH tools can re-use them.

    Examples:
      cdh cloudbase init
      cdh cloudbase init --secret-id xxx --secret-key xxx
    """
    if not secret_id:
        secret_id = click.prompt("Tencent Cloud Secret ID", hide_input=False)
    if not secret_key:
        secret_key = click.prompt("Tencent Cloud Secret Key", hide_input=True)

    from onecode.mcp.cloudbase import MCP_SERVER_NAME, write_tokens
    from onecode.mcp.config import MCPServerConfig
    from onecode.mcp.manager import MCPManager

    mgr = MCPManager()

    env = {
        "TENCENTCLOUD_SECRETID": secret_id,
        "TENCENTCLOUD_SECRETKEY": secret_key,
    }
    if env_id:
        env["CLOUDBASE_ENV_ID"] = env_id
        env["TCB_ENV_ID"] = env_id

    if mgr.get_server(MCP_SERVER_NAME):
        click.echo("CloudBase MCP server already configured. Updating credentials...")
        mgr.remove(MCP_SERVER_NAME)

    cfg = MCPServerConfig(
        name=MCP_SERVER_NAME,
        type="local",
        command=["npx", "-y", "@cloudbase/cloudbase-mcp@latest"],
        environment=env,
        enabled=True,
    )
    mgr.add_server(MCP_SERVER_NAME, cfg)
    click.echo("CloudBase MCP server configured (local) in mcp.json.")

    try:
        path = write_tokens(secret_id, secret_key, env_id or "")
        click.echo(f"Credentials saved to {path}")
    except OSError as e:
        click.echo(f"Warning: could not save credentials: {e}", err=True)


@cloudbase.command("logout")
def cloudbase_logout():
    """Remove CloudBase credentials from the tokens file (keeps mcp.json)."""
    from onecode.mcp.cloudbase import clear_tokens

    if clear_tokens():
        click.echo("CloudBase credentials removed from tokens file.")
    else:
        click.echo("No CloudBase credentials to remove.")


@cloudbase.command("status")
def cloudbase_status():
    """Check CloudBase MCP connection status."""
    from onecode.mcp.manager import MCPManager
    mgr = MCPManager()

    cfg = mgr.get("cloudbase")
    if not cfg:
        click.echo("CloudBase MCP server is not configured.")
        click.echo("Run `cdh cloudbase init` to set up.")
        return

    enabled = cfg.get("enabled", False)
    transport = cfg.get("transport", "stdio")
    click.echo(f"CloudBase MCP server: {'[enabled]' if enabled else '[disabled]'} ({transport})")

    if not enabled:
        return

    connected = mgr.is_connected("cloudbase")
    if connected:
        click.echo("Connection: connected")
        import asyncio
        tools = asyncio.run(mgr.list_tools("cloudbase"))
        click.echo(f"Available tools: {len(tools)}")
        for t in tools[:5]:
            click.echo(f"  - {t.name}: {t.description}")
        return

    click.echo("No active connection — running a live probe...")

    async def _probe():
        ok = await mgr.connect("cloudbase", auto_reconnect=False)
        if not ok:
            return False, []
        try:
            tools = await mgr.list_tools("cloudbase")
            return True, tools
        finally:
            await mgr.disconnect("cloudbase")

    try:
        import asyncio
        ok, tools = asyncio.run(_probe())
    except Exception as e:
        click.echo(f"Connection: probe failed ({e})")
        return

    if ok:
        click.echo(f"Connection: connected (probe) — {len(tools)} tools")
        for t in tools[:5]:
            click.echo(f"  - {t.name}: {t.description}")
    else:
        click.echo("Connection: not connected (probe failed)")
        click.echo("Hint: run `cdh cloudbase init` to configure credentials.")


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
    from onecode.codebase import CodebaseEngine

    project_dir = Path(path).resolve()
    if not project_dir.is_dir():
        click.echo(f"Error: {path} is not a valid directory")
        return

    cfg = load_config()
    engine = CodebaseEngine(project_dir, cfg.codebase)
    result = asyncio.run(engine.ensure_indexed(force=force))

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
    from onecode.codebase import CodebaseStorage

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
    from onecode.codebase import CodebaseEngine

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
    from onecode.codebase import CodebaseEngine

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


@cli.group()
def memory():
    """Manage long-term memory.

    \b
    Memory stores conversation history with BM25 keyword recall.
    Use `cdh memory status` to view memory usage and `cdh memory clear` to reset.
    """
    pass


@memory.command("status")
def memory_status():
    """Show memory usage statistics."""
    from onecode.memory.backend import MemoryBackend

    backend = MemoryBackend()
    counts = backend.count_by_layer()
    total = sum(counts.values())
    click.echo(f"Total entries: {total}")
    for layer, count in counts.items():
        click.echo(f"  {layer}: {count}")
    if total == 0:
        click.echo("  (no memories stored yet)")


@memory.command("clear")
@click.option("--layer", default=None, help="Layer to clear (default: all layers)")
def memory_clear(layer: str):
    """Clear memory entries."""
    from onecode.memory import AgentMemory
    from onecode.memory.pyramid import MemoryLayer

    am = AgentMemory()
    if layer:
        layers_to_clear = [ml for ml in MemoryLayer if ml.value == layer]
    else:
        layers_to_clear = list(MemoryLayer)
    removed = 0
    for ml in layers_to_clear:
        entries = am.pyramid.list_by_layer(ml)
        for e in entries:
            am.forget(ml, e.id)
            removed += 1
    click.echo(f"Cleared {removed} memory entries.")


@memory.command("count")
@click.option("--layer", default=None, help="Layer to count (default: all layers)")
def memory_count(layer: str):
    """Count memory entries."""
    from onecode.memory.backend import MemoryBackend

    backend = MemoryBackend()
    counts = backend.count_by_layer()
    if layer:
        click.echo(f"Entries in {layer}: {counts.get(layer, 0)}")
    else:
        total = sum(counts.values())
        click.echo(f"Total entries: {total}")
        for ly, count in sorted(counts.items()):
            click.echo(f"  {ly}: {count}")


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
    from onecode import __version__
    click.echo(f"onecode {__version__}")


def main():
    cli()


if __name__ == "__main__":
    main()
