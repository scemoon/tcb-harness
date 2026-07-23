from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModelInfo:
    id: str
    provider: str
    context_window: int = 0
    max_output: int = 4096
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    capabilities: list[str] = field(default_factory=list)
    description: str = ""


REFERENCE_MODELS: list[ModelInfo] = [
    # ── Anthropic (Claude) ──
    ModelInfo(
        id="claude-opus-4.7",
        provider="anthropic",
        context_window=200000,
        max_output=8192,
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
        capabilities=["reasoning", "coding", "analysis", "complex"],
        description="Claude Opus 4.7, Anthropic's most capable model",
    ),
    ModelInfo(
        id="claude-opus-4.7-fast",
        provider="anthropic",
        context_window=200000,
        max_output=8192,
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
        capabilities=["reasoning", "coding", "fast"],
        description="Claude Opus 4.7 Fast, faster inference variant",
    ),
    ModelInfo(
        id="claude-3-opus-20240229",
        provider="anthropic",
        context_window=200000,
        max_output=4096,
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
        capabilities=["reasoning", "coding", "analysis", "complex"],
        description="Most capable Anthropic model for complex tasks",
    ),
    ModelInfo(
        id="claude-3-sonnet-20240229",
        provider="anthropic",
        context_window=200000,
        max_output=4096,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        capabilities=["coding", "design", "medium"],
        description="Balanced Anthropic model for everyday tasks",
    ),
    ModelInfo(
        id="claude-3-haiku-20240307",
        provider="anthropic",
        context_window=200000,
        max_output=4096,
        cost_per_1k_input=0.00025,
        cost_per_1k_output=0.00125,
        capabilities=["quick", "simple", "summarization"],
        description="Fastest Anthropic model for simple tasks",
    ),
    # ── OpenAI ──
    ModelInfo(
        id="gpt-4o",
        provider="openai",
        context_window=128000,
        max_output=16384,
        cost_per_1k_input=0.005,
        cost_per_1k_output=0.015,
        capabilities=["reasoning", "coding", "vision", "complex"],
        description="OpenAI multimodal flagship model",
    ),
    ModelInfo(
        id="gpt-4-turbo",
        provider="openai",
        context_window=128000,
        max_output=4096,
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.03,
        capabilities=["reasoning", "coding", "complex"],
        description="OpenAI GPT-4 Turbo, fast and capable",
    ),
    ModelInfo(
        id="gpt-5.5-pro",
        provider="openai",
        context_window=128000,
        max_output=16384,
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.04,
        capabilities=["reasoning", "coding", "complex"],
        description="OpenAI GPT-5.5 Pro, most capable model",
    ),
    ModelInfo(
        id="gpt-5.5",
        provider="openai",
        context_window=128000,
        max_output=16384,
        cost_per_1k_input=0.005,
        cost_per_1k_output=0.015,
        capabilities=["reasoning", "coding", "general"],
        description="OpenAI GPT-5.5, balanced general-purpose model",
    ),
    # ── DeepSeek ──
    ModelInfo(
        id="deepseek-v4-pro",
        provider="deepseek",
        context_window=128000,
        max_output=8192,
        cost_per_1k_input=0.00055,
        cost_per_1k_output=0.00219,
        capabilities=["reasoning", "coding", "analysis", "complex"],
        description="DeepSeek V4 Pro, advanced reasoning model",
    ),
    ModelInfo(
        id="deepseek-v4-flash",
        provider="deepseek",
        context_window=128000,
        max_output=8192,
        cost_per_1k_input=0.00014,
        cost_per_1k_output=0.00028,
        capabilities=["coding", "general", "fast"],
        description="DeepSeek V4 Flash, fast cost-efficient model",
    ),
    ModelInfo(
        id="deepseek-chat",
        provider="deepseek",
        context_window=128000,
        max_output=8192,
        cost_per_1k_input=0.00014,
        cost_per_1k_output=0.00028,
        capabilities=["reasoning", "coding", "general"],
        description="DeepSeek general-purpose chat model",
    ),
    ModelInfo(
        id="deepseek-reasoner",
        provider="deepseek",
        context_window=128000,
        max_output=8192,
        cost_per_1k_input=0.00055,
        cost_per_1k_output=0.00219,
        capabilities=["reasoning", "analysis", "complex"],
        description="DeepSeek reasoning model for complex tasks",
    ),
    # ── MiniMax ──
    ModelInfo(
        id="minimax-m1",
        provider="minimax",
        context_window=1000000,
        max_output=16384,
        cost_per_1k_input=0.001,
        cost_per_1k_output=0.003,
        capabilities=["reasoning", "coding", "long-context", "complex"],
        description="MiniMax M1 flagship model with 1M context",
    ),
    ModelInfo(
        id="minimax-m1-light",
        provider="minimax",
        context_window=128000,
        max_output=8192,
        cost_per_1k_input=0.0002,
        cost_per_1k_output=0.0006,
        capabilities=["coding", "general", "cost-efficient"],
        description="MiniMax M1 Light, faster and cost-effective",
    ),
    ModelInfo(
        id="MiniMax-M3",
        provider="minimaxi",
        context_window=1000000,
        max_output=16384,
        cost_per_1k_input=0.001,
        cost_per_1k_output=0.003,
        capabilities=["reasoning", "coding", "long-context", "complex"],
        description="MiniMax M3 flagship model with 1M context",
    ),
    ModelInfo(
        id="MiniMax-M2.7",
        provider="minimaxi",
        context_window=128000,
        max_output=8192,
        cost_per_1k_input=0.0002,
        cost_per_1k_output=0.0006,
        capabilities=["coding", "general", "cost-efficient"],
        description="MiniMax M2.7, balanced and capable",
    ),
    ModelInfo(
        id="MiniMax-M2.5",
        provider="minimaxi",
        context_window=64000,
        max_output=4096,
        cost_per_1k_input=0.0001,
        cost_per_1k_output=0.0003,
        capabilities=["quick", "general", "cost-efficient"],
        description="MiniMax M2.5, fast and affordable",
    ),
    # ── Zhipu GLM ──
    ModelInfo(
        id="glm-5.1",
        provider="glm",
        context_window=128000,
        max_output=8192,
        cost_per_1k_input=0.007,
        cost_per_1k_output=0.007,
        capabilities=["reasoning", "coding", "analysis"],
        description="GLM-5.1, Zhipu's flagship model",
    ),
    ModelInfo(
        id="glm-5",
        provider="glm",
        context_window=128000,
        max_output=8192,
        cost_per_1k_input=0.004,
        cost_per_1k_output=0.004,
        capabilities=["coding", "general", "balanced"],
        description="GLM-5, balanced and capable",
    ),
    ModelInfo(
        id="glm-4-plus",
        provider="glm",
        context_window=128000,
        max_output=8192,
        cost_per_1k_input=0.007,
        cost_per_1k_output=0.007,
        capabilities=["reasoning", "coding", "analysis"],
        description="GLM-4 Plus, Zhipu's most advanced model",
    ),
    ModelInfo(
        id="glm-4-flash",
        provider="glm",
        context_window=128000,
        max_output=4096,
        cost_per_1k_input=0.0001,
        cost_per_1k_output=0.0001,
        capabilities=["quick", "general", "cost-efficient"],
        description="GLM-4 Flash, fast and affordable",
    ),
    # ── Ollama (local) ──
    ModelInfo(
        id="llama2",
        provider="ollama",
        context_window=4096,
        max_output=2048,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        capabilities=["local", "simple"],
        description="Local Llama 2 model via Ollama",
    ),
    ModelInfo(
        id="codellama",
        provider="ollama",
        context_window=16384,
        max_output=4096,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        capabilities=["local", "coding"],
        description="Local CodeLlama model via Ollama",
    ),
]


