from __future__ import annotations

import asyncio
import time
from pathlib import Path

from cdh.verification.aggregation import GateResult
from cdh.verification.gates.base import Gate
from cdh.verification.policy import is_source_file


class LintGate(Gate):
    name = "lint"

    def should_run(self, file_path: str) -> bool:
        return is_source_file(file_path)

    async def run(self, project_dir: str) -> GateResult:
        start = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                "ruff", "check", str(Path(project_dir)),
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
                summary=out[:500],
            )
        except FileNotFoundError:
            return GateResult(name=self.name, status="skipped", summary="ruff not found")