"""JSON-based MCP configuration (opencode-style).

Defines the ``~/.onecode/mcp.json`` declarative config schema and the
``{env:VAR}`` / ``{file:PATH:KEY}`` template resolver used to expand
references in environment variables and HTTP headers before a server
is started.

The on-disk file uses the same field names as opencode:

.. code-block:: json

    {
        "$schema": "...",
        "mcp": {
            "cloudbase": {
                "type": "local",
                "command": ["npx", "-y", "@cloudbase/cloudbase-mcp@latest"],
                "environment": {
                    "TENCENTCLOUD_SECRETID": "{env:TENCENTCLOUD_SECRETID}",
                    "TENCENTCLOUD_SECRETKEY": "{env:TENCENTCLOUD_SECRETKEY}",
                    "CLOUDBASE_ENV_ID": "{env:CLOUDBASE_ENV_ID}"
                },
                "enabled": true
            }
        }
    }

For backward compatibility, the loader also accepts the legacy
``mcps.yaml`` layout (``transport: stdio|http|sse``, ``command: str`` +
``args: list``, ``env: dict``) and converts it on load.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("onecode.mcp.config")

CONFIG_FILENAME = "mcp.json"
LEGACY_CONFIG_FILENAME = "mcps.yaml"

_ENV_PATTERN = re.compile(r"\{env:([A-Za-z_][A-Za-z0-9_]*)\}")
_FILE_PATTERN = re.compile(r"\{file:([^:}]+):([^:}]+)\}")


@dataclass
class MCPServerConfig:
    """One MCP server entry in the opencode-style JSON config."""

    name: str
    type: str = "local"  # "local" (stdio) or "remote" (sse/http)
    command: Optional[list[str]] = None
    url: Optional[str] = None
    environment: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    oauth: Any = None  # dict | bool | None
    enabled: bool = True
    timeout: Optional[int] = None
    cwd: Optional[str] = None
    # Legacy fields accepted on input for backward compatibility:
    transport: Optional[str] = None
    args: Optional[list[str]] = None
    env: Optional[dict[str, str]] = None

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty if valid)."""
        errors: list[str] = []
        if self.type not in ("local", "remote"):
            errors.append(
                f"MCP server '{self.name}': type must be 'local' or 'remote', got '{self.type}'"
            )
        if self.type == "local":
            if not self.command:
                errors.append(f"MCP server '{self.name}': 'command' is required for type=local")
        else:
            if not self.url:
                errors.append(f"MCP server '{self.name}': 'url' is required for type=remote")
        if self.timeout is not None and self.timeout <= 0:
            errors.append(f"MCP server '{self.name}': timeout must be > 0")
        return errors

    def to_legacy(self) -> dict[str, Any]:
        """Render in the legacy ``mcps.yaml`` shape used by existing clients."""
        if self.type == "local":
            cmd = self.command or []
            entry: dict[str, Any] = {
                "transport": "stdio",
                "command": cmd[0] if cmd else "",
                "args": list(cmd[1:]) if len(cmd) > 1 else (self.args or []),
                "enabled": self.enabled,
            }
            if self.environment:
                entry["env"] = dict(self.environment)
            elif self.env:
                entry["env"] = dict(self.env)
            if self.cwd:
                entry["cwd"] = self.cwd
        else:
            transport = "http" if self.headers else "sse"
            entry = {
                "transport": transport,
                "url": self.url or "",
                "enabled": self.enabled,
            }
            if self.headers:
                entry["headers"] = dict(self.headers)
        if self.timeout is not None:
            entry["timeout"] = self.timeout
        if self.oauth is not None:
            entry["oauth"] = self.oauth
        return entry

    def to_json(self) -> dict[str, Any]:
        """Render as a JSON-serializable dict (opencode shape)."""
        out: dict[str, Any] = {"type": self.type, "enabled": self.enabled}
        if self.type == "local":
            out["command"] = list(self.command or [])
            if self.environment:
                out["environment"] = dict(self.environment)
        else:
            out["url"] = self.url or ""
            if self.headers:
                out["headers"] = dict(self.headers)
            if self.oauth is not None:
                out["oauth"] = self.oauth
        if self.timeout is not None:
            out["timeout"] = self.timeout
        if self.cwd:
            out["cwd"] = self.cwd
        return out


