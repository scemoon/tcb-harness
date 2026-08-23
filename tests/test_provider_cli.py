"""Tests for `cdh onecode config provider` CLI commands + config auto-populate."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from onecode.cli import cli
from onecode.config import ProviderConfig, global_config_path, load_config


@pytest.fixture
def fake_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


class TestProviderCLI:
    def test_get(self, fake_home):
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "provider", "get"])
        assert result.exit_code == 0, result.output
        assert "provider =" in result.output

    def test_set(self, fake_home):
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "provider", "set", "minimaxi"])
        assert result.exit_code == 0, result.output
        assert "minimaxi" in result.output

    def test_list_contains_registered_providers(self, fake_home):
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "provider", "list"])
        assert result.exit_code == 0, result.output
        assert "Available providers" in result.output
        # At least one known provider should be listed
        assert "minimaxi" in result.output or "openai" in result.output
        # The current one should be marked active
        assert "active" in result.output
        # Switch hint at the bottom
        assert "Switch with" in result.output


class TestLoadConfigAutoPopulate:
    def test_empty_providers_gets_defaults(self, fake_home):
        config_path = global_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("default_provider: minimaxi\nproviders: {}\n")
        cfg = load_config()
        # All default providers should now be present
        assert set(cfg.providers.keys()) >= {
            "anthropic", "openai", "deepseek", "minimax", "minimaxi", "glm", "ollama",
        }
        # All should be ProviderConfig instances, not raw dicts.
        for name, pcfg in cfg.providers.items():
            assert isinstance(pcfg, ProviderConfig), f"{name} is {type(pcfg)}"

    def test_existing_providers_preserved(self, fake_home):
        config_path = global_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            "default_provider: custom\n"
            "providers:\n"
            "  custom:\n"
            "    api_key: ${CUSTOM_KEY}\n"
            "    endpoint: https://x\n"
            "    models: [my-model]\n"
        )
        cfg = load_config()
        # Custom entry must be preserved exactly.
        assert "custom" in cfg.providers
        assert len(cfg.providers) == 1
        custom = cfg.providers["custom"]
        assert isinstance(custom, ProviderConfig)
        assert custom.api_key == "${CUSTOM_KEY}"
        assert custom.endpoint == "https://x"
        assert custom.models == ["my-model"]

    def test_handwritten_dict_normalized(self, fake_home):
        """A user-edited YAML may produce nested dicts; load should still
        produce proper ProviderConfig instances."""
        config_path = global_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            "providers:\n"
            "  myprov:\n"
            "    api_key: foo\n"
            "    endpoint: https://x\n"
            "    models: []\n"
        )
        cfg = load_config()
        assert isinstance(cfg.providers["myprov"], ProviderConfig)
        assert cfg.providers["myprov"].api_key == "foo"