class ModelRegistry:
    _models: dict[str, ModelInfo] = {}

    _reference: dict[str, ModelInfo] = {m.id: m for m in REFERENCE_MODELS}

    @classmethod
    def initialize(cls):
        from onecode.config import load_config
        cfg = load_config()
        cls._models.clear()
        for provider, prov_cfg in cfg.providers.items():
            for model_id in prov_cfg.models:
                ref = cls._reference.get(model_id)
                cls._models[model_id] = ModelInfo(
                    id=model_id,
                    provider=provider,
                    context_window=ref.context_window if ref else 0,
                    max_output=ref.max_output if ref else 4096,
                    cost_per_1k_input=ref.cost_per_1k_input if ref else 0.0,
                    cost_per_1k_output=ref.cost_per_1k_output if ref else 0.0,
                    capabilities=list(ref.capabilities) if ref else [],
                    description=ref.description if ref else "",
                )
        # Also register any reference models not in config
        for m in REFERENCE_MODELS:
            if m.id not in cls._models:
                cls._models[m.id] = m

    @classmethod
    def get(cls, model_id: str) -> Optional[ModelInfo]:
        return cls._models.get(model_id)

    @classmethod
    def list_all(cls) -> list[ModelInfo]:
        return list(cls._models.values())

    @classmethod
    def list_by_provider(cls, provider: str) -> list[ModelInfo]:
        return [m for m in cls._models.values() if m.provider == provider]

    @classmethod
    def reference_table(cls) -> str:
        from rich.table import Table

        table = Table(title="Model Reference")
        table.add_column("Model", style="cyan")
        table.add_column("Provider", style="green")
        table.add_column("Context", justify="right")
        table.add_column("Input Cost", justify="right")
        table.add_column("Output Cost", justify="right")
        table.add_column("Capabilities")
        for m in cls._models.values():
            table.add_row(
                m.id,
                m.provider,
                f"{m.context_window:,}",
                f"${m.cost_per_1k_input:.5f}",
                f"${m.cost_per_1k_output:.5f}",
                ", ".join(m.capabilities),
            )
        return table
