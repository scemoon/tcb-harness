"""cdh platform MCP injector — injects platform MCPs into engines.

Strategies (per engine capability):
- env var: Set CDH_SHARED_MCP with JSON-serialized platform MCP configs
- CLI args: Inject via engine-specific CLI flags (--mcp-server name=url)
- config file: Write a temp config that the engine reads at startup

Name conflict: engine private MCPs win over cdh platform MCPs.
Engines that don't support injection get a silent fallback (INFO log).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("cdh.mcp.injector")

CDH_SHARED_MCP_ENV = "CDH_SHARED_MCP"


class CdhMcpInjector:
    SUPPORTED_ENGINES = {"onecode", "opencode"}

    def __init__(self, platform_mcps_dir: Path | None = None):
        from cdh.cdh_mcp_manager import CDH_PLATFORM_MCPS_DIR

        self.platform_mcps_dir = platform_mcps_dir or CDH_PLATFORM_MCPS_DIR

    def inject_env(self) -> None:
        """Set CDH_SHARED_MCP env var with platform MCP configs."""
        config_path = self.platform_mcps_dir / "mcps.yaml"
        if not config_path.exists():
            return
        try:
            data = yaml.safe_load(config_path.read_text()) or {}
            os.environ[CDH_SHARED_MCP_ENV] = json.dumps(data)
            logger.debug("Set %s with %d MCP servers", CDH_SHARED_MCP_ENV, len(data))
        except Exception as e:
            logger.warning("Failed to inject platform MCPs via env: %s", e)

    def clear_env(self) -> None:
        os.environ.pop(CDH_SHARED_MCP_ENV, None)

    def get_shared_mcp_config(self) -> dict[str, dict]:
        raw = os.environ.get(CDH_SHARED_MCP_ENV, "")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid %s value, ignoring", CDH_SHARED_MCP_ENV)
            return {}

    def inject_for_engine(
        self,
        engine_name: str,
        engine_mcps_path: Path | None = None,
    ) -> Optional[str]:
        """Inject platform MCPs for a specific engine.

        Returns an info/warning message, or None if no injection needed.

        For supported engines: sets CDH_SHARED_MCP env var.
        For unsupported engines: logs a silent INFO fallback.
        """
        platform_config = self._load_platform_config()
        if not platform_config:
            return None

        if engine_name not in self.SUPPORTED_ENGINES:
            logger.info(
                "Engine '%s' does not support cdh platform MCP injection. "
                "Platform MCPs available via %s env var.",
                engine_name,
                CDH_SHARED_MCP_ENV,
            )
            return None

        # Merge with engine private (engine wins)
        merged = dict(platform_config)
        if engine_mcps_path and engine_mcps_path.exists():
            try:
                engine_data = yaml.safe_load(engine_mcps_path.read_text()) or {}
                engine_data = {
                    k: v for k, v in engine_data.items() if isinstance(v, dict)
                }
            except Exception:
                engine_data = {}
            merged.update(engine_data)

        os.environ[CDH_SHARED_MCP_ENV] = json.dumps(merged)
        logger.debug(
            "Injected %d platform MCPs + %d engine MCPs via %s for '%s'",
            len(platform_config),
            len(engine_data) if engine_mcps_path and engine_mcps_path.exists() else 0,
            CDH_SHARED_MCP_ENV,
            engine_name,
        )
        return f"{len(platform_config)} platform MCP(s) injected for '{engine_name}'"

    def _load_platform_config(self) -> dict[str, dict]:
        config_path = self.platform_mcps_dir / "mcps.yaml"
        if not config_path.exists():
            return {}
        try:
            data = yaml.safe_load(config_path.read_text()) or {}
            return {k: v for k, v in data.items() if isinstance(v, dict)}
        except Exception:
            return {}
