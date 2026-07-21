"""Verify that a running shell command is actually terminated when the user
cancels the agent's turn (via ``cancel_check`` flipping to True, or via the
parent task being cancelled).  This guards the "提示取消实际还在运行" bug where
``process.communicate()`` blocked until the command finished naturally.
"""

import asyncio
import os
import signal
import tempfile
from pathlib import Path

import pytest

from onecode.agent.tools.sandbox import Sandbox, SandboxConfig, ResourceLimits, SandboxMode


def _make_sandbox(tmp_path: Path) -> Sandbox:
    cfg = SandboxConfig(
        workspace_root=tmp_path,
        mode=SandboxMode.NONE,
        network_enabled=False,
        resource_limits=ResourceLimits(),
    )
    return Sandbox(cfg)


async def _pid_still_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


async def _spawn_sleeper(sandbox: Sandbox, cancel_check, timeout: int = 30):
    """Run a command that writes its own pid to a file and then sleeps."""
    marker = sandbox.config.workspace_root / "pid.txt"
    cmd = f"echo $$ > {marker} && sleep 30"
    result = await sandbox.exec_async(cmd, timeout=timeout, cancel_check=cancel_check)
    return result, marker


async def test_cancel_check_terminates_process():
    """When cancel_check becomes True mid-run, the subprocess is killed."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        sandbox = _make_sandbox(tmp)
        state = {"cancelled": False}

        def cancel_check():
            return state["cancelled"]

        async def trigger():
            # Give the command time to start, then cancel.
            await asyncio.sleep(0.5)
            state["cancelled"] = True

        trigger_task = asyncio.ensure_future(trigger())
        result, marker = await _spawn_sleeper(sandbox, cancel_check)
        await trigger_task

        # The command must report cancellation, not run to completion.
        assert result.get("error") == "Cancelled", result
        assert result.get("success") is False

        # The child shell process must be gone.
        assert marker.exists(), "pid marker was never written"
        pid = int(marker.read_text().strip())
        # Allow a brief grace for reaping, then assert it is dead.
        for _ in range(50):
            if not await _pid_still_alive(pid):
                break
            await asyncio.sleep(0.1)
        assert not await _pid_still_alive(pid), f"pid {pid} still alive after cancel"


async def test_task_cancel_terminates_process():
    """Cancelling the awaiting task must terminate the child process too."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        sandbox = _make_sandbox(tmp)
        marker = tmp / "pid.txt"
        cmd = f"echo $$ > {marker} && sleep 30"

        def never_cancel():
            return False

        async def run():
            return await sandbox.exec_async(cmd, timeout=30, cancel_check=never_cancel)

        run_task = asyncio.ensure_future(run())
        # Let it start, then cancel the awaiting task.
        await asyncio.sleep(0.5)
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task

        assert marker.exists(), "pid marker was never written"
        pid = int(marker.read_text().strip())
        for _ in range(50):
            if not await _pid_still_alive(pid):
                break
            await asyncio.sleep(0.1)
        assert not await _pid_still_alive(pid), f"pid {pid} leaked after task cancel"
