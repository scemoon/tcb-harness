from importlib.resources import files
import asyncio

from tui.agent_schema import Agent


class AgentReadError(Exception):
    """Problem reading the agents."""


async def read_agents() -> dict[str, Agent]:
    """Read agent information from data/agents

    Raises:
        AgentReadError: If the files could not be read.

    Returns:
        A mapping of identity on to Agent dict.
    """
    import tomllib

    def read_agents() -> list[Agent]:
        """Read agent information.

        Stored in data/agents

        Returns:
            List of agent dicts.
        """
        agents: list[Agent] = []
        for file in files("tui.data").joinpath("agents").iterdir():
            if file.name.startswith("."):
                continue
            try:
                agent: Agent = tomllib.load(file.open("rb"))
            except Exception:
                continue
            if agent.get("active", True):
                agents.append(agent)

        return agents

    agents = await asyncio.to_thread(read_agents)
    agent_map = {agent["identity"]: agent for agent in agents}

    return agent_map
