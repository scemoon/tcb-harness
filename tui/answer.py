from typing import NamedTuple


class Answer(NamedTuple):
    """An answer to a question posed by the agent."""

    text: str
    """The textual response."""
    id: str
    """The id of the response."""
    kind: str | None = None
    """Optional hint: permission kind or keyboard shortcut key for UI display."""
