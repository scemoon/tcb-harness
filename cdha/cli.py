import click
import logging
from pathlib import Path

from cdha.config import ensure_dirs, load_config, save_config

LOG_DIR = Path.home() / ".cdh" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging(log_level: str = "INFO"):
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    handlers = [
        logging.FileHandler(LOG_DIR / "cdh.log", mode="a"),
    ]

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=handlers,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("cdha").setLevel(logging.WARNING)


@click.group()
def cli():
    """CDH Agent CLI - Cloud Dev Harness Agent commands."""
    pass


@cli.command()
def init():
    """Initialize CDH config directory and default config."""
    ensure_dirs()
    click.echo("CDH initialized at ~/.cdh/")


@cli.command()
@click.argument("key")
@click.argument("value", required=False)
def set(key, value):
    """Set a config value."""
    cfg = load_config()
    if key == "mode":
        cfg.default_mode = value or "agent"
    elif key == "model":
        cfg.default_model = value or ""
    elif key == "provider":
        cfg.default_provider = value or ""
    elif key == "cloud":
        cfg.default_cloud = value or ""
    elif key == "log-level":
        cfg.log_level = value or "info"
    else:
        click.echo(f"Unknown config key: {key}")
        return
    save_config(cfg)
    click.echo(f"config.{key} = {value}")


@cli.command()
def list():
    """Show all configuration."""
    cfg = load_config()
    import yaml
    from cdha.config import _dataclass_to_dict
    click.echo(yaml.dump(_dataclass_to_dict(cfg), default_flow_style=False))


@cli.group(invoke_without_command=True)
def config():
    """Open TUI config screen or manage config."""
    pass


@config.command()
@click.argument("key")
@click.argument("value", required=False)
def set(key, value):
    """Set a config value."""
    cfg = load_config()
    if key == "mode":
        cfg.default_mode = value or "agent"
    elif key == "model":
        cfg.default_model = value or ""
    elif key == "provider":
        cfg.default_provider = value or ""
    elif key == "cloud":
        cfg.default_cloud = value or ""
    elif key == "log-level":
        cfg.log_level = value or "info"
    else:
        click.echo(f"Unknown config key: {key}")
        return
    save_config(cfg)
    click.echo(f"config.{key} = {value}")


@config.command()
def list():
    """Show all configuration."""
    cfg = load_config()
    import yaml
    from cdha.config import _dataclass_to_dict
    click.echo(yaml.dump(_dataclass_to_dict(cfg), default_flow_style=False))


@config.command()
def tui():
    """Open TUI config screen."""
    from cdha.config_screen import main as config_main
    config_main()


@cli.command()
@click.option("--mode", default="agent", help="Agent mode: agent, plan, solo")
@click.option("--provider", help="Override default provider")
@click.option("--model", help="Override default model")
@click.option("--session", help="Session ID to resume")
def tui(mode, provider, model, session):
    """Launch the CDH TUI."""
    from tui.app import main as tui_main
    tui_main()


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
