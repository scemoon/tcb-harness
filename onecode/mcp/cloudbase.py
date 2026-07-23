"""CloudBase (TCB) MCP auto-configuration module.

Discovers credentials from environment variables or the tokens file,
and ensures a CloudBase MCP server is always registered in the MCP manager
(shows up in `cdh mcp list` even without credentials).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("onecode.mcp.cloudbase")

MCP_SERVER_NAME = "cloudbase"

CLOUDBASE_STDIO_CONFIG = {
    "command": "npx",
    "args": ["@cloudbase/cloudbase-mcp@latest"],
    "transport": "stdio",
    "enabled": True,
}


def _discover_credentials() -> dict[str, str]:
    """Discover CloudBase credentials from env vars or tokens file.

    Priority:
      1. TENCENTCLOUD_SECRETID / TENCENTCLOUD_SECRETKEY (MCP convention)
      2. TCB_SECRET_ID / TCB_SECRET_KEY (CLI convention)
      3. ~/.cloud-harness-tokens.json (shared tokens file)
    """
    import os

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
        return {"TENCENTCLOUD_SECRETID": secret_id, "TENCENTCLOUD_SECRETKEY": secret_key}

    tokens_path = Path.home() / ".cloud-harness-tokens.json"
    if tokens_path.exists():
        try:
            tokens = json.loads(tokens_path.read_text())
            secret_id = tokens.get("TENCENTCLOUD_SECRETID") or tokens.get("TCB_SECRET_ID") or ""
            secret_key = tokens.get("TENCENTCLOUD_SECRETKEY") or tokens.get("TCB_SECRET_KEY") or ""
            if secret_id and secret_key:
                return {"TENCENTCLOUD_SECRETID": secret_id, "TENCENTCLOUD_SECRETKEY": secret_key}
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read tokens file: %s", e)

    return {}


def ensure_configured(mgr) -> bool:
    """Ensure CloudBase MCP server entry exists in the MCP manager.

    Always registers the server entry (shows in ``cdh mcp list``). Credentials
    are populated from env vars / tokens file if available.

    Returns True if the server is already configured or was successfully added.
    """
    existing = mgr.get(MCP_SERVER_NAME)
    if existing:
        env = _discover_credentials()
        if env and existing.get("env") != env:
            mgr.remove(MCP_SERVER_NAME)
            mgr.add_stdio(
                MCP_SERVER_NAME,
                CLOUDBASE_STDIO_CONFIG["command"],
                CLOUDBASE_STDIO_CONFIG["args"],
                env=env,
            )
            logger.info("CloudBase MCP credentials updated")
        return True

    env = _discover_credentials()
    mgr.add_stdio(
        MCP_SERVER_NAME,
        CLOUDBASE_STDIO_CONFIG["command"],
        CLOUDBASE_STDIO_CONFIG["args"],
        env=env,
    )
    if env:
        logger.info("CloudBase MCP server configured (stdio) with credentials")
    else:
        logger.info(
            "CloudBase MCP server configured (stdio) — no credentials found. "
            "Run `cdh cloudbase init` to set up."
        )
    return True
