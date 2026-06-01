import sys

import click

from cdha.cli import cli as cdha_cli
from cdha.cli import setup_logging
from cdha.config import ensure_dirs, load_config, save_config
from tui.app import A2TUIApp


_COMMON_HELP = """
\b
Quick config:
  cdh model <name>      Set default model
  cdh provider <name>   Set default provider
  cdh mode <name>       Set default mode
  cdh cloud <name>      Set default cloud

\b
TUI config editor:
  cdh config            Open interactive configuration UI

\b
Paths:
  Config   ~/.cdh/cdh.config.yaml
  Logs     ~/.cdh/logs/
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

    Run without arguments to launch the TUI.
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(tui)


@cli.command(
    short_help="Launch the TUI",
)
@click.option("--mode", default=None, help="Startup mode (plan|agent|solo)")
@click.option("--project", default=None, help="Project directory to open on startup")
def tui(mode, project):
    """
    Launch the CDH TUI interface.

    This is the default command when no subcommand is given.

    \b
    Examples:
      cdh                    Start TUI
      cdh tui --mode plan    Start in plan mode
      cdh tui --project .    Start with current project
    """
    ensure_dirs()
    cfg = load_config()
    setup_logging(cfg.log_level)

    agent_data = {
        "identity": "cdh.cloud-dev-harness",
        "name": "CDH Agent",
        "short_name": "cdh",
        "url": "https://github.com/cloud-dev-harness/cdh",
        "protocol": "acp",
        "type": "coding",
        "author_name": "CDH Team",
        "author_url": "https://github.com/cloud-dev-harness",
        "publisher_name": "CDH Team",
        "publisher_url": "https://github.com/cloud-dev-harness",
        "description": "Cloud Dev Harness Agent",
        "tags": [],
        "run_command": {"*": f"{sys.executable} -m cdha.agent.cdh_agent_acp"},
        "actions": {},
    }

    app = A2TUIApp(project_dir=project, agent_data=agent_data)
    app.run()


CONFIG_KEY_MAP = {
    "mode": ("default_mode",),
    "model": ("default_model",),
    "provider": ("default_provider",),
    "cloud": ("default_cloud",),
    "log-level": ("log_level",),
}

def _set_config(key: str, value: str):
    cfg = load_config()
    attrs = CONFIG_KEY_MAP.get(key)
    if not attrs:
        return False
    for attr in attrs:
        setattr(cfg, attr, value)
    save_config(cfg)
    click.echo(f"{key} = {value}")
    return True


@cli.command(short_help="Set default model")
@click.argument("value")
def model(value):
    """
    Set the default model used by the CDH agent.

    \b
    Examples:
      cdh model claude-opus-4.7    Use Claude Opus 4.7
      cdh model deepseek-v4-flash  Use DeepSeek V4 Flash
      cdh model MiniMax-M2.7       Use MiniMax M2.7
    """
    _set_config("model", value)


@cli.command(short_help="Set default provider")
@click.argument("value")
def provider(value):
    """
    Set the default LLM provider.

    \b
    Supported providers:
      anthropic   Claude models
      openai      GPT models
      deepseek    DeepSeek models
      minimax     MiniMax models
      minimaxi    MiniMaxi models
      glm         GLM models
      ollama      Local Ollama models

    \b
    Examples:
      cdh provider anthropic    Use Anthropic
      cdh provider deepseek     Use DeepSeek
      cdh provider ollama       Use local Ollama
    """
    _set_config("provider", value)


@cli.command(short_help="Set default mode (agent|plan|solo)")
@click.argument("value")
def mode(value):
    """
    Set the default agent startup mode.

    \b
    Modes:
      agent   Full agent mode with tool access
      plan    Planning-only mode
      solo    Solo/chat mode

    \b
    Examples:
      cdh mode agent    Full agent mode
      cdh mode plan     Planning mode
    """
    _set_config("mode", value)


@cli.command(short_help="Set default cloud")
@click.argument("value")
def cloud(value):
    """
    Set the default cloud platform for deployments.

    \b
    Examples:
      cdh cloud tcb    Tencent Cloud Base
    """
    _set_config("cloud", value)


# --- config group (overrides cdha's config) ---

@cli.group(
    invoke_without_command=True,
    short_help="Open configuration editor",
)
@click.pass_context
def config(ctx):
    """
    Open the interactive TUI configuration editor.

    Launches a Textual-based UI for editing all CDH settings
    including providers, models, cloud platforms, agent parameters.
    """
    if ctx.invoked_subcommand is None:
        from cdha.config_screen import main as config_main
        config_main()


@config.command(short_help="Get a config value")
@click.argument("key")
def get(key):
    """Get a single config value by key.

    \b
    Keys: mode, model, provider, cloud, log-level
    """
    cfg = load_config()
    mapping = {"mode": cfg.default_mode, "model": cfg.default_model,
               "provider": cfg.default_provider, "cloud": cfg.default_cloud,
               "log-level": cfg.log_level}
    val = mapping.get(key)
    if val is None:
        click.echo(f"Unknown key: {key}")
    else:
        click.echo(val)


@config.command(short_help="Unset/reset a config value")
@click.argument("key")
def unset(key):
    """Reset a config value to its default."""
    cfg = load_config()
    defaults = {"mode": "agent", "model": "", "provider": "minimaxi",
                "cloud": "tcb", "log-level": "info"}
    if key not in defaults:
        click.echo(f"Unknown key: {key}")
        return
    _set_config(key, defaults[key])

# Reuse subcommands from cdha (set, list)
for _cfg_cmd in cdha_cli.get_command(None, "config").commands.values():
    if _cfg_cmd.name not in config.commands:
        config.add_command(_cfg_cmd)


# Attach remaining cdha subcommands (skip config/init since we override or remove)
for cmd_name in cdha_cli.commands:
    if cmd_name in ("config", "init"):
        continue
    cli.add_command(cdha_cli.get_command(None, cmd_name))


def main():
    cli()


if __name__ == "__main__":
    main()
