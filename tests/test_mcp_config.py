"""Tests for the opencode-style MCP config layer."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from onecode.mcp.config import (
    CONFIG_FILENAME,
    LEGACY_CONFIG_FILENAME,
    MCPServerConfig,
    MCPConfigFile,
    _coerce_server,
    resolve_env_template,
    resolve_mapping,
)


@pytest.fixture
def tmp_config_dir() -> Path:
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


class TestResolveEnvTemplate:
    def test_literal(self):
        assert resolve_env_template("plain") == "plain"

    def test_env_var_substituted(self, monkeypatch):
        monkeypatch.setenv("MY_TEST_VAR", "hello")
        assert resolve_env_template("{env:MY_TEST_VAR}") == "hello"
        assert resolve_env_template("a-{env:MY_TEST_VAR}-b") == "a-hello-b"

    def test_env_var_missing_returns_empty(self):
        # warnings are emitted; assert no exception
        assert resolve_env_template("{env:DEFINITELY_NOT_SET_XYZ}") == ""

    def test_file_template(self, tmp_config_dir):
        tokens = tmp_config_dir / "tokens.json"
        tokens.write_text(json.dumps({"TENCENTCLOUD_SECRETID": "abc"}))
        assert resolve_env_template(f"{{file:{tokens}:TENCENTCLOUD_SECRETID}}") == "abc"

    def test_file_template_nested(self, tmp_config_dir):
        tokens = tmp_config_dir / "tokens.json"
        tokens.write_text(json.dumps({"a": {"b": "deep"}}))
        assert resolve_env_template(f"{{file:{tokens}:a.b}}") == "deep"

    def test_file_template_missing(self, tmp_config_dir):
        tokens = tmp_config_dir / "tokens.json"
        tokens.write_text(json.dumps({"a": 1}))
        assert resolve_env_template(f"{{file:{tokens}:b}}") == ""

    def test_non_string_passthrough(self):
        # The resolver only processes strings; other types pass through.
        assert resolve_env_template(42) == 42  # type: ignore[arg-type]


class TestResolveMapping:
    def test_empty(self):
        assert resolve_mapping(None) == {}
        assert resolve_mapping({}) == {}

    def test_substitutes_all(self, monkeypatch):
        monkeypatch.setenv("A", "1")
        monkeypatch.setenv("B", "2")
        out = resolve_mapping({"a": "{env:A}", "b": "{env:B}", "c": "literal"})
        assert out == {"a": "1", "b": "2", "c": "literal"}


class TestCoerceServer:
    def test_opencode_local(self):
        cfg = _coerce_server("x", {
            "type": "local",
            "command": ["npx", "-y", "pkg"],
            "environment": {"K": "V"},
        })
        assert cfg.type == "local"
        assert cfg.command == ["npx", "-y", "pkg"]
        assert cfg.environment == {"K": "V"}
        assert cfg.enabled is True

    def test_opencode_remote(self):
        cfg = _coerce_server("x", {
            "type": "remote",
            "url": "https://example.com",
            "headers": {"X-Key": "v"},
        })
        assert cfg.type == "remote"
        assert cfg.url == "https://example.com"
        assert cfg.headers == {"X-Key": "v"}

    def test_legacy_stdio(self):
        cfg = _coerce_server("x", {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "pkg"],
            "env": {"K": "V"},
        })
        assert cfg.type == "local"
        assert cfg.command == ["npx", "-y", "pkg"]
        assert cfg.environment == {"K": "V"}

    def test_legacy_http(self):
        cfg = _coerce_server("x", {
            "transport": "http",
            "url": "https://example.com",
            "headers": {"X": "Y"},
        })
        assert cfg.type == "remote"
        assert cfg.url == "https://example.com"
        assert cfg.headers == {"X": "Y"}

    def test_legacy_sse(self):
        cfg = _coerce_server("x", {
            "transport": "sse",
            "url": "https://example.com/sse",
        })
        assert cfg.type == "remote"
        assert cfg.url == "https://example.com/sse"

    def test_disabled(self):
        cfg = _coerce_server("x", {"type": "local", "command": ["c"], "enabled": False})
        assert cfg.enabled is False

    def test_timeout_parsed(self):
        cfg = _coerce_server("x", {"type": "local", "command": ["c"], "timeout": 90})
        assert cfg.timeout == 90


class TestMCPServerConfigValidate:
    def test_local_ok(self):
        cfg = MCPServerConfig(name="x", type="local", command=["c"])
        assert cfg.validate() == []

    def test_remote_ok(self):
        cfg = MCPServerConfig(name="x", type="remote", url="https://x")
        assert cfg.validate() == []

    def test_local_missing_command(self):
        cfg = MCPServerConfig(name="x", type="local")
        errs = cfg.validate()
        assert any("command" in e for e in errs)

    def test_remote_missing_url(self):
        cfg = MCPServerConfig(name="x", type="remote")
        errs = cfg.validate()
        assert any("url" in e for e in errs)

    def test_unknown_type(self):
        cfg = MCPServerConfig(name="x", type="weird")
        errs = cfg.validate()
        assert any("type" in e for e in errs)

    def test_to_legacy_local(self):
        cfg = MCPServerConfig(
            name="x", type="local",
            command=["npx", "-y", "pkg"],
            environment={"K": "V"},
        )
        legacy = cfg.to_legacy()
        assert legacy["transport"] == "stdio"
        assert legacy["command"] == "npx"
        assert legacy["args"] == ["-y", "pkg"]
        assert legacy["env"] == {"K": "V"}

    def test_to_legacy_remote_http(self):
        cfg = MCPServerConfig(
            name="x", type="remote",
            url="https://x", headers={"X": "Y"},
        )
        legacy = cfg.to_legacy()
        assert legacy["transport"] == "http"
        assert legacy["headers"] == {"X": "Y"}

    def test_to_legacy_remote_sse(self):
        cfg = MCPServerConfig(name="x", type="remote", url="https://x")
        legacy = cfg.to_legacy()
        assert legacy["transport"] == "sse"


class TestMCPConfigFileSaveLoad:
    def test_save_load_roundtrip(self, tmp_config_dir):
        path = tmp_config_dir / CONFIG_FILENAME
        cfg = MCPConfigFile(path=path)
        servers = {
            "a": MCPServerConfig(name="a", type="local", command=["npx"], environment={"K": "{env:HOME}"}),
            "b": MCPServerConfig(name="b", type="remote", url="https://x", headers={"Auth": "Bearer x"}),
        }
        cfg.save(servers)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["mcp"]["a"]["type"] == "local"
        assert data["mcp"]["a"]["command"] == ["npx"]
        assert data["mcp"]["b"]["type"] == "remote"
        assert data["mcp"]["b"]["url"] == "https://x"

        loaded = cfg.load()
        assert set(loaded.keys()) == {"a", "b"}
        assert loaded["a"].command == ["npx"]
        assert loaded["b"].headers == {"Auth": "Bearer x"}

    def test_load_legacy_fallback(self, tmp_config_dir):
        legacy = tmp_config_dir / LEGACY_CONFIG_FILENAME
        legacy.write_text(yaml.dump({
            "srv": {
                "transport": "stdio",
                "command": "echo",
                "args": ["hi"],
                "env": {"X": "Y"},
            }
        }))
        cfg = MCPConfigFile(
            path=tmp_config_dir / "mcp.json",
            legacy_path=legacy,
        )
        loaded = cfg.load()
        assert "srv" in loaded
        assert loaded["srv"].type == "local"
        assert loaded["srv"].command == ["echo", "hi"]
        assert loaded["srv"].environment == {"X": "Y"}

    def test_load_invalid_json_returns_empty(self, tmp_config_dir):
        path = tmp_config_dir / "mcp.json"
        path.write_text("{ not valid json")
        cfg = MCPConfigFile(path=path)
        assert cfg.load() == {}

    def test_load_validation_warns_but_includes(self, tmp_config_dir, caplog):
        path = tmp_config_dir / "mcp.json"
        path.write_text(json.dumps({
            "mcp": {
                "bad": {"type": "local"},  # missing command
                "good": {"type": "remote", "url": "https://x"},
            }
        }))
        cfg = MCPConfigFile(path=path)
        loaded = cfg.load()
        # Both entries are loaded, bad one has empty command
        assert "bad" in loaded
        assert "good" in loaded


class TestMigrateFromLegacy:
    def test_migrates_and_backs_up(self, tmp_config_dir):
        legacy = tmp_config_dir / LEGACY_CONFIG_FILENAME
        legacy.write_text(yaml.dump({
            "srv": {"transport": "stdio", "command": "echo", "args": ["hi"]}
        }))
        new = tmp_config_dir / "mcp.json"
        cfg = MCPConfigFile(path=new, legacy_path=legacy)
        assert cfg.migrate_from_legacy() is True
        assert not legacy.exists()
        assert legacy.with_suffix(".yaml.bak").exists()
        assert new.exists()
        data = json.loads(new.read_text())
        assert "srv" in data["mcp"]

    def test_no_legacy_returns_false(self, tmp_config_dir):
        cfg = MCPConfigFile(
            path=tmp_config_dir / "mcp.json",
            legacy_path=tmp_config_dir / LEGACY_CONFIG_FILENAME,
        )
        assert cfg.migrate_from_legacy() is False

    def test_already_migrated_returns_false(self, tmp_config_dir):
        legacy = tmp_config_dir / LEGACY_CONFIG_FILENAME
        legacy.write_text("srv: {transport: stdio, command: echo}")
        new = tmp_config_dir / "mcp.json"
        new.write_text("{}")
        cfg = MCPConfigFile(path=new, legacy_path=legacy)
        # Refuses to overwrite existing new file
        assert cfg.migrate_from_legacy() is False
