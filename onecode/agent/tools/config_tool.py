from __future__ import annotations

import logging
from typing import Any

from onecode.agent.tools.protocol import ToolResult
from onecode.agent.tools.registry import Tool, ToolSpec
from onecode.config import GlobalConfig

logger = logging.getLogger("onecode.tools.config")


class ConfigReadTool(Tool):
    """Read configuration values accessible to the LLM (Clawd-Code pattern)."""

    def __init__(self, config: GlobalConfig):
        self._config = config

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="ConfigRead",
            description="Read configuration values. Returns current config for the specified path (e.g. 'default_model', 'default_provider', 'tui.theme').",
            input_schema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Config key path (e.g. 'default_model', 'tui.theme'). Empty returns all.",
                    },
                },
            },
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        key = tool_input.get("key", "")
        if not key:
            return ToolResult(name="ConfigRead", output={"config": self._config_to_dict()})
        parts = key.split(".")
        val = self._resolve(self._config, parts)
        if val is None:
            return ToolResult(name="ConfigRead", output={"error": f"config key '{key}' not found"}, is_error=True)
        return ToolResult(name="ConfigRead", output={"key": key, "value": val})

    def _config_to_dict(self) -> dict:
        return {
            "default_model": self._config.default_model,
            "default_provider": self._config.default_provider,
            "default_mode": self._config.default_mode,
            "current_project": self._config.current_project,
            "tui.theme": self._config.tui.theme if self._config.tui else None,
            "log_level": self._config.log_level,
        }

    def _resolve(self, obj: Any, parts: list[str]) -> Any:
        current = obj
        for part in parts:
            if hasattr(current, part):
                current = getattr(current, part)
            elif isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current



class ConfigWriteTool(Tool):
    """Write configuration values accessible to the LLM (Clawd-Code pattern)."""

    def __init__(self, config: GlobalConfig, save_fn=None):
        self._config = config
        self._save_fn = save_fn

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="ConfigWrite",
            description="Set a configuration value. Path supports dot notation (e.g. 'tui.theme'). Only string/numeric values. Does NOT expose API keys or secrets.",
            input_schema={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Config key path (e.g. 'default_model', 'tui.theme')"},
                    "value": {"type": "string", "description": "Value to set"},
                },
                "required": ["key", "value"],
            },
        )

    ALLOWED_KEYS = {
        "default_model", "default_provider", "default_mode",
        "tui.theme", "log_level", "current_project",
    }

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        key = tool_input.get("key", "")
        value = tool_input.get("value", "")
        if key not in self.ALLOWED_KEYS:
            return ToolResult(
                name="ConfigWrite",
                output={"error": f"key '{key}' is not writable via this tool. Allowed: {sorted(self.ALLOWED_KEYS)}"},
                is_error=True,
            )
        parts = key.split(".")
        try:
            self._set(self._config, parts, value)
        except Exception as e:
            return ToolResult(name="ConfigWrite", output={"error": str(e)}, is_error=True)
        if self._save_fn:
            try:
                self._save_fn(self._config)
            except Exception as e:
                logger.warning("Config save failed: %s", e)
        return ToolResult(name="ConfigWrite", output={"key": key, "value": value, "status": "updated"})

    def _set(self, obj: Any, parts: list[str], value: Any) -> None:
        current = obj
        for part in parts[:-1]:
            if hasattr(current, part):
                current = getattr(current, part)
        last = parts[-1]
        if hasattr(current, last):
            field_type = type(getattr(current, last))
            if field_type is int:
                setattr(current, last, int(value))
            elif field_type is float:
                setattr(current, last, float(value))
            elif field_type is bool:
                setattr(current, last, value.lower() in ("true", "1", "yes"))
            else:
                setattr(current, last, value)

