import pytest
from pathlib import Path
from cdha.config import GlobalConfig, AgentConfig, resolve_env, ensure_dirs


def test_default_config_values():
    cfg = GlobalConfig()
    assert cfg.default_mode == "agent"
    assert cfg.default_provider == "minimaxi"
    assert cfg.default_model == "MiniMax-M2.7"
    assert cfg.log_level == "info"
    assert cfg.session_auto_save is True


def test_config_overrides():
    cfg = GlobalConfig(
        default_mode="plan",
        log_level="debug",
        agent=AgentConfig(max_iterations=50),
    )
    assert cfg.default_mode == "plan"
    assert cfg.log_level == "debug"
    assert cfg.agent.max_iterations == 50


def test_resolve_env(monkeypatch):
    monkeypatch.setenv("MY_KEY", "secret123")
    assert resolve_env("${MY_KEY}") == "secret123"
    assert resolve_env("plain") == "plain"
    assert resolve_env("${NONEXISTENT}") == ""


def test_ensure_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr("cdha.config.CLOUD_DEV_HARNESS_DIR", tmp_path)
    ensure_dirs()
    assert (tmp_path / "sessions").exists()
    assert (tmp_path / "skills").exists()
    assert (tmp_path / "mcps").exists()
    assert (tmp_path / "traces").exists()
    assert (tmp_path / "logs").exists()
    assert (tmp_path / "models").exists()
    assert (tmp_path / "workspace").exists()
    assert (tmp_path / "workspace" / "projects").exists()
