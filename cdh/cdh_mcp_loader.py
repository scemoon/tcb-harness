"""cdh platform MCP loader — merges platform MCPs with engine-private MCPs.

Discovery order:
1. Read engine-private MCPs from engine's own config (e.g. ~/.onecode/mcps/mcps.yaml)
2. Read cdh platform MCPs from ~/.cdh/mcps/mcps.yaml
3. Merge: engine private wins on name conflict
4. Return merged list for injection
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from cdh.cdh_mcp_manager import CDH_PLATFORM_MCPS_DIR

logger = logging.getLogger("cdh.mcp.loader")


class CdhMcpLoader:
    def __init__(self, platform_mcps_dir: Path | None = None):
        self.platform_mcps_dir = platform_mcps_dir or CDH_PLATFORM_MCPS_DIR
        self._cache: dict[str, dict] | None = None

    def load_platform(self) -> dict[str, dict]:
        config_path = self.platform_mcps_dir / "mcps.yaml"
        if not config_path.exists():
            return {}
        try:
            data = yaml.safe_load(config_path.read_text()) or {}
            return {k: v for k, v in data.items() if isinstance(v, dict)}
        except Exception:
            logger.warning("Failed to load platform MCP config from %s", config_path)
            return {}

    def get_merged(
        self, engine_mcps_path: Path | None = None
    ) -> list[dict]:
        platform = self.load_platform()

        if engine_mcps_path and engine_mcps_path.exists():
            try:
                engine_data = yaml.safe_load(engine_mcps_path.read_text()) or {}
                engine_data = {k: v for k, v in engine_data.items() if isinstance(v, dict)}
            except Exception:
                engine_data = {}
        else:
            engine_data = {}

        merged = dict(platform)
        merged.update(engine_data)

        return [
            {"name": name, **cfg, "source": "engine" if name in engine_data else "platform"}
            for name, cfg in merged.items()
        ]

    def get_platform_only(self) -> list[dict]:
        return [
            {"name": name, **cfg, "source": "platform"}
            for name, cfg in self.load_platform().items()
        ]

    def invalidate_cache(self) -> None:
        self._cache = None
