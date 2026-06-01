from __future__ import annotations

import asyncio
from typing import Optional

from cdha.cloud.base import CloudProvider


class TCBProvider(CloudProvider):
    name = "tcb"

    def __init__(self, region: str = "ap-shanghai", env_id: str = ""):
        self.region = region
        self.env_id = env_id

    async def _run_tcb(self, args: list[str], timeout: int) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
            return (stdout or stderr).decode()
        except FileNotFoundError:
            return "TCB CLI not found. Install with: npm install -g @cloudbase/cli"
        except asyncio.TimeoutError:
            return f"TCB command timed out."

    async def deploy(self, project_path: str, version: Optional[str] = None) -> str:
        args = ["tcb", "deploy", "--env", self.env_id, "--path", project_path]
        return await self._run_tcb(args, timeout=300)

    async def status(self) -> str:
        return f"TCB ({self.region}) - env: {self.env_id}"

    async def rollback(self, version: str) -> str:
        args = ["tcb", "rollback", "--env", self.env_id, "--version", version]
        return await self._run_tcb(args, timeout=120)
