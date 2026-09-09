"""Tests for MCPManager: opencode-style config + legacy compat + glob disable."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from onecode.mcp.config import CONFIG_FILENAME, LEGACY_CONFIG_FILENAME
from onecode.mcp.manager import MCPManager


@pytest.fixture
def cfg_paths(tmp_path) -> tuple[Path, Path]:
    new = tmp_path / CONFIG_FILENAME
    legacy = tmp_path / LEGACY_CONFIG_FILENAME
    return new, legacy


class TestMCPManagerCRUD:
    def test_add_stdio_persists(self, cfg_paths):
        new, legacy = cfg_paths
        m = MCPManager(config_path=new, legacy_config_path=legacy)
        m.add_stdio("foo", "npx", ["-y", "pkg"], {"K": "V"})
        assert new.exists()
        data = json.loads(new.read_text())
        assert data["mcp"]["foo"]["type"] == "local"
        assert data["mcp"]["foo"]["command"] == ["npx", "-y", "pkg"]
        assert data["mcp"]["foo"]["environment"] == {"K": "V"}

    def test_add_http_persists(self, cfg_paths):
        new, legacy = cfg_paths
        m = MCPManager(config_path=new, legacy_config_path=legacy)
        m.add_http("bar", "https://x", {"X-K": "v"})
        data = json.loads(new.read_text())
        assert data["mcp"]["bar"]["type"] == "remote"
        assert data["mcp"]["bar"]["headers"] == {"X-K": "v"}

    def test_add_sse_uses_remote(self, cfg_paths):
        new, legacy = cfg_paths
        m = MCPManager(config_path=new, legacy_config_path=legacy)
        m.add("baz", "https://sse", transport="sse")
        data = json.loads(new.read_text())
        assert data["mcp"]["baz"]["type"] == "remote"
        assert data["mcp"]["baz"]["url"] == "https://sse"

    def test_list_and_get_legacy_shape(self, cfg_paths):
        new, legacy = cfg_paths
        m = MCPManager(config_path=new, legacy_config_path=legacy)
        m.add_stdio("foo", "echo", ["hi"])
        listing = m.list()
        assert len(listing) == 1
        assert listing[0]["name"] == "foo"
        assert listing[0]["transport"] == "stdio"
        assert listing[0]["command"] == "echo"
        assert listing[0]["args"] == ["hi"]
        got = m.get("foo")
        assert got["transport"] == "stdio"

    def test_get_server_typed(self, cfg_paths):
        new, legacy = cfg_paths
        m = MCPManager(config_path=new, legacy_config_path=legacy)
        m.add_stdio("foo", "echo", ["hi"])
        sc = m.get_server("foo")
        assert sc is not None
        assert sc.type == "local"
        assert sc.command == ["echo", "hi"]

    def test_remove(self, cfg_paths):
        new, legacy = cfg_paths
        m = MCPManager(config_path=new, legacy_config_path=legacy)
        m.add_stdio("foo", "echo")
        m.remove("foo")
        assert m.get("foo") is None
        assert m.list() == []

    def test_enable_disable(self, cfg_paths):
        new, legacy = cfg_paths
        m = MCPManager(config_path=new, legacy_config_path=legacy)
        m.add_stdio("foo", "echo")
        assert m.enable("foo", False) is None
        assert m.get("foo")["enabled"] is False
        assert m.enable("nonexistent", True) == "MCP server 'nonexistent' not found"

    def test_duplicate_add_returns_error_via_cli(self, cfg_paths):
        # add_server directly; CLI handles duplicate detection
        new, legacy = cfg_paths
        m = MCPManager(config_path=new, legacy_config_path=legacy)
        from onecode.mcp.config import MCPServerConfig
        m.add_server("x", MCPServerConfig(name="x", type="local", command=["c"]))
        m.add_server("x", MCPServerConfig(name="x", type="local", command=["c"]))
        assert len(m.list()) == 1


class TestMCPManagerLoad:
    def test_loads_from_existing_json(self, tmp_path):
        new = tmp_path / "mcp.json"
        new.write_text(json.dumps({
            "mcp": {
                "foo": {"type": "local", "command": ["echo"], "environment": {"K": "V"}},
                "bar": {"type": "remote", "url": "https://x"},
            }
        }))
        m = MCPManager(config_path=new, legacy_config_path=tmp_path / "legacy.yaml")
        assert {s["name"] for s in m.list()} == {"foo", "bar"}
        sc = m.get_server("foo")
        assert sc.environment == {"K": "V"}

    def test_falls_back_to_legacy_yaml(self, tmp_path):
        legacy = tmp_path / "mcps.yaml"
        legacy.write_text(yaml.dump({
            "old": {"transport": "stdio", "command": "echo", "args": ["hi"], "env": {"X": "Y"}}
        }))
        m = MCPManager(
            config_path=tmp_path / "mcp.json",
            legacy_config_path=legacy,
        )
        assert "old" in {s["name"] for s in m.list()}
        sc = m.get_server("old")
        assert sc.command == ["echo", "hi"]
        assert sc.environment == {"X": "Y"}

    def test_empty_when_nothing_exists(self, tmp_path):
        m = MCPManager(
            config_path=tmp_path / "mcp.json",
            legacy_config_path=tmp_path / "mcps.yaml",
        )
        assert m.list() == []


class TestMCPManagerTemplates:
    def test_env_template_preserved_in_disk(self, cfg_paths):
        new, legacy = cfg_paths
        m = MCPManager(config_path=new, legacy_config_path=legacy)
        m.add_stdio("foo", "echo", env={"K": "{env:HOME}"})
        text = new.read_text()
        # Template not resolved on disk; only at connect-time.
        assert "{env:HOME}" in text


class TestGlobDisable:
    def test_glob_match(self, cfg_paths, monkeypatch, tmp_path):
        from onecode import config
        from onecode.config import save_config, GlobalConfig

        new, legacy = cfg_paths
        sandbox_cfg = tmp_path / "onecode.config.yaml"
        monkeypatch.setattr(config, "global_config_path", lambda: sandbox_cfg)

        cfg = GlobalConfig()
        cfg.mcp.disabled = ["cloudbase", "test-*"]
        save_config(cfg)

        m = MCPManager(config_path=new, legacy_config_path=legacy)
        assert m.is_globally_disabled("cloudbase")
        assert m.is_globally_disabled("test-foo")
        assert m.is_globally_disabled("test-anything")
        assert not m.is_globally_disabled("other")

    def test_empty_disabled_list_allows_all(self, cfg_paths):
        new, legacy = cfg_paths
        m = MCPManager(config_path=new, legacy_config_path=legacy)
        assert not m.is_globally_disabled("anything")
