"""CloudBase (TCB) MCP auto-configuration module (opencode-style).

Discovers credentials from environment variables or the tokens file,
and ensures a CloudBase MCP server is always registered in the MCP manager
(shows up in `cdh mcp list` even without credentials).

The registered server uses the opencode declarative shape with
``{env:VAR}`` templates so the same config works whether credentials
are sourced from the environment or the shared tokens file at
``~/.cloud-harness-tokens.json``.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from onecode.mcp.config import MCPServerConfig

logger = logging.getLogger("onecode.mcp.cloudbase")

MCP_SERVER_NAME = "cloudbase"

TOKENS_FILENAME = ".cloud-harness-tokens.json"


def _default_config() -> MCPServerConfig:
    """Build the opencode-style CloudBase config with env templates.

    Templates are resolved at connect time by ``MCPManager.connect()``
    so the same on-disk config works whether the credentials are
    exported in the environment or stored in the tokens file (the
    token-file path is also exposed as a template).
    """
    return MCPServerConfig(
        name=MCP_SERVER_NAME,
        type="local",
        command=["npx", "-y", "@cloudbase/cloudbase-mcp@latest"],
        environment={
            "TENCENTCLOUD_SECRETID": "{env:TENCENTCLOUD_SECRETID}",
            "TENCENTCLOUD_SECRETKEY": "{env:TENCENTCLOUD_SECRETKEY}",
            "CLOUDBASE_ENV_ID": "{env:CLOUDBASE_ENV_ID}",
        },
        enabled=True,
    )


def _discover_credentials() -> dict[str, str]:
    """Discover CloudBase credentials from env vars or the tokens file.

    Priority:
      1. TENCENTCLOUD_SECRETID / TENCENTCLOUD_SECRETKEY (MCP convention)
      2. TCB_SECRET_ID / TCB_SECRET_KEY (CLI convention)
      3. ~/.cloud-harness-tokens.json (shared tokens file)

    Environment ID is picked up from CLOUDBASE_ENV_ID (MCP convention)
    or TCB_ENV_ID, and included as CLOUDBASE_ENV_ID in the returned dict.
    """
    env_id = os.environ.get("CLOUDBASE_ENV_ID") or os.environ.get("TCB_ENV_ID") or ""

    secret_id = (
        os.environ.get("TENCENTCLOUD_SECRETID")
        or os.environ.get("TCB_SECRET_ID")
        or ""
    )
    secret_key = (
        os.environ.get("TENCENTCLOUD_SECRETKEY")
        or os.environ.get("TCB_SECRET_KEY")
        or ""
    )

    if secret_id and secret_key:
        result = {"TENCENTCLOUD_SECRETID": secret_id, "TENCENTCLOUD_SECRETKEY": secret_key}
        if env_id:
            result["CLOUDBASE_ENV_ID"] = env_id
        return result

    tokens_path = Path.home() / TOKENS_FILENAME
    if tokens_path.exists():
        try:
            tokens = json.loads(tokens_path.read_text())
            secret_id = tokens.get("TENCENTCLOUD_SECRETID") or tokens.get("TCB_SECRET_ID") or ""
            secret_key = tokens.get("TENCENTCLOUD_SECRETKEY") or tokens.get("TCB_SECRET_KEY") or ""
            env_id = env_id or tokens.get("CLOUDBASE_ENV_ID") or tokens.get("TCB_ENV_ID") or ""
            if secret_id and secret_key:
                result = {"TENCENTCLOUD_SECRETID": secret_id, "TENCENTCLOUD_SECRETKEY": secret_key}
                if env_id:
                    result["CLOUDBASE_ENV_ID"] = env_id
                return result
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read tokens file: %s", e)

    return {}


def _credentials_match_env(credentials: dict[str, str], env: dict[str, str]) -> bool:
    """Return True if the discovered credentials are equivalent to the on-disk env."""
    if not credentials:
        return True
    for key, value in credentials.items():
        if env.get(key) != value:
            return False
    return True


def ensure_configured(mgr) -> bool:
    """Ensure a CloudBase MCP server entry exists in the MCP manager.

    Always registers the server entry (shows in ``cdh mcp list``) using
    the opencode-style config with ``{env:VAR}`` templates so credentials
    can be provided later through the environment or the tokens file.

    When credentials are already present in the environment or the
    tokens file, they are also written into the on-disk environment map
    so that ``cdh mcp list`` shows them masked. If the on-disk env
    differs from the current discovered credentials, the entry is
    refreshed and the caller is signalled that a reconnect is needed
    (return value ``False``).
    """
    existing = mgr.get_server(MCP_SERVER_NAME)
    discovered = _discover_credentials()

    if existing:
        # Existing entry: only refresh the in-disk env if credentials changed.
        if discovered and not _credentials_match_env(discovered, existing.environment):
            was_connected = mgr.is_connected(MCP_SERVER_NAME)
            cfg = _default_config()
            cfg.environment.update(discovered)
            mgr.add_server(MCP_SERVER_NAME, cfg)
            logger.info("CloudBase MCP credentials updated")
            if was_connected:
                logger.info("CloudBase MCP credentials changed, reconnect needed")
                return False
        return True

    cfg = _default_config()
    if discovered:
        cfg.environment.update(discovered)
    mgr.add_server(MCP_SERVER_NAME, cfg)
    if discovered:
        logger.info("CloudBase MCP server configured (local) with credentials")
    else:
        logger.info(
            "CloudBase MCP server configured (local) — no credentials found. "
            "Run `cdh cloudbase init` to set up."
        )
    return True


def write_tokens(secret_id: str, secret_key: str, env_id: str = "") -> Path:
    """Persist credentials to ``~/.cloud-harness-tokens.json``.

    Returns the path to the file.
    """
    tokens_path = Path.home() / TOKENS_FILENAME
    tokens: dict = {}
    if tokens_path.exists():
        try:
            tokens = json.loads(tokens_path.read_text()) or {}
        except (OSError, json.JSONDecodeError):
            tokens = {}
    tokens["TENCENTCLOUD_SECRETID"] = secret_id
    tokens["TENCENTCLOUD_SECRETKEY"] = secret_key
    if env_id:
        tokens["CLOUDBASE_ENV_ID"] = env_id
    tokens_path.write_text(json.dumps(tokens, indent=2) + "\n")
    return tokens_path


def clear_tokens() -> bool:
    """Remove the CloudBase credentials from the tokens file. Returns True if removed."""
    tokens_path = Path.home() / TOKENS_FILENAME
    if not tokens_path.exists():
        return False
    try:
        data = json.loads(tokens_path.read_text()) or {}
    except (OSError, json.JSONDecodeError):
        return False
    changed = False
    for k in ("TENCENTCLOUD_SECRETID", "TENCENTCLOUD_SECRETKEY", "CLOUDBASE_ENV_ID", "TCB_SECRET_ID", "TCB_SECRET_KEY", "TCB_ENV_ID"):
        if k in data:
            del data[k]
            changed = True
    if changed:
        tokens_path.write_text(json.dumps(data, indent=2) + "\n")
    return changed
