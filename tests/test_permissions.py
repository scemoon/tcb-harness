"""Tests for the unified permission system: PermissionStore + _check_tool_permission."""

from __future__ import annotations

import json
from pathlib import Path

from cdha.agent.agents.types import AgentPermission, BuildAgent, PlanAgent, SoloAgent
from cdha.agent.permissions_store import PermissionStore
from cdha.agent.session import AgentSession


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


# ── Subagent inheritance tests ──────────────────────────────────────────────


class TestPermStoreSubagentInheritance:
    """PermissionStore overrides set on parent engine must propagate to
    child engines spawned via ``_spawn_subagent_async_streaming``."""

    def test_subagent_receives_parent_perm_store(self):
        from cdha.agent.engine import AgentEngine

        class FakeApp:
            config = type("cfg", (), {"default_provider": "minimaxi", "default_model": "minimax-m1-671b", "providers": {}})()

        parent = AgentEngine(FakeApp(), project_dir=Path.cwd())
        parent._perm_store.set_override("edit", AgentPermission.ALLOW)

        # Simulate subagent creation (the exact line from _spawn_subagent_async_streaming)
        child = AgentEngine(FakeApp(), project_dir=Path.cwd(), perm_store=parent._perm_store)
        child.set_agent("build")

        assert child.current_agent.permission_edit == AgentPermission.ALLOW

    def test_subagent_inherits_live_override(self):
        """Override set on parent after child creation is visible in child
        (because they share the same PermissionStore instance)."""
        from cdha.agent.engine import AgentEngine

        class FakeApp:
            config = type("cfg", (), {"default_provider": "minimaxi", "default_model": "minimax-m1-671b", "providers": {}})()

        parent = AgentEngine(FakeApp(), project_dir=Path.cwd())
        child = AgentEngine(FakeApp(), project_dir=Path.cwd(), perm_store=parent._perm_store)
        child.set_agent("build")

        # Parent sets override AFTER child exists
        parent._perm_store.set_override("bash", AgentPermission.ALLOW)

        # Re-apply to child (simulates child calling set_agent again)
        child._perm_store.apply_to(child.current_agent)

        assert child.current_agent.permission_bash == AgentPermission.ALLOW

    def test_set_agent_auto_applies_perm_store(self):
        """After Engine.__init__ with perm_store, set_agent() must auto-apply."""
        from cdha.agent.engine import AgentEngine

        class FakeApp:
            config = type("cfg", (), {"default_provider": "minimaxi", "default_model": "minimax-m1-671b", "providers": {}})()

        store = PermissionStore()
        store.set_override("websearch", AgentPermission.DENY)

        engine = AgentEngine(FakeApp(), project_dir=Path.cwd(), perm_store=store)
        engine.set_agent("build")

        assert engine.current_agent.permission_websearch == AgentPermission.DENY
        result = engine._check_tool_permission("WebSearch", {})
        assert result is not None
        assert "denied" in result


# ── Persistence round-trip tests ────────────────────────────────────────────


