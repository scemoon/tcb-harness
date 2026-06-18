from __future__ import annotations

import re
from typing import Any


_PATH_RE = re.compile(r'\$path')
_ARG_RE = re.compile(r'\$(\d+)')
_ARGS_RE = re.compile(r'\$ARGUMENTS')


def substitute_arguments(content: str, arguments: list[str] | None = None) -> str:
    """Substitute positional arguments in skill content.

    Supports:
      $path        -> first argument
      $0, $1, $2   -> positional arguments
      $ARGUMENTS   -> all arguments joined by space
    """
    args = arguments or []
    text = content

    # $path -> first argument
    if args:
        text = _PATH_RE.sub(args[0], text)
    else:
        text = _PATH_RE.sub("", text)

    # $0, $1, $2...
    def _replace_arg(m: re.Match) -> str:
        idx = int(m.group(1))
        return args[idx] if idx < len(args) else ""

    text = _ARG_RE.sub(_replace_arg, text)

    # $ARGUMENTS -> all joined
    text = _ARGS_RE.sub(" ".join(args), text)

    return text
