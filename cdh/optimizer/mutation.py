from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cdh.optimizer.reward import SessionMetrics

AGENT_CONFIG_PATH = Path.home() / ".cdh" / "agent_config.yaml"


@dataclass
class ConfigMutation:
    platform_params: dict[str, Any] = field(default_factory=dict)
    engine_params: dict[str, dict[str, Any]] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    parent_reward: float = 0.0

    def to_dict(self) -> dict:
        return {
            "platform": self.platform_params,
            "engine": self.engine_params,
            "timestamp": self.timestamp,
            "parent_reward": self.parent_reward,
        }


PLATFORM_PARAMS = [
    "verification.policy",
    "verification.gates",
]

ENGINE_PARAMS = [
    "onecode.temperature",
    "onecode.max_iterations",
    "onecode.plan_gate_mode",
]


class ConfigMutator:
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)

    def suggest(self, history: list[SessionMetrics],
                current_reward: float) -> ConfigMutation | None:
        if not history:
            return None

        if current_reward < 0.5:
            return self._random_explore(current_reward)
        elif current_reward >= 0.8:
            return None
        else:
            return self._random_explore(current_reward)

    def _random_explore(self, current_reward: float) -> ConfigMutation | None:
        platform_params: dict[str, Any] = {}
        engine_params: dict[str, dict[str, Any]] = {}

        if self.rng.random() < 0.2:
            platform_params["verification.policy"] = self.rng.choice(
                ["conditional", "every_step", "final_only"]
            )

        onecode: dict[str, Any] = {}
        if self.rng.random() < 0.3:
            onecode["temperature"] = round(
                max(0.0, min(2.0, 0.7 + self.rng.uniform(-0.1, 0.1))), 2
            )
        if self.rng.random() < 0.3:
            onecode["max_iterations"] = max(5, 10 + self.rng.choice([-5, 0, 5]))
        if onecode:
            engine_params["onecode.dev"] = onecode

        platform = platform_params if platform_params else None
        engine = engine_params if engine_params else None
        if not platform and not engine:
            return None
        return ConfigMutation(
            platform_params=platform_params,
            engine_params=engine_params,
            parent_reward=current_reward,
        )