from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable

from tui.slash_command import SlashCommand

if TYPE_CHECKING:
    from tui.widgets.conversation import Conversation

Handler = Callable[["Conversation", str], Awaitable[None]]


class _CommandEntry:
    def __init__(self, command: str, help: str, handler: Handler, hint: str | None = None):
        self.slash_command = SlashCommand(f"/{command}", help, hint)
        self.handler = handler


_registry: dict[str, _CommandEntry] = {}


def register(command: str, help: str, handler: Handler, hint: str | None = None) -> None:
    _registry[command] = _CommandEntry(command, help, handler, hint)


def clear() -> None:
    _registry.clear()


def get_commands() -> dict[str, _CommandEntry]:
    return _registry


def get_slash_commands() -> list[SlashCommand]:
    return [entry.slash_command for entry in _registry.values()]


async def dispatch(conversation: Conversation, command: str, parameters: str) -> bool:
    entry = _registry.get(command)
    if entry is None:
        return False
    await entry.handler(conversation, parameters)
    return True