class TestPermStorePersistence:
    """Verify that permission overrides survive save → load cycles."""

    def test_roundtrip_via_to_dict_from_dict(self):
        store = PermissionStore()
        store.set_override("edit", AgentPermission.ALLOW)
        store.set_override("bash", AgentPermission.DENY)

        d = store.to_dict()
        restored = PermissionStore.from_dict(d)

        assert restored.get_override("edit") == AgentPermission.ALLOW
        assert restored.get_override("bash") == AgentPermission.DENY

        agent = BuildAgent()
        restored.apply_to(agent)
        assert agent.permission_edit == AgentPermission.ALLOW
        assert agent.permission_bash == AgentPermission.DENY

    def test_project_loader_persistence(self, tmp_path):
        """Use CdhProjectLoader to save permissions to .cdh/permissions.json
        and then load them back."""
        from cdha.agent.cdh_loader import CdhProjectLoader

        cdh_dir = tmp_path / ".cdh"
        cdh_dir.mkdir()

        store = PermissionStore()
        store.set_override("bash", AgentPermission.ALLOW)
        store.set_override("edit", AgentPermission.DENY)

        CdhProjectLoader.save_permissions(cdh_dir, store.to_dict())

        saved_path = cdh_dir / "permissions.json"
        assert saved_path.exists()

        loaded_data = CdhProjectLoader.load_permissions(cdh_dir)
        assert loaded_data == {"bash": "allow", "edit": "deny"}

        restored = PermissionStore.from_dict(loaded_data)
        assert restored.get_override("bash") == AgentPermission.ALLOW
        assert restored.get_override("edit") == AgentPermission.DENY

    def test_project_loader_persistence_no_cdh_dir(self, tmp_path):
        """load_permissions should return {} when .cdh/ doesn't exist."""
        from cdha.agent.cdh_loader import CdhProjectLoader

        no_dir = tmp_path / "nonexistent"
        result = CdhProjectLoader.load_permissions(no_dir)
        assert result == {}

    def test_reset_permission_via_clear_and_reapply(self):
        """Simulate /reset-permission: clear override + set_agent reapply."""
        store = PermissionStore()
        store.set_override("bash", AgentPermission.DENY)

        agent = BuildAgent()
        store.apply_to(agent)
        assert agent.permission_bash == AgentPermission.DENY

        # Simulate /reset-permission bash
        store.clear_override("bash")
        agent2 = BuildAgent()
        store.apply_to(agent2)
        assert agent2.permission_bash == AgentPermission.ASK  # back to default


# ── Context stats persistence tests ──────────────────────────────────────────


class TestContextStatsPersistence:
    """Verify that context usage stats survive save_session → load_session."""

    def _make_engine(self) -> AgentEngine:
        from cdha.agent.engine import AgentEngine
        class FakeApp:
            config = type("cfg", (), {"default_provider": "minimaxi", "default_model": "minimax-m1-671b", "max_tokens": 4096, "providers": {}})()
        return AgentEngine(FakeApp(), project_dir=Path.cwd())

    def test_save_and_restore_via_lifecycle_state(self):
        engine = self._make_engine()
        session = AgentSession()
        engine.attach_session(session)

        engine.total_tokens = 5000
        engine.iterations = 10
        engine._turn_usages = [{"input_tokens": 200, "output_tokens": 100, "total_tokens": 300}]

        engine.save_session()
        sid = session.id

        engine2 = self._make_engine()
        ok = engine2.load_session(sid)
        assert ok
        assert engine2.total_tokens == 5000
        assert engine2.iterations == 10
        assert engine2._turn_usages == [{"input_tokens": 200, "output_tokens": 100, "total_tokens": 300}]

        session.delete()

    def test_save_and_restore_via_attach(self):
        session = AgentSession()
        session.update_state("stats", {
            "total_tokens": 777,
            "iterations": 4,
            "turn_usages": [{"input_tokens": 50}],
        })

        engine = self._make_engine()
        engine.attach_session(session)

        assert engine.total_tokens == 777
        assert engine.iterations == 4
        assert engine._turn_usages == [{"input_tokens": 50}]

    def test_empty_stats_does_not_override_defaults(self):
        session = AgentSession()
        engine = self._make_engine()
        engine.total_tokens = 100
        engine.iterations = 2
        engine.attach_session(session)
        # Should keep engine values, not reset to 0
        assert engine.total_tokens == 100
        assert engine.iterations == 2

    def test_build_session_usage_fallback(self):
        """_build_session_usage falls back to engine.total_tokens when _turn_usages is empty."""
        from cdha.agent.cdh_agent_acp import CDHACPAdapter
        engine = self._make_engine()
        engine.total_tokens = 999
        engine._turn_usages = []  # empty

        adapter = CDHACPAdapter()
        adapter.agent = engine
        usage = adapter._build_session_usage()
        assert usage["total_tokens"] == 999
        assert usage["input_tokens"] == 0
        assert usage["output_tokens"] == 0
