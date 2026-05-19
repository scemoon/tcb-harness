import click
import logging
import sys
from pathlib import Path

from cdh.config import ensure_dirs, load_config, save_config
from cdh.tui.app import CloudDevHarnessApp

LOG_DIR = Path.home() / ".cloud-dev-harness" / "logs"
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
    logging.getLogger("cdh").setLevel(logging.WARNING)


@click.group()
def cli():
    pass


@cli.command()
@click.option("--mode", default=None, help="Startup mode (plan|agent|solo)")
@click.option("--project", default=None, help="Project to open on startup")
def tui(mode, project):
    ensure_dirs()
    cfg = load_config()
    setup_logging(cfg.log_level)
    logging.info(f"Starting Cloud Dev Harness with provider={cfg.default_provider}, model={cfg.default_model}")
    app = CloudDevHarnessApp()
    if mode:
        app.current_mode = mode
    if project:
        app.current_project = project
    app.run()


@cli.command()
def init():
    ensure_dirs()
    click.echo("Cloud Dev Harness initialized at ~/.cloud-dev-harness/")


@cli.group()
def config():
    """View or set configuration."""
    pass


@config.command()
@click.argument("key")
@click.argument("value", required=False)
def set(key, value):
    """Set a config value. Key supports dot notation, e.g. workspace default ~/cdh-workspace"""
    cfg = load_config()
    if key == "workspace":
        cfg.default_workspace = value or ""
    elif key == "mode":
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
    from cdh.config import _dataclass_to_dict
    click.echo(yaml.dump(_dataclass_to_dict(cfg), default_flow_style=False))


def main():
    cli()


if __name__ == "__main__":
    main()
