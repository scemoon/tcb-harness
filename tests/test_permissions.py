"""Tests for the unified permission system: PermissionStore + _check_tool_permission."""

from __future__ import annotations

import json
from pathlib import Path

from cdha.agent.agents.types import AgentPermission, BuildAgent, PlanAgent, SoloAgent
from cdha.agent.permissions_store import PermissionStore


# ── PermissionStore tests ──────────────────────────────────────────────────


class TestPermissionStore:
    def test_set_and_get_override(self):
        store = PermissionStore()
        assert store.get_override("edit") is None
        store.set_override("edit", AgentPermission.ALLOW)
        assert store.get_override("edit") == AgentPermission.ALLOW

    def test_apply_to_agent(self):
        store = PermissionStore()
        store.set_override("bash", AgentPermission.ALLOW)
        agent = BuildAgent()
        assert agent.permission_bash == AgentPermission.ASK  # default
        store.apply_to(agent)
        assert agent.permission_bash == AgentPermission.ALLOW

    def test_apply_to_agent_reject_always(self):
        store = PermissionStore()
        store.set_override("edit", AgentPermission.DENY)
        agent = SoloAgent()
        assert agent.permission_edit == AgentPermission.ALLOW  # default
        store.apply_to(agent)
        assert agent.permission_edit == AgentPermission.DENY

    def test_clear_override(self):
        store = PermissionStore()
        store.set_override("edit", AgentPermission.ALLOW)
        store.clear_override("edit")
        assert store.get_override("edit") is None

    def test_clear_all(self):
        store = PermissionStore()
        store.set_override("edit", AgentPermission.ALLOW)
        store.set_override("bash", AgentPermission.DENY)
        store.clear_all()
        assert store.get_override("edit") is None
        assert store.get_override("bash") is None

    def test_snapshot_roundtrip(self):
        store = PermissionStore()
        store.set_override("edit", AgentPermission.ALLOW)
        snap = store.snapshot()
        assert snap == {"edit": AgentPermission.ALLOW}

    def test_to_dict_and_from_dict(self):
        store = PermissionStore()
        store.set_override("edit", AgentPermission.ALLOW)
        store.set_override("bash", AgentPermission.DENY)
        d = store.to_dict()
        assert d == {"edit": "allow", "bash": "deny"}
        restored = PermissionStore.from_dict(d)
        assert restored.get_override("edit") == AgentPermission.ALLOW
        assert restored.get_override("bash") == AgentPermission.DENY

    def test_apply_to_preserves_unrelated_fields(self):
        store = PermissionStore()
        store.set_override("bash", AgentPermission.ALLOW)
        agent = BuildAgent()
        original_edit = agent.permission_edit
        store.apply_to(agent)
        assert agent.permission_bash == AgentPermission.ALLOW
        assert agent.permission_edit == original_edit  # unchanged

    def test_set_agent_create_new_agent_and_reapply(self):
        """Simulate the adapter flow: set_agent() creates fresh agent,
        then PermissionStore.apply_to() restores overrides."""
        store = PermissionStore()
        store.set_override("edit", AgentPermission.ALLOW)

        # BuildAgent defaults
        agent = BuildAgent()
        assert agent.permission_edit == AgentPermission.ASK

        store.apply_to(agent)
        assert agent.permission_edit == AgentPermission.ALLOW

        # Simulate mode switch: create a new agent
        agent2 = PlanAgent()
        assert agent2.permission_edit == AgentPermission.ASK  # PlanAgent defaults

        store.apply_to(agent2)
        assert agent2.permission_edit == AgentPermission.ALLOW  # restored!


# ── _check_tool_permission integration tests ───────────────────────────────


