from __future__ import annotations

from typing import Optional

from onecode.agent.agents.types import AgentPermission


class PermissionStore:
    """Persists user-defined allow_always / reject_always overrides across
    ``set_agent()`` calls so permissions survive mode switches.

    Usage::

        store = PermissionStore()
        store.set_override("bash", AgentPermission.ALLOW)   # user said "Allow always"
        store.set_override("edit", AgentPermission.DENY)    # user said "Reject always"
        ...
        store.apply_to(current_agent)                       # re-apply after set_agent
    """

    def __init__(self) -> None:
        # perm_key → AgentPermission  (e.g. "bash" → AgentPermission.ALLOW)
        self._overrides: dict[str, AgentPermission] = {}

    def set_override(self, perm_key: str, perm: AgentPermission) -> None:
        """Record a user override for the given permission key."""
        self._overrides[perm_key] = perm

    def get_override(self, perm_key: str) -> Optional[AgentPermission]:
        return self._overrides.get(perm_key)

    def clear_override(self, perm_key: str) -> None:
        self._overrides.pop(perm_key, None)

    def clear_all(self) -> None:
        self._overrides.clear()

    def apply_to(self, agent) -> None:
        """Apply all recorded overrides to an AgentConfig instance.

        Call this after ``set_agent()`` to restore the user's choices.
        """
        for perm_key, perm in self._overrides.items():
            attr_name = f"permission_{perm_key}"
            if hasattr(agent, attr_name):
                setattr(agent, attr_name, perm)

    def to_dict(self) -> dict[str, str]:
        return {k: v.value for k, v in self._overrides.items()}

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> PermissionStore:
        store = cls()
        for k, v in d.items():
            try:
                store._overrides[k] = AgentPermission(v)
            except ValueError:
                pass
        return store

    def snapshot(self) -> dict[str, AgentPermission]:
        return dict(self._overrides)
