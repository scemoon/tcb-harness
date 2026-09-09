from __future__ import annotations

import asyncio
import time
from typing import Any

from onecode.agent.turn_record import TurnRecord
from onecode.verification.aggregation import GateResult
from onecode.verification.gates.base import Gate


class TypeGate(Gate):
    name = "type"
    target_dir: str = "."

    def __init__(self, target_dir: str = "."):
        self.target_dir = target_dir

    def should_run(self, tool_name: str, tool_result: Any) -> bool:
        return tool_name in {"WriteTool", "EditTool", "InsertTool", "ApplyPatchTool"}

    async def run(self, turn_record: TurnRecord) -> GateResult:
        start = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                "mypy", self.target_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            duration = int((time.time() - start) * 1000)
            out = stderr.decode() or stdout.decode()
            passed = proc.returncode == 0
            return GateResult(
                name=self.name,
                status="passed" if passed else "failed",
                exit_code=proc.returncode,
                duration_ms=duration,
                summary=out[:500],
            )
        except FileNotFoundError:
            return GateResult(
                name=self.name,
                status="skipped",
                summary="mypy not found in PATH",
            )