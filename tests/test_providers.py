import importlib
import pytest
from cdh.models.provider import Message, ProviderRegistry


def _load_providers():
    for mod_name in ["cdh.models.providers.anthropic_provider",
                     "cdh.models.providers.openai_provider",
                     "cdh.models.providers.ollama_provider"]:
        try:
            importlib.import_module(mod_name)
        except ImportError:
            pass


def test_provider_registry():
    _load_providers()
    providers = ProviderRegistry.list()
    assert "anthropic" in providers
    assert "openai" in providers
    assert "ollama" in providers


def test_provider_registry_get():
    from cdh.models.providers import AnthropicProvider
    cls = ProviderRegistry.get("anthropic")
    assert cls is AnthropicProvider


def test_message_creation():
    msg = Message(role="user", content="Hello")
    assert msg.role == "user"
    assert isinstance(msg.content, list)
    assert len(msg.content) == 1
    assert msg.content[0].text == "Hello"
