from __future__ import annotations

import importlib
import shlex
from typing import Any, Callable, Optional

from rich.text import Text


_COMMAND_MODULES = [
    "cdh.tui.commands.session_cmds",
    "cdh.tui.commands.mode_cmds",
    "cdh.tui.commands.lifecycle_cmds",
    "cdh.tui.commands.model_cmds",
    "cdh.tui.commands.agent_cmds",
    "cdh.tui.commands.manage_cmds",
    "cdh.tui.commands.trace_cmds",
    "cdh.tui.commands.general_cmds",
    "cdh.tui.commands.harness_cmds",
    "cdh.tui.commands.vim_cmds",
]


HandlerFunc = Callable[..., str]
CommandEntry = tuple[HandlerFunc, str, str]  # (handler, help_text, usage)


def _ensure_loaded():
    if not CommandRegistry._handlers:
        for mod_name in _COMMAND_MODULES:
            try:
                importlib.import_module(mod_name)
            except ImportError:
                pass


def command(name: str, help_text: str = "", usage: str = ""):
    def wrapper(fn: HandlerFunc):
        CommandRegistry.register(name, fn, help_text, usage)
        return fn
    return wrapper


class CommandRegistry:
    _handlers: dict[str, CommandEntry] = {}

    @classmethod
    def register(cls, name: str, handler: HandlerFunc, help_text: str = "", usage: str = ""):
        cls._handlers[name] = (handler, help_text, usage)

    @classmethod
    def get_handler(cls, name: str) -> Optional[HandlerFunc]:
        _ensure_loaded()
        entry = cls._handlers.get(name)
        return entry[0] if entry else None

    @classmethod
    def get_info(cls, name: str) -> Optional[CommandEntry]:
        _ensure_loaded()
        return cls._handlers.get(name)

    @classmethod
    def list_commands(cls) -> list[tuple[str, str]]:
        _ensure_loaded()
        return [(k, v[1]) for k, v in sorted(cls._handlers.items())]

    @classmethod
    def dispatch(cls, app: Any, cmd_line: str) -> str:
        parts = shlex.split(cmd_line)
        if not parts:
            return "Empty command."
        parts[0] = parts[0].lstrip("/")

        # Try matching multi-word commands first (e.g. "spec accept", "session new")
        for n in (3, 2, 1):
            if len(parts) >= n:
                candidate = " ".join(parts[:n])
                handler = cls.get_handler(candidate)
                if handler is not None:
                    args = parts[n:]
                    try:
                        result = handler(app, *args)
                        return result
                    except TypeError as e:
                        return f"Usage error: {e}"
                    except Exception as e:
                        return f"Error: {e}"

        # Single-word top-level command — show available subcommands
        if len(parts) == 1:
            prefix = parts[0]
            subcmds = sorted(k for k in cls._handlers if k.startswith(prefix) and k != prefix)
            if subcmds:
                lines = "\n  ".join(f"/{s}" for s in subcmds)
                return f"Available {prefix} commands:\n  {lines}"

        # No match found — suggest similar commands
        similar = [k for k in cls._handlers if parts[0] in k]
        if similar:
            return f"Unknown command. Did you mean: /{similar[0]}?"
        return f"Unknown command: /{parts[0]}. Type /help for available commands."