def resolve_env_template(value: str, *, warn_missing: bool = True) -> str:
    """Expand ``{env:VAR}`` and ``{file:PATH:KEY}`` references in ``value``.

    Missing environment variables resolve to empty string and emit a
    warning (so a partially-configured environment does not break the
    whole MCP server).
    """
    if not isinstance(value, str) or "{" not in value:
        return value

    def _env_sub(m: re.Match[str]) -> str:
        var = m.group(1)
        val = os.environ.get(var)
        if val is None:
            if warn_missing:
                logger.warning("MCP config: env var %s is not set", var)
            return ""
        return val

    def _file_sub(m: re.Match[str]) -> str:
        path_str, key = m.group(1), m.group(2)
        try:
            data = json.loads(Path(path_str).expanduser().read_text())
        except (OSError, json.JSONDecodeError) as e:
            if warn_missing:
                logger.warning("MCP config: cannot read %s: %s", path_str, e)
            return ""
        cur: Any = data
        for part in key.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                if warn_missing:
                    logger.warning("MCP config: key %s not found in %s", key, path_str)
                return ""
        return str(cur)

    value = _ENV_PATTERN.sub(_env_sub, value)
    value = _FILE_PATTERN.sub(_file_sub, value)
    return value


def resolve_mapping(
    mapping: Optional[dict[str, str]], *, warn_missing: bool = True
) -> dict[str, str]:
    """Apply :func:`resolve_env_template` to every value in a mapping."""
    if not mapping:
        return {}
    return {k: resolve_env_template(v, warn_missing=warn_missing) for k, v in mapping.items()}


def _coerce_server(name: str, raw: dict[str, Any]) -> MCPServerConfig:
    """Normalize a raw dict (mixed legacy + opencode shape) to MCPServerConfig."""
    cfg = MCPServerConfig(name=name)

    # Type: opencode uses "type"; legacy uses "transport"
    if "type" in raw:
        cfg.type = str(raw["type"]).lower()
    elif "transport" in raw:
        transport = str(raw["transport"]).lower()
        cfg.type = "remote" if transport in ("http", "sse") else "local"

    # Command: opencode uses list; legacy uses str + args list
    if "command" in raw:
        cmd = raw["command"]
        if isinstance(cmd, list):
            cfg.command = [str(c) for c in cmd]
        else:
            cfg.command = [str(cmd)]
    if "args" in raw and isinstance(raw["args"], list):
        cfg.args = [str(a) for a in raw["args"]]
        if cfg.command is None:
            cfg.command = list(cfg.args)
            cfg.args = []
        elif len(cfg.command) == 1 and cfg.args:
            # legacy: command is single string, args is the list
            cfg.command = cfg.command + list(cfg.args)
            cfg.args = []

    # Environment: opencode uses "environment"; legacy uses "env"
    if "environment" in raw and isinstance(raw["environment"], dict):
        cfg.environment = {str(k): str(v) for k, v in raw["environment"].items()}
    if "env" in raw and isinstance(raw["env"], dict):
        cfg.env = {str(k): str(v) for k, v in raw["env"].items()}
        if not cfg.environment:
            cfg.environment = dict(cfg.env)

    # URL / headers / oauth / enabled / timeout / cwd
    if "url" in raw:
        cfg.url = str(raw["url"])
    if "headers" in raw and isinstance(raw["headers"], dict):
        cfg.headers = {str(k): str(v) for k, v in raw["headers"].items()}
    if "oauth" in raw:
        cfg.oauth = raw["oauth"]
    if "enabled" in raw:
        cfg.enabled = bool(raw["enabled"])
    if "timeout" in raw and raw["timeout"] is not None:
        try:
            cfg.timeout = int(raw["timeout"])
        except (TypeError, ValueError):
            pass
    if "cwd" in raw and raw["cwd"]:
        cfg.cwd = str(raw["cwd"])

    return cfg