class TestCheckToolPermission:
    """Verify that the engine's _check_tool_permission method correctly
    respects AgentConfig permission fields after PermissionStore overrides."""

    def _make_engine_mock(self, agent):
        """Create a minimal object that behaves like AgentEngine for the
        purpose of calling _check_tool_permission.
        
        We import the actual method from engine module.
        """
        from cdha.agent.engine import AgentEngine

        class FakeApp:
            config = type("cfg", (), {"default_provider": "minimaxi", "default_model": "minimax-m1-671b", "providers": {}})()

        engine = AgentEngine(FakeApp(), project_dir=Path.cwd())
        engine.current_agent = agent
        return engine

    def test_ask_returns_requires_approval(self):
        from cdha.agent.engine import AgentEngine
        engine = self._make_engine_mock(BuildAgent())
        result = engine._check_tool_permission("Bash", {})
        assert result is not None
        parsed = json.loads(result)
        assert parsed.get("requires_approval") is True

    def test_allow_returns_none(self):
        from cdha.agent.engine import AgentEngine
        agent = BuildAgent()
        setattr(agent, "permission_bash", AgentPermission.ALLOW)
        engine = self._make_engine_mock(agent)
        result = engine._check_tool_permission("Bash", {})
        assert result is None

    def test_deny_returns_denied_message(self):
        from cdha.agent.engine import AgentEngine
        agent = BuildAgent()
        setattr(agent, "permission_bash", AgentPermission.DENY)
        engine = self._make_engine_mock(agent)
        result = engine._check_tool_permission("Bash", {})
        assert result is not None
        parsed = json.loads(result)
        assert "denied" in parsed.get("error", "")

    def test_setattr_after_allow_always_then_check(self):
        """Simulate the exact flow: user clicks 'Allow always' → setattr
        → next tool call → _check_tool_permission returns None."""
        from cdha.agent.engine import AgentEngine

        # BuildAgent defaults: permission_bash = ASK
        agent = BuildAgent()
        assert agent.permission_bash == AgentPermission.ASK
        assert agent.get_tools_config()["bash"] == AgentPermission.ASK

        # User clicks "Allow always"
        setattr(agent, "permission_bash", AgentPermission.ALLOW)

        # Next tool call
        engine = self._make_engine_mock(agent)
        result = engine._check_tool_permission("Bash", {})
        assert result is None

    def test_reject_always_then_check(self):
        """User clicks 'Reject always' → setattr → next call is denied."""
        from cdha.agent.engine import AgentEngine

        agent = BuildAgent()
        setattr(agent, "permission_bash", AgentPermission.DENY)

        engine = self._make_engine_mock(agent)
        result = engine._check_tool_permission("Bash", {})
        assert result is not None
        parsed = json.loads(result)
        assert "denied" in parsed.get("error", "")

    def test_permission_store_reapply_via_setattr(self):
        """Integration: PermissionStore.set_override → apply_to →
        _check_tool_permission sees ALLOW even after creating a fresh agent."""
        from cdha.agent.engine import AgentEngine

        store = PermissionStore()
        store.set_override("bash", AgentPermission.ALLOW)

        # Fresh agent (e.g. after set_agent("build"))
        agent = BuildAgent()
        store.apply_to(agent)

        engine = self._make_engine_mock(agent)
        result = engine._check_tool_permission("Bash", {})
        assert result is None

    def test_unknown_tool_name_returns_none(self):
        from cdha.agent.engine import AgentEngine
        engine = self._make_engine_mock(BuildAgent())
        result = engine._check_tool_permission("NonExistentTool", {})

    def test_all_tool_names_mapped(self):
        """Every tool in _TOOL_NAME_TO_PERM_KEY maps to a valid attr name."""
        from cdha.agent.engine import AgentEngine

        agent = BuildAgent()
        for tool_name, perm_key in AgentEngine._TOOL_NAME_TO_PERM_KEY.items():
            agent = BuildAgent()
            attr_name = f"permission_{perm_key}"
            assert hasattr(agent, attr_name), f"Agent missing {attr_name}"
            setattr(agent, attr_name, AgentPermission.ALLOW)
            engine = self._make_engine_mock(agent)
            result = engine._check_tool_permission(tool_name, {})
            assert result is None, f"{tool_name} (key={perm_key}) returned {result}"
