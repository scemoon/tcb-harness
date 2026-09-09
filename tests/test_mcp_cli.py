"""Tests for the opencode-style MCP CLI surface (cdh mcp / cdh cloudbase)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from onecode.cli import cli


@pytest.fixture
def cli_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for k in (
        "TENCENTCLOUD_SECRETID",
        "TENCENTCLOUD_SECRETKEY",
        "CLOUDBASE_ENV_ID",
        "TCB_ENV_ID",
    ):
        monkeypatch.delenv(k, raising=False)
    return home


@pytest.fixture
def cli_runner(cli_home) -> CliRunner:
    return CliRunner()


class TestMCPAdd:
    def test_add_stdio_shortcut(self, cli_runner, cli_home):
        result = cli_runner.invoke(cli, [
            "mcp", "add", "my-tool",
            "--type", "stdio",
            "--command", "npx,-y,@modelcontextprotocol/server-everything",
            "--env", "FOO={env:HOME},BAR=literal",
        ])
        assert result.exit_code == 0, result.output
        cfg = json.loads((cli_home / ".onecode" / "mcp.json").read_text())
        assert cfg["mcp"]["my-tool"]["type"] == "local"
        assert cfg["mcp"]["my-tool"]["command"] == ["npx", "-y", "@modelcontextprotocol/server-everything"]
        assert cfg["mcp"]["my-tool"]["environment"]["FOO"] == "{env:HOME}"

    def test_add_http(self, cli_runner, cli_home):
        result = cli_runner.invoke(cli, [
            "mcp", "add", "remote1",
            "--type", "http",
            "--url", "https://example.com/mcp",
            "--headers", "Authorization=Bearer xyz,Content-Type=application/json",
        ])
        assert result.exit_code == 0, result.output
        cfg = json.loads((cli_home / ".onecode" / "mcp.json").read_text())
        assert cfg["mcp"]["remote1"]["type"] == "remote"
        assert cfg["mcp"]["remote1"]["url"] == "https://example.com/mcp"
        assert cfg["mcp"]["remote1"]["headers"]["Authorization"] == "Bearer xyz"

    def test_add_duplicate_errors(self, cli_runner):
        cli_runner.invoke(cli, [
            "mcp", "add", "x",
            "--type", "stdio", "--command", "echo",
        ])
        result = cli_runner.invoke(cli, [
            "mcp", "add", "x",
            "--type", "stdio", "--command", "echo",
        ])
        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_add_stdio_missing_command(self, cli_runner):
        result = cli_runner.invoke(cli, [
            "mcp", "add", "x", "--type", "stdio",
        ])
        assert result.exit_code != 0
        assert "command" in result.output.lower()


class TestMCPList:
    def test_list_masks_secrets(self, cli_runner, cli_home):
        cli_runner.invoke(cli, [
            "mcp", "add", "remote1",
            "--type", "http",
            "--url", "https://x",
            "--headers", "Authorization=Bearer secret123",
        ])
        result = cli_runner.invoke(cli, ["mcp", "list"])
        assert result.exit_code == 0
        assert "***" in result.output
        assert "secret123" not in result.output


class TestMCPMigrate:
    def test_dry_run(self, cli_runner, cli_home):
        legacy = cli_home / ".onecode" / "mcps.yaml"
        legacy.parent.mkdir(exist_ok=True)
        legacy.write_text(yaml.dump({"srv": {"transport": "stdio", "command": "echo", "args": ["hi"]}}))
        result = cli_runner.invoke(cli, ["mcp", "migrate", "--dry-run"])
        assert result.exit_code == 0
        assert "Would migrate" in result.output
        assert legacy.exists()  # not modified

    def test_migrate_creates_json_and_backup(self, cli_runner, cli_home):
        legacy = cli_home / ".onecode" / "mcps.yaml"
        legacy.parent.mkdir(exist_ok=True)
        legacy.write_text(yaml.dump({"srv": {"transport": "stdio", "command": "echo", "args": ["hi"]}}))
        result = cli_runner.invoke(cli, ["mcp", "migrate"])
        assert result.exit_code == 0
        assert "Migrated" in result.output
        assert not legacy.exists()
        assert legacy.with_suffix(".yaml.bak").exists()
        new = json.loads((cli_home / ".onecode" / "mcp.json").read_text())
        assert "srv" in new["mcp"]

    def test_migrate_no_legacy(self, cli_runner):
        result = cli_runner.invoke(cli, ["mcp", "migrate"])
        assert "nothing to migrate" in result.output


class TestMCPAuthLogout:
    def test_auth_stdio_rejected(self, cli_runner):
        cli_runner.invoke(cli, ["mcp", "add", "local-x", "--type", "stdio", "--command", "echo"])
        result = cli_runner.invoke(cli, ["mcp", "auth", "local-x"])
        assert "local" in result.output.lower()
        assert result.exit_code != 0

    def test_auth_remote_saves_token(self, cli_runner, cli_home):
        cli_runner.invoke(cli, [
            "mcp", "add", "remote-x",
            "--type", "http", "--url", "https://x",
        ])
        result = cli_runner.invoke(cli, ["mcp", "auth", "remote-x"], input="tok-abc\n")
        assert "saved" in result.output.lower()
        auth_file = cli_home / ".onecode" / "mcp-auth.json"
        assert auth_file.exists()
        data = json.loads(auth_file.read_text())
        assert "remote-x" in data
        assert data["remote-x"]["access_token"] == "tok-abc"

    def test_logout(self, cli_runner, cli_home):
        cli_runner.invoke(cli, [
            "mcp", "add", "remote-x", "--type", "http", "--url", "https://x",
        ])
        cli_runner.invoke(cli, ["mcp", "auth", "remote-x"], input="tok\n")
        result = cli_runner.invoke(cli, ["mcp", "logout", "remote-x"])
        assert "removed" in result.output.lower()
        data = json.loads((cli_home / ".onecode" / "mcp-auth.json").read_text())
        assert "remote-x" not in data

    def test_logout_no_auth(self, cli_runner):
        result = cli_runner.invoke(cli, ["mcp", "logout", "nothing"])
        assert "no oauth" in result.output.lower() or "No OAuth" in result.output


class TestMCPDebug:
    def test_debug_missing(self, cli_runner):
        result = cli_runner.invoke(cli, ["mcp", "debug", "missing"])
        assert "not configured" in result.output

    def test_debug_shows_config(self, cli_runner, cli_home, monkeypatch):
        cli_runner.invoke(cli, [
            "mcp", "add", "local-x",
            "--type", "stdio",
            "--command", "echo,hi",
            "--env", "K=V",
        ])
        # Patch connect so we don't spawn a real subprocess.
        from onecode.mcp import manager as mgr_mod

        async def fake_connect(self, name, auto_reconnect=True):
            return False

        monkeypatch.setattr(mgr_mod.MCPManager, "connect", fake_connect)
        result = cli_runner.invoke(cli, ["mcp", "debug", "local-x"])
        assert "Type:" in result.output
        assert "local" in result.output
        assert "echo hi" in result.output
        assert "K=***" in result.output


class TestCloudbase:
    def test_init_writes_opencode_config(self, cli_runner, cli_home):
        result = cli_runner.invoke(cli, [
            "cloudbase", "init",
            "--secret-id", "ID1",
            "--secret-key", "KEY1",
            "--env-id", "ENV1",
        ])
        assert result.exit_code == 0, result.output
        cfg = json.loads((cli_home / ".onecode" / "mcp.json").read_text())
        assert "cloudbase" in cfg["mcp"]
        cb = cfg["mcp"]["cloudbase"]
        assert cb["type"] == "local"
        assert cb["command"] == ["npx", "-y", "@cloudbase/cloudbase-mcp@latest"]
        assert cb["environment"]["TENCENTCLOUD_SECRETID"] == "ID1"
        # tokens file
        tokens = json.loads((cli_home / ".cloud-harness-tokens.json").read_text())
        assert tokens["TENCENTCLOUD_SECRETID"] == "ID1"
        assert tokens["CLOUDBASE_ENV_ID"] == "ENV1"

    def test_init_interactive_prompts(self, cli_runner, cli_home):
        result = cli_runner.invoke(
            cli,
            ["cloudbase", "init"],
            input="id-from-prompt\nkey-from-prompt\nenv-from-prompt\n",
        )
        assert result.exit_code == 0, result.output
        cfg = json.loads((cli_home / ".onecode" / "mcp.json").read_text())
        assert cfg["mcp"]["cloudbase"]["environment"]["TENCENTCLOUD_SECRETID"] == "id-from-prompt"

    def test_status_not_configured(self, cli_runner):
        result = cli_runner.invoke(cli, ["cloudbase", "status"])
        assert "not configured" in result.output.lower()

    def test_logout_clears_tokens(self, cli_runner, cli_home):
        cli_runner.invoke(cli, [
            "cloudbase", "init",
            "--secret-id", "ID1", "--secret-key", "KEY1",
        ])
        result = cli_runner.invoke(cli, ["cloudbase", "logout"])
        assert "removed" in result.output.lower()
        tokens_file = cli_home / ".cloud-harness-tokens.json"
        data = json.loads(tokens_file.read_text())
        assert "TENCENTCLOUD_SECRETID" not in data
