"""Tests for CloudBase MCP auto-config + tokens file helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from onecode.mcp.cloudbase import (
    MCP_SERVER_NAME,
    _default_config,
    clear_tokens,
    ensure_configured,
    write_tokens,
)
from onecode.mcp.config import CONFIG_FILENAME, LEGACY_CONFIG_FILENAME
from onecode.mcp.manager import MCPManager


@pytest.fixture
def fake_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    # Also clear any cloudbase-related env vars
    for k in (
        "TENCENTCLOUD_SECRETID",
        "TENCENTCLOUD_SECRETKEY",
        "CLOUDBASE_ENV_ID",
        "TCB_SECRET_ID",
        "TCB_SECRET_KEY",
        "TCB_ENV_ID",
    ):
        monkeypatch.delenv(k, raising=False)
    return home


class TestDefaultConfig:
    def test_opencode_shape(self):
        cfg = _default_config()
        assert cfg.type == "local"
        assert cfg.command == ["npx", "-y", "@cloudbase/cloudbase-mcp@latest"]
        # env uses templates
        assert cfg.environment == {
            "TENCENTCLOUD_SECRETID": "{env:TENCENTCLOUD_SECRETID}",
            "TENCENTCLOUD_SECRETKEY": "{env:TENCENTCLOUD_SECRETKEY}",
            "CLOUDBASE_ENV_ID": "{env:CLOUDBASE_ENV_ID}",
        }
        assert cfg.enabled is True


class TestEnsureConfigured:
    def test_registers_with_templates_when_no_credentials(self, fake_home):
        oc_dir = fake_home / ".onecode"
        oc_dir.mkdir(exist_ok=True)
        m = MCPManager(
            config_path=oc_dir / CONFIG_FILENAME,
            legacy_config_path=oc_dir / LEGACY_CONFIG_FILENAME,
        )
        assert ensure_configured(m) is True
        sc = m.get_server(MCP_SERVER_NAME)
        assert sc.type == "local"
        assert sc.environment["TENCENTCLOUD_SECRETID"] == "{env:TENCENTCLOUD_SECRETID}"

    def test_registers_with_literal_creds_from_env(self, fake_home, monkeypatch):
        oc_dir = fake_home / ".onecode"
        oc_dir.mkdir(exist_ok=True)
        monkeypatch.setenv("TENCENTCLOUD_SECRETID", "id123")
        monkeypatch.setenv("TENCENTCLOUD_SECRETKEY", "key456")
        monkeypatch.setenv("CLOUDBASE_ENV_ID", "env1")
        m = MCPManager(
            config_path=oc_dir / CONFIG_FILENAME,
            legacy_config_path=oc_dir / LEGACY_CONFIG_FILENAME,
        )
        ensure_configured(m)
        sc = m.get_server(MCP_SERVER_NAME)
        assert sc.environment["TENCENTCLOUD_SECRETID"] == "id123"
        assert sc.environment["CLOUDBASE_ENV_ID"] == "env1"

    def test_registers_with_literal_creds_from_tokens(self, fake_home):
        oc_dir = fake_home / ".onecode"
        oc_dir.mkdir(exist_ok=True)
        tokens = fake_home / ".cloud-harness-tokens.json"
        tokens.write_text(json.dumps({
            "TENCENTCLOUD_SECRETID": "tid",
            "TENCENTCLOUD_SECRETKEY": "tkey",
            "CLOUDBASE_ENV_ID": "tenv",
        }))
        m = MCPManager(
            config_path=oc_dir / CONFIG_FILENAME,
            legacy_config_path=oc_dir / LEGACY_CONFIG_FILENAME,
        )
        ensure_configured(m)
        sc = m.get_server(MCP_SERVER_NAME)
        assert sc.environment["TENCENTCLOUD_SECRETID"] == "tid"
        assert sc.environment["CLOUDBASE_ENV_ID"] == "tenv"

    def test_idempotent(self, fake_home):
        oc_dir = fake_home / ".onecode"
        oc_dir.mkdir(exist_ok=True)
        m = MCPManager(
            config_path=oc_dir / CONFIG_FILENAME,
            legacy_config_path=oc_dir / LEGACY_CONFIG_FILENAME,
        )
        assert ensure_configured(m) is True
        assert ensure_configured(m) is True
        assert len(m.list()) == 1


class TestTokensFile:
    def test_write_creates_file(self, fake_home):
        p = write_tokens("id1", "key1", "env1")
        assert p == fake_home / ".cloud-harness-tokens.json"
        data = json.loads(p.read_text())
        assert data["TENCENTCLOUD_SECRETID"] == "id1"
        assert data["CLOUDBASE_ENV_ID"] == "env1"

    def test_write_preserves_other_keys(self, fake_home):
        existing = fake_home / ".cloud-harness-tokens.json"
        existing.write_text(json.dumps({"OTHER": "value"}))
        p = write_tokens("id1", "key1")
        data = json.loads(p.read_text())
        assert data["OTHER"] == "value"
        assert data["TENCENTCLOUD_SECRETID"] == "id1"

    def test_clear_removes_keys(self, fake_home):
        p = fake_home / ".cloud-harness-tokens.json"
        p.write_text(json.dumps({
            "TENCENTCLOUD_SECRETID": "x",
            "TENCENTCLOUD_SECRETKEY": "y",
            "CLOUDBASE_ENV_ID": "z",
            "UNRELATED": "keep",
        }))
        assert clear_tokens() is True
        data = json.loads(p.read_text())
        assert "TENCENTCLOUD_SECRETID" not in data
        assert data["UNRELATED"] == "keep"

    def test_clear_no_file(self, fake_home):
        assert clear_tokens() is False

    def test_clear_empty_file(self, fake_home):
        (fake_home / ".cloud-harness-tokens.json").write_text("{}")
        assert clear_tokens() is False
