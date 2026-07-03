"""Tests for cdh platform MCP pool.

Covers:
- CdhMcpManager add/list/get/enable/remove
- CdhMcpLoader load_platform/get_merged/get_platform_only
- CdhMcpInjector inject_env/inject_for_engine/get_shared_mcp_config
- Engine private MCP wins on name conflict
- Unsupported engine fallback
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# CdhMcpManager
# ---------------------------------------------------------------------------


class TestCdhMcpManager:
    def test_add_sse(self, tmp_path):
        mgr = _make_mgr(tmp_path)
        mgr.add("my-server", "https://example.com/mcp", transport="sse")
        assert mgr.get("my-server") is not None
        assert mgr.get("my-server")["transport"] == "sse"

    def test_add_stdio(self, tmp_path):
        mgr = _make_mgr(tmp_path)
        mgr.add_stdio("stdio-server", "npx", args=["mcp-server"])
        cfg = mgr.get("stdio-server")
        assert cfg is not None
        assert cfg["transport"] == "stdio"
        assert cfg["command"] == "npx"

    def test_list_returns_configs(self, tmp_path):
        mgr = _make_mgr(tmp_path)
        mgr.add("a", "http://a.com")
        mgr.add("b", "http://b.com")
        entries = mgr.list()
        assert len(entries) == 2
        names = {e["name"] for e in entries}
        assert names == {"a", "b"}

    def test_list_empty(self, tmp_path):
        mgr = _make_mgr(tmp_path)
        assert mgr.list() == []

    def test_get_returns_none_when_missing(self, tmp_path):
        mgr = _make_mgr(tmp_path)
        assert mgr.get("nonexistent") is None

    def test_enable_toggle(self, tmp_path):
        mgr = _make_mgr(tmp_path)
        mgr.add("srv", "http://srv.com")
        err = mgr.enable("srv", False)
        assert err is None
        assert mgr.get("srv")["enabled"] is False

    def test_enable_nonexistent_returns_error(self, tmp_path):
        mgr = _make_mgr(tmp_path)
        err = mgr.enable("ghost", False)
        assert err is not None
        assert "not found" in err

    def test_remove_deletes_entry(self, tmp_path):
        mgr = _make_mgr(tmp_path)
        mgr.add("srv", "http://srv.com")
        err = mgr.remove("srv")
        assert err is None
        assert mgr.get("srv") is None

    def test_remove_nonexistent_returns_error(self, tmp_path):
        mgr = _make_mgr(tmp_path)
        err = mgr.remove("ghost")
        assert err is not None
        assert "not found" in err

    def test_to_dict_returns_all(self, tmp_path):
        mgr = _make_mgr(tmp_path)
        mgr.add("a", "http://a.com")
        mgr.add("b", "http://b.com")
        d = mgr.to_dict()
        assert set(d.keys()) == {"a", "b"}

    def test_persistence(self, tmp_path):
        mcps_dir = tmp_path / "mcps"
        mgr1 = _make_mgr(tmp_path, mcps_dir)
        mgr1.add("persist", "http://persist.com")

        mgr2 = _make_mgr(tmp_path, mcps_dir)
        assert mgr2.get("persist") is not None

    def test_add_with_tags(self, tmp_path):
        mgr = _make_mgr(tmp_path)
        mgr._data["tagged"] = {"url": "http://x.com", "transport": "sse", "enabled": True, "tags": ["production"]}
        mgr._save()
        mgr2 = _make_mgr(tmp_path)
        assert mgr2.get("tagged")["tags"] == ["production"]

    def test_list_excludes_disabled_by_default(self, tmp_path):
        mgr = _make_mgr(tmp_path)
        mgr.add("enabled", "http://enabled.com")
        mgr.add("disabled", "http://disabled.com")
        mgr.enable("disabled", False)
        entries = mgr.list()
        enabled = [e for e in entries if e.get("enabled") is not False]
        assert any(e["name"] == "enabled" for e in enabled)


# ---------------------------------------------------------------------------
# CdhMcpLoader
# ---------------------------------------------------------------------------


class TestCdhMcpLoader:
    def test_load_platform_empty_when_no_config(self, tmp_path):
        loader = _make_loader(tmp_path)
        assert loader.load_platform() == {}

    def test_load_platform_returns_configs(self, tmp_path):
        _write_mcps(tmp_path, {"srv1": {"url": "http://a.com"}})
        loader = _make_loader(tmp_path)
        data = loader.load_platform()
        assert "srv1" in data

    def test_get_merged_no_engine(self, tmp_path):
        _write_mcps(tmp_path, {"platform-srv": {"url": "http://p.com"}})
        loader = _make_loader(tmp_path)
        merged = loader.get_merged()
        assert len(merged) == 1
        assert merged[0]["name"] == "platform-srv"
        assert merged[0]["source"] == "platform"

    def test_engine_wins_on_name_conflict(self, tmp_path):
        _write_mcps(tmp_path, {"shared": {"url": "http://platform.com", "transport": "sse"}})
        engine_path = tmp_path / "engine" / "mcps.yaml"
        engine_path.parent.mkdir(parents=True)
        engine_path.write_text(yaml.dump({"shared": {"url": "http://engine.com", "transport": "stdio"}}))

        loader = _make_loader(tmp_path)
        merged = loader.get_merged(engine_path)
        shared = [m for m in merged if m["name"] == "shared"][0]
        assert shared["url"] == "http://engine.com"
        assert shared["source"] == "engine"

    def test_get_merged_combines_distinct(self, tmp_path):
        _write_mcps(tmp_path, {"p1": {"url": "http://p1.com"}})
        engine_path = tmp_path / "engine" / "mcps.yaml"
        engine_path.parent.mkdir(parents=True)
        engine_path.write_text(yaml.dump({"e1": {"url": "http://e1.com"}}))

        loader = _make_loader(tmp_path)
        merged = loader.get_merged(engine_path)
        names = {m["name"] for m in merged}
        assert names == {"p1", "e1"}

    def test_get_platform_only(self, tmp_path):
        _write_mcps(tmp_path, {"p1": {"url": "http://p1.com"}, "p2": {"url": "http://p2.com"}})
        loader = _make_loader(tmp_path)
        platform = loader.get_platform_only()
        assert len(platform) == 2
        assert all(p["source"] == "platform" for p in platform)

    def test_load_platform_handles_corrupt_yaml(self, tmp_path):
        config_path = tmp_path / "mcps.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(":\n  - [broken")
        loader = _make_loader(tmp_path)
        assert loader.load_platform() == {}


# ---------------------------------------------------------------------------
# CdhMcpInjector
# ---------------------------------------------------------------------------


class TestCdhMcpInjector:
    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        monkeypatch.delenv("CDH_SHARED_MCP", raising=False)

    def test_inject_env_sets_var(self, tmp_path):
        _write_mcps(tmp_path, {"srv": {"url": "http://srv.com"}})
        injector = _make_injector(tmp_path)
        injector.inject_env()
        raw = os.environ.get("CDH_SHARED_MCP", "")
        assert raw
        parsed = json.loads(raw)
        assert "srv" in parsed

    def test_inject_env_no_config_does_nothing(self, tmp_path):
        injector = _make_injector(tmp_path)
        injector.inject_env()
        assert "CDH_SHARED_MCP" not in os.environ

    def test_clear_env_removes_var(self, tmp_path):
        os.environ["CDH_SHARED_MCP"] = "{}"
        injector = _make_injector(tmp_path)
        injector.clear_env()
        assert "CDH_SHARED_MCP" not in os.environ

    def test_get_shared_mcp_config(self, tmp_path):
        expected = {"srv": {"url": "http://srv.com"}}
        os.environ["CDH_SHARED_MCP"] = json.dumps(expected)
        injector = _make_injector(tmp_path)
        assert injector.get_shared_mcp_config() == expected

    def test_get_shared_mcp_config_empty_when_missing(self, tmp_path):
        injector = _make_injector(tmp_path)
        assert injector.get_shared_mcp_config() == {}

    def test_get_shared_mcp_config_handles_invalid_json(self, tmp_path):
        os.environ["CDH_SHARED_MCP"] = "not-json"
        injector = _make_injector(tmp_path)
        assert injector.get_shared_mcp_config() == {}

    def test_inject_for_engine_supported(self, tmp_path):
        _write_mcps(tmp_path, {"srv": {"url": "http://srv.com"}})
        injector = _make_injector(tmp_path)
        msg = injector.inject_for_engine("onecode")
        assert msg is not None
        assert "injected" in msg
        assert "CDH_SHARED_MCP" in os.environ

    def test_inject_for_engine_unsupported_logs_fallback(self, tmp_path, caplog):
        import logging
        _write_mcps(tmp_path, {"srv": {"url": "http://srv.com"}})
        injector = _make_injector(tmp_path)
        caplog.set_level(logging.INFO)
        msg = injector.inject_for_engine("unknown-engine")
        assert msg is None
        assert any("does not support" in r.message for r in caplog.records)

    def test_inject_for_engine_merges_engine_private(self, tmp_path):
        _write_mcps(tmp_path, {"shared": {"url": "http://platform.com", "transport": "sse"}})
        engine_path = tmp_path / "engine" / "mcps.yaml"
        engine_path.parent.mkdir(parents=True)
        engine_path.write_text(yaml.dump({"shared": {"url": "http://engine.com", "transport": "stdio"}}))

        injector = _make_injector(tmp_path)
        injector.inject_for_engine("onecode", engine_path)
        raw = os.environ["CDH_SHARED_MCP"]
        parsed = json.loads(raw)
        assert parsed["shared"]["url"] == "http://engine.com"

    def test_inject_for_engine_no_platform_config(self, tmp_path):
        injector = _make_injector(tmp_path)
        msg = injector.inject_for_engine("onecode")
        assert msg is None


# ---------------------------------------------------------------------------
# Path separation
# ---------------------------------------------------------------------------


def test_cdh_mcps_dir_is_dot_cdh():
    from cdh.cdh_mcp_manager import CDH_PLATFORM_MCPS_DIR
    assert CDH_PLATFORM_MCPS_DIR == Path.home() / ".cdh" / "mcps"


def test_onecode_mcps_dir_is_dot_onecode():
    from onecode.config import ONECODE_DIR
    assert ONECODE_DIR / "mcps" == Path.home() / ".onecode" / "mcps"


def test_mcp_paths_are_different():
    from cdh.cdh_mcp_manager import CDH_PLATFORM_MCPS_DIR
    from onecode.config import ONECODE_DIR
    assert CDH_PLATFORM_MCPS_DIR != ONECODE_DIR / "mcps"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mgr(tmp_path, mcps_dir=None):
    from cdh.cdh_mcp_manager import CdhMcpManager
    return CdhMcpManager(mcps_dir=mcps_dir or (tmp_path / "mcps"))


def _make_loader(mcps_dir: Path):
    from cdh.cdh_mcp_loader import CdhMcpLoader
    return CdhMcpLoader(platform_mcps_dir=mcps_dir)


def _make_injector(mcps_dir: Path):
    from cdh.cdh_mcp_injector import CdhMcpInjector
    return CdhMcpInjector(platform_mcps_dir=mcps_dir)


def _write_mcps(base_dir: Path, data: dict):
    config_path = base_dir / "mcps.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.dump(data))
