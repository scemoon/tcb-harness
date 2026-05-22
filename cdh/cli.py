import click
import logging
import sys
from pathlib import Path

from cdh.config import ensure_dirs, load_config, save_config
from tui.app import TUI2App

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


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    if ctx.invoked_subcommand is None:
        ctx.invoke(tui)


@cli.command()
@click.option("--mode", default=None, help="Startup mode (plan|agent|solo)")
@click.option("--project", default=None, help="Project to open on startup")
@click.option("--workspace", default=None, help="Development workspace directory (default: ~/.cloud-dev-harness/workspace)")
def tui(mode, project, workspace):
    ensure_dirs()
    cfg = load_config()
    if workspace:
        cfg.default_workspace = str(Path(workspace).expanduser().resolve())
        save_config(cfg)
    setup_logging(cfg.log_level)
    logging.info(f"Starting Cloud Dev Harness with provider={cfg.default_provider}, model={cfg.default_model}")

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
        "run_command": {"*": f"{sys.executable} -m cdh.agent.cdh_agent_acp"},
        "actions": {},
    }

    app = TUI2App(project_dir=project, agent_data=agent_data)
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
