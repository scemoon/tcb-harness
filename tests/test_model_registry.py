import pytest
from cdh.models.registry import ModelRegistry, REFERENCE_MODELS


def test_registry_initialize():
    ModelRegistry.initialize()
    assert len(ModelRegistry.list_all()) > 0


def test_get_model():
    ModelRegistry.initialize()
    model = ModelRegistry.get("claude-opus-4.7")
    assert model is not None
    assert model.provider == "anthropic"


def test_get_unknown_model():
    ModelRegistry.initialize()
    assert ModelRegistry.get("nonexistent-model") is None


def test_list_by_provider():
    ModelRegistry.initialize()
    anthropic_models = ModelRegistry.list_by_provider("anthropic")
    assert len(anthropic_models) >= 2
    for m in anthropic_models:
        assert m.provider == "anthropic"


def test_reference_table():
    ModelRegistry.initialize()
    table = ModelRegistry.reference_table()
    assert table is not None