class MCPConfigFile:
    """Loader / saver for the declarative ``mcp.json`` file."""

    def __init__(self, path: Optional[Path] = None, legacy_path: Optional[Path] = None):
        # Resolve ``Path.home()`` at construction time (not import time) so
        # tests that monkey-patch ``$HOME`` get isolated paths. We
        # intentionally do NOT depend on ``onecode.config.ONECODE_DIR``
        # here, since that constant is captured at import time and would
        # point to the production path even when ``$HOME`` has been
        # overridden by a test.
        if path is None:
            self.path = Path.home() / ".onecode" / CONFIG_FILENAME
        else:
            self.path = Path(path)
        if legacy_path is None:
            self.legacy_path = Path.home() / ".onecode" / LEGACY_CONFIG_FILENAME
        else:
            self.legacy_path = Path(legacy_path)

    def load(self) -> dict[str, MCPServerConfig]:
        """Load servers from ``mcp.json``, falling back to ``mcps.yaml``."""
        if self.path.exists():
            return self._load_json()
        if self.legacy_path.exists():
            logger.info(
                "MCP: legacy %s found; loading as fallback (run `cdh mcp migrate` to upgrade)",
                self.legacy_path.name,
            )
            return self._load_legacy()
        return {}

    def _load_json(self) -> dict[str, MCPServerConfig]:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            logger.error("MCP: failed to parse %s: %s", self.path, e)
            return {}
        mcp_section = data.get("mcp", {}) if isinstance(data, dict) else {}
        if not isinstance(mcp_section, dict):
            return {}
        out: dict[str, MCPServerConfig] = {}
        for name, raw in mcp_section.items():
            if not isinstance(raw, dict):
                continue
            cfg = _coerce_server(name, raw)
            errs = cfg.validate()
            if errs:
                for e in errs:
                    logger.warning("MCP config: %s", e)
            out[name] = cfg
        return out

    def _load_legacy(self) -> dict[str, MCPServerConfig]:
        try:
            import yaml
        except ImportError:
            logger.error("MCP: cannot load legacy YAML without PyYAML installed")
            return {}
        try:
            raw = yaml.safe_load(self.legacy_path.read_text()) or {}
        except (OSError, yaml.YAMLError) as e:
            logger.error("MCP: failed to parse %s: %s", self.legacy_path, e)
            return {}
        if not isinstance(raw, dict):
            return {}
        out: dict[str, MCPServerConfig] = {}
        for name, entry in raw.items():
            if not isinstance(entry, dict):
                continue
            out[name] = _coerce_server(name, entry)
        return out

    def save(self, servers: dict[str, MCPServerConfig]) -> None:
        """Persist ``servers`` to ``mcp.json`` (creates parent dir if needed)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "$schema": "https://opencode.ai/config.json",
            "mcp": {name: cfg.to_json() for name, cfg in servers.items()},
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    def migrate_from_legacy(self) -> bool:
        """One-shot migration from ``mcps.yaml`` -> ``mcp.json``.

        Returns True if a migration was performed, False if there was
        nothing to migrate.
        """
        if not self.legacy_path.exists():
            return False
        if self.path.exists():
            logger.info("MCP migrate: %s already exists; leaving legacy file alone", self.path.name)
            return False
        servers = self._load_legacy()
        if not servers:
            return False
        backup = self.legacy_path.with_suffix(self.legacy_path.suffix + ".bak")
        try:
            self.legacy_path.rename(backup)
        except OSError as e:
            logger.warning("MCP migrate: could not back up %s: %s", self.legacy_path, e)
        self.save(servers)
        logger.info(
            "MCP migrate: %d server(s) migrated to %s; legacy backed up to %s",
            len(servers),
            self.path.name,
            backup.name,
        )
        return True


__all__ = [
    "CONFIG_FILENAME",
    "LEGACY_CONFIG_FILENAME",
    "MCPServerConfig",
    "MCPConfigFile",
    "resolve_env_template",
    "resolve_mapping",
]
