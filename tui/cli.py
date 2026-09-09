import sys

import click
from tui.app import A2TUIApp
from tui.agent_schema import Agent


def set_process_title(title: str) -> None:
    """Set the process title.

    Args:
        title: Desired title.
    """
    try:
        import setproctitle

        setproctitle.setproctitle(title)
    except Exception:
        pass


def check_directory(path: str) -> None:
    """Check a path is directory, or exit the app.

    Args:
        path: Path to check.
    """
    from pathlib import Path

    if not Path(path).resolve().is_dir():
        print(f"Not a directory: {path}")
        sys.exit(-1)


async def get_agent_data(launch_agent) -> Agent | None:
    launch_agent = launch_agent.lower()

    from tui.agents import read_agents, AgentReadError

    try:
        agents = await read_agents()
    except AgentReadError:
        agents = {}

    for agent_data in agents.values():
        if (
            agent_data["short_name"].lower() == launch_agent
            or agent_data["identity"].lower() == launch_agent
        ):
            launch_agent = agent_data["identity"]
            break

    return agents.get(launch_agent)


class DefaultCommandGroup(click.Group):
    def parse_args(self, ctx, args):
        if "--help" in args or "-h" in args:
            return super().parse_args(ctx, args)
        if "--version" in args or "-v" in args:
            return super().parse_args(ctx, args)
        # Check if first arg is a known subcommand
        if not args or args[0] not in self.commands:
            # If not a subcommand, prepend the default command name
            args.insert(0, "run")
        return super().parse_args(ctx, args)

    def format_usage(self, ctx, formatter):
        formatter.write_usage(ctx.command_path, "[OPTIONS] PATH OR COMMAND [ARGS]...")


@click.group(cls=DefaultCommandGroup, invoke_without_command=True)
@click.option("-v", "--version", is_flag=True, help="Show version and exit.")
@click.pass_context
def main(ctx, version):
    """ A2TUI — AI for your terminal."""
    if version:
        from tui import get_version

        click.echo(get_version())
        ctx.exit()
    # If no command and no version flag, let the default command handling proceed
    if ctx.invoked_subcommand is None and not version:
        pass


# @click.group(invoke_without_command=True)
# @click.pass_context
@main.command("run")
@click.argument("project_dir", metavar="PATH", required=False, default=".")
@click.option("-a", "--agent", metavar="AGENT", default="")
def run(
    project_dir: str = ".",
    agent: str = "",
):
    """Run A2TUI."""

    check_directory(project_dir)

    app = A2TUIApp(
        agent_data=None,
        project_dir=project_dir,
    )
    app.run()
    app.run_on_exit()


@main.command("acp")
@click.argument("command", metavar="COMMAND")
@click.argument("project_dir", metavar="PATH", default=None)
@click.option(
    "-t",
    "--title",
    metavar="TITLE",
    help="Optional title to display in the status bar",
    default=None,
)
@click.option("-d", "--project-dir", metavar="PATH", default=None)
def acp(
    command: str,
    title: str | None,
    project_dir: str | None,
) -> None:
    """Run an ACP agent from a command."""

    from rich import print

    from tui.agent_schema import Agent as AgentData

    command_name = command.split(" ", 1)[0].lower()
    identity = f"{command_name}.custom.batrachian.ai"

    agent_data: AgentData = {
        "identity": identity,
        "name": title or command.partition(" ")[0],
        "short_name": "agent",
        "url": "https://github.com/batrachianai/tui",
        "protocol": "acp",
        "type": "coding",
        "author_name": "Will McGugan",
        "author_url": "https://willmcgugan.github.io/",
        "publisher_name": "Will McGugan",
        "publisher_url": "https://willmcgugan.github.io/",
        "description": "Agent launched from CLI",
        "tags": [],
        "help": "",
        "run_command": {"*": command},
        "actions": {},
    }
    app = A2TUIApp(agent_data=agent_data, project_dir=project_dir)
    app.run()
    app.run_on_exit()

    print("")
    print("[bold magenta]Thanks for trying out A2TUI!")
    print("Please head to Discussions to share your experiences (good or bad).")
    print("https://github.com/batrachianai/tui/discussions")


@main.command("settings")
def settings() -> None:
    """Settings information."""
    app = A2TUIApp()
    print(f"{app.settings_path}")


@main.command("replay")
@click.argument("path", metavar="FILE")
def replay(path: str) -> None:
    """Replay interaction from a log file.

    This is a debugging aid. You probably won't need it unless you are building an agent.

    Run it in place of a command line to run an ACP agent:

    tui acp "tui replay tui.log"

    This will replay the agents output, and A2TUI will update the conversation as it would a real agent.
    """
    import time

    stdout = sys.stdout.buffer
    with open(path, "rb") as replay_file:
        for line in replay_file.readlines():
            sender, space, json_line = line.partition(b" ")
            if sender == b"[agent]":
                stdout.write(json_line.strip() + b"\n")
            time.sleep(0.01)
            stdout.write(line)
            stdout.flush()





@main.command("about")
def about() -> None:
    """Show about information."""

    from tui import about

    app = A2TUIApp()

    print(about.render(app))


if __name__ == "__main__":
    main()
