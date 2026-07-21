from __future__ import annotations

import logging
import shutil
from enum import Enum
from typing import Any

import yaml

from cdh.event_loop.events import Event, EventTypes
from cdh.optimizer.mutation import ConfigMutator, ConfigMutation, AGENT_CONFIG_PATH
from cdh.optimizer.reward import RewardCalculator, SessionMetrics
from cdh.optimizer.tracker import OptimizationTracker

logger = logging.getLogger("cdh.optimizer.loop")

_VALID_PARAMS: dict[str, tuple[float, float]] = {
    "temperature": (0.0, 2.0),
    "max_iterations": (1, 200),
    "top_p": (0.0, 1.0),
} 


class HillclimbState(Enum):
    IDLE = "idle"
    COLLECTING = "collecting"
    EVALUATING = "evaluating"
    MUTATING = "mutating"
    DEPLOYING = "deploying"
    COMPLETED = "completed"
    FAILED = "failed"


class HillclimbLoop:
    def __init__(self, min_sessions: int = 3):
        self.state = HillclimbState.IDLE
        self._base_min_sessions = min_sessions
        self.min_sessions = min_sessions
        self.tracker = OptimizationTracker()
        self.reward_calc = RewardCalculator()
        self.mutator = ConfigMutator()
        self.bus: Any = None
        self._tool_count: int = 0
        self._test_pass_count: int = 0
        self._test_total_count: int = 0

    def start(self, bus: Any = None) -> None:
        self.state = HillclimbState.COLLECTING
        self.bus = bus
        self.tracker.initialize()
        logger.info("Hillclimb: started collecting, min_sessions=%d", self.min_sessions)

    def subscribe(self, bus: Any) -> None:
        bus.subscribe(EventTypes.SESSION_ENDED, self.on_session_ended)
        bus.subscribe(EventTypes.TOOL_EXECUTED, self._on_tool_executed)
        bus.subscribe(EventTypes.VERIFICATION_PASSED, self._on_verification_pass)
        bus.subscribe(EventTypes.VERIFICATION_FAILED, self._on_verification_fail)

    def _on_tool_executed(self, event: Event) -> None:
        if self.state == HillclimbState.COLLECTING:
            self._tool_count += 1

    def _on_verification_pass(self, event: Event) -> None:
        if self.state == HillclimbState.COLLECTING:
            self._test_total_count += 1
            self._test_pass_count += 1

    def _on_verification_fail(self, event: Event) -> None:
        if self.state == HillclimbState.COLLECTING:
            self._test_total_count += 1

    def on_session_ended(self, event: Event) -> None:
        if self.state != HillclimbState.COLLECTING:
            return

        payload = event.payload
        metrics = payload.get("metrics", {})

        test_pass_rate = (
            self._test_pass_count / max(self._test_total_count, 1)
            if self._test_total_count > 0
            else metrics.get("test_pass_rate", 0.0)
        )
        tool_efficiency = (
            min(1.0, 10.0 / max(self._tool_count, 1))
            if self._tool_count > 0
            else metrics.get("tool_efficiency", 0.0)
        )
        task_pct = metrics.get("task_completion_pct", None)

        session_metrics = SessionMetrics(
            session_id=payload.get("session_id", ""),
            test_pass_rate=test_pass_rate,
            task_completion_pct=task_pct if task_pct is not None else 0.0,
            tool_efficiency=tool_efficiency,
            turn_count=payload.get("turn_count", 0),
        )
        self.tracker.record(session_metrics)

        if self.tracker.count() >= self.min_sessions:
            self._run_optimization_cycle()

    def on_config_changed(self, event: Event) -> None:
        payload = event.payload
        mutation_data = payload.get("mutation", {})
        logger.info("Hillclimb: config changed via mutation %s", mutation_data)

    def _run_optimization_cycle(self) -> None:
        logger.info("Hillclimb: optimization cycle started (%d sessions)",
                    self.tracker.count())

        self.state = HillclimbState.EVALUATING
        all_metrics = self.tracker.get_all()
        baseline = self.reward_calc.compute_all(all_metrics)

        self.state = HillclimbState.MUTATING
        mutation = self.mutator.suggest(all_metrics, baseline)

        if mutation:
            self.state = HillclimbState.DEPLOYING
            self._apply_mutation(mutation)
            self.tracker.save_mutation(mutation)

        self.tracker.clear()
        self._tool_count = 0
        self._test_pass_count = 0
        self._test_total_count = 0
        self.min_sessions = min(self._base_min_sessions * 5, self.min_sessions + 2)
        self.state = HillclimbState.COLLECTING

        if mutation and self.bus:
            self.bus.publish(Event(
                type=EventTypes.CONFIG_CHANGED,
                source="cdh.optimizer",
                payload={"mutation": mutation.to_dict()},
            ))

    def _validate_mutation(self, mutation: ConfigMutation) -> list[str]:
        errors: list[str] = []
        onecode = mutation.engine_params.get("onecode.dev", {})
        for key, value in onecode.items():
            if key in _VALID_PARAMS:
                lo, hi = _VALID_PARAMS[key]
                if not (lo <= float(value) <= hi):
                    errors.append(f"{key}={value} out of range [{lo}, {hi}]")
            else:
                logger.debug("Unrecognised engine param in mutation: %s", key)
        return errors

    def _apply_mutation(self, mutation: ConfigMutation) -> None:
        errors = self._validate_mutation(mutation)
        if errors:
            logger.warning("Mutation rejected: %s", errors)
            return

        AGENT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

        if AGENT_CONFIG_PATH.exists():
            backup = AGENT_CONFIG_PATH.with_suffix(".yaml.bak")
            try:
                shutil.copy(AGENT_CONFIG_PATH, backup)
            except Exception as e:
                logger.warning("Failed to backup agent config: %s", e)

        config: dict[str, Any] = {}
        if AGENT_CONFIG_PATH.exists():
            try:
                config = yaml.safe_load(AGENT_CONFIG_PATH.read_text()) or {}
            except Exception as e:
                logger.warning("Hillclimb: failed to read agent config: %s", e)

        if "version" not in config:
            config["version"] = 1

        platform = config.setdefault("platform", {})
        for key, value in mutation.platform_params.items():
            self._set_nested(platform, key, value)

        engine = config.setdefault("engine", {})
        for engine_id, params in mutation.engine_params.items():
            if engine_id not in engine:
                engine[engine_id] = {}
            engine[engine_id].update(params)

        try:
            AGENT_CONFIG_PATH.write_text(yaml.dump(config, default_flow_style=False))
            logger.info("Hillclimb: applied mutation to %s", AGENT_CONFIG_PATH)
        except Exception as e:
            logger.warning("Hillclimb: failed to write agent config: %s", e)

    def _set_nested(self, config: dict, key: str, value: Any) -> None:
        parts = key.split(".")
        d = config
        for part in parts[:-1]:
            if part not in d:
                d[part] = {}
            d = d[part]
        d[parts[-1]] = value