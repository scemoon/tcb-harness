from __future__ import annotations

import subprocess
from typing import Optional

from cdh.cloud.base import CloudProvider


class TCBProvider(CloudProvider):
    name = "tcb"

    def __init__(self, region: str = "ap-shanghai", env_id: str = ""):
        self.region = region
        self.env_id = env_id

    async def deploy(self, project_path: str, version: Optional[str] = None) -> str:
        try:
            result = subprocess.run(
                ["tcb", "deploy", "--env", self.env_id, "--path", project_path],
                capture_output=True,
                text=True,
                timeout=300,
            )
            return result.stdout or result.stderr
        except FileNotFoundError:
            return "TCB CLI not found. Install with: npm install -g @cloudbase/cli"
        except subprocess.TimeoutExpired:
            return "Deploy timed out."

    async def status(self) -> str:
        return f"TCB ({self.region}) - env: {self.env_id}"

    async def rollback(self, version: str) -> str:
        try:
            result = subprocess.run(
                ["tcb", "rollback", "--env", self.env_id, "--version", version],
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.stdout or result.stderr
        except FileNotFoundError:
            return "TCB CLI not found."
