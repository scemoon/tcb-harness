"""cdh platform MCP manager — operates ~/.cdh/mcps/.

This is the cdh platform equivalent of onecode.mcp.manager.MCPManager,
but operates strictly on ~/.cdh/mcps/ (cdh platform shared MCP pool).
Engines (onecode/opencode/claude) read platform MCPs via env var
injection at launch time (see cdh_mcp_injector.py).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("cdh.mcp")

CDH_PLATFORM_MCPS_DIR = Path.home() / ".cdh" / "mcps"


class CdhMcpManager:
    def __init__(self, mcps_dir: Path | None = None):
        self.mcps_dir = mcps_dir or CDH_PLATFORM_MCPS_DIR
        self.mcps_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.mcps_dir / "mcps.yaml"
        self._data: dict[str, dict] = {}
        if self.config_path.exists():
            try:
                self._data = yaml.safe_load(self.config_path.read_text()) or {}
            except Exception:
                self._data = {}

    def add(self, name: str, url: str, transport: str = "sse") -> None:
        self._data[name] = {"url": url, "transport": transport, "enabled": True}
        self._save()

    def add_stdio(self, name: str, command: str, args: list[str] | None = None) -> None:
        self._data[name] = {
            "command": command,
            "args": args or [],
            "transport": "stdio",
            "enabled": True,
        }
        self._save()

    def list(self) -> list[dict]:
        return [{"name": name, **cfg} for name, cfg in self._data.items()]

    def get(self, name: str) -> Optional[dict]:
        return self._data.get(name)

    def enable(self, name: str, enabled: bool = True) -> Optional[str]:
        if name not in self._data:
            return f"MCP server '{name}' not found"
        self._data[name]["enabled"] = enabled
        self._save()
        return None

    def remove(self, name: str) -> Optional[str]:
        if name not in self._data:
            return f"MCP server '{name}' not found"
        del self._data[name]
        self._save()
        return None

    def to_dict(self) -> dict[str, dict]:
        return dict(self._data)

    def _save(self) -> None:
        self.config_path.write_text(
            yaml.dump(self._data, default_flow_style=False), encoding="utf-8"
        )
