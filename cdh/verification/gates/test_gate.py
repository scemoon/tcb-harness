from __future__ import annotations

import asyncio
import time
from pathlib import Path

from cdh.verification.aggregation import GateResult
from cdh.verification.gates.base import Gate


class TestGate(Gate):
    name = "test"
    test_dir: str = "tests"

    def __init__(self, test_dir: str = "tests"):
        self.test_dir = test_dir

    def should_run(self, file_path: str) -> bool:
        return file_path.endswith(".py")

    async def run(self, project_dir: str) -> GateResult:
        start = time.time()
        target = str(Path(project_dir) / self.test_dir)
        try:
            proc = await asyncio.create_subprocess_exec(
                "pytest", target, "-x", "--tb=short",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            duration = int((time.time() - start) * 1000)
            out = stderr.decode() or stdout.decode()
            return GateResult(
                name=self.name,
                status="passed" if proc.returncode == 0 else "failed",
                exit_code=proc.returncode,
                duration_ms=duration,
                summary=out[-800:] if len(out) > 800 else out,
            )
        except FileNotFoundError:
            return GateResult(name=self.name, status="skipped", summary="pytest not found")