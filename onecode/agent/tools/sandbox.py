from __future__ import annotations

import asyncio
import enum
import logging
import os
import resource
import signal
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("onecode.sandbox")

# How often to poll cancel_check while a subprocess is running.  Small enough
# that a user cancel feels immediate, large enough to avoid busy-spinning.
CANCEL_POLL_INTERVAL = 0.1


class SandboxMode(enum.Enum):
    NONE = "none"
    BUBBLEWRAP = "bwrap"
    DOCKER = "docker"


@dataclass
class ResourceLimits:
    cpu_time: int = 30
    memory_mb: int = 512
    max_procs: int = 10
    max_open_files: int = 100
    max_pseudo_terminals: int = 0


@dataclass
class SandboxConfig:
    workspace_root: Path
    mode: SandboxMode = SandboxMode.NONE
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    read_only_bindings: tuple[str, ...] = ("/usr", "/bin", "/lib", "/lib64", "/opt", "/tmp")
    network_enabled: bool = False
    env_whitelist: tuple[str, ...] = ("PATH", "HOME", "USER", "TERM", "LANG", "LC_*")


class SandboxError(Exception):
    pass


class Sandbox:
    def __init__(self, config: SandboxConfig):
        self.config = config
        self._bwrap_available: Optional[bool] = None

    def _check_bwrap_available(self) -> bool:
        if self._bwrap_available is not None:
            return self._bwrap_available
        try:
            subprocess.run(["bwrap", "--version"], capture_output=True, check=True)
            self._bwrap_available = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            self._bwrap_available = False
        return self._bwrap_available

    def _build_bwrap_cmd(self, cmd: str) -> list[str]:
        ws = str(self.config.workspace_root.resolve())

        bwrap_args = ["bwrap"]

        bwrap_args.extend(["--dev", "/dev"])
        bwrap_args.extend(["--proc", "/proc"])

        bwrap_args.extend(["--bind", ws, "/workspace"])

        for ro_path in self.config.read_only_bindings:
            p = Path(ro_path)
            if p.exists():
                bwrap_args.extend(["--ro-bind", str(p), str(p)])

        bwrap_args.extend(["--tmpfs", "/tmp"])
        bwrap_args.extend(["--tmpfs", "/var/tmp"])

        if not self.config.network_enabled:
            bwrap_args.append("--unshare-net")

        bwrap_args.extend(["--uid", str(os.getuid())])
        bwrap_args.extend(["--gid", str(os.getgid())])

        bwrap_args.extend(["--setenv", "HOME", "/workspace"])
        bwrap_args.extend(["--setenv", "PATH", "/usr/local/sbin:/usr/local/bin:/usr/bin:/bin"])

        bwrap_args.extend(["--chdir", "/workspace"])

        bwrap_args.extend(["--", "sh", "-c", cmd])

        return bwrap_args

    def _set_resource_limits(self) -> None:
        """Deprecated: applied rlimits to the parent process which broke
        ``subprocess.run``.  Kept as a no-op for backward compatibility —
        use :meth:`_exec_direct` (which now applies the limits in a
        ``preexec_fn``) instead.
        """
        return

    def exec(self, cmd: str, timeout: int = 60) -> dict:
        """Public entry point — dispatches to the right backend for the mode."""
        mode = self.config.mode

        if mode == SandboxMode.NONE:
            return self._exec_direct(cmd, timeout)
        if mode == SandboxMode.BUBBLEWRAP:
            if self._check_bwrap_available():
                return self._exec_bwrap(cmd, timeout)
            return self._exec_direct(cmd, timeout)
        if mode == SandboxMode.DOCKER:
            return self._exec_docker(cmd, timeout)
        return self._exec_direct(cmd, timeout)

    async def exec_async(
        self, cmd: str, timeout: int = 60,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict:
        """Async public entry point — supports cancellation mid-execution."""
        mode = self.config.mode

        if mode == SandboxMode.NONE:
            return await self._exec_direct_async(cmd, timeout, cancel_check)
        if mode == SandboxMode.BUBBLEWRAP:
            if self._check_bwrap_available():
                return await self._exec_bwrap_async(cmd, timeout, cancel_check)
            return await self._exec_direct_async(cmd, timeout, cancel_check)
        if mode == SandboxMode.DOCKER:
            return await self._exec_docker_async(cmd, timeout, cancel_check)
        return await self._exec_direct_async(cmd, timeout, cancel_check)

    def _exec_direct(self, cmd: str, timeout: int) -> dict:
        # Apply resource limits in the *child* process only — calling
        # ``setrlimit`` on the parent (this Python interpreter) shrinks
        # its own address space, which then fails with ``EAGAIN`` on the
        # very next ``fork``/``execve`` that ``subprocess.run`` performs.
        limits = self.config.resource_limits

        def _preexec_apply_rlimits() -> None:  # pragma: no cover (runs in child)
            try:
                resource.setrlimit(
                    resource.RLIMIT_CPU, (limits.cpu_time, limits.cpu_time + 5)
                )
            except (ValueError, OSError, resource.error) as exc:
                logger.warning("RLIMIT_CPU setrlimit failed in preexec: %s", exc)
            try:
                mem_bytes = limits.memory_mb * 1024 * 1024
                resource.setrlimit(
                    resource.RLIMIT_AS, (mem_bytes, mem_bytes)
                )
            except (ValueError, OSError, resource.error) as exc:
                logger.warning("RLIMIT_AS setrlimit failed in preexec: %s", exc)
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(self.config.workspace_root),
                timeout=timeout,
                preexec_fn=_preexec_apply_rlimits,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "sandbox": "none",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timed out", "sandbox": "none"}
        except Exception as e:
            return {"success": False, "error": str(e), "sandbox": "none"}

    async def _exec_direct_async(
        self, cmd: str, timeout: int,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict:
        limits = self.config.resource_limits

        def _preexec_apply_rlimits() -> None:
            try:
                resource.setrlimit(
                    resource.RLIMIT_CPU, (limits.cpu_time, limits.cpu_time + 5)
                )
            except (ValueError, OSError, resource.error) as exc:
                logger.warning("RLIMIT_CPU setrlimit failed in preexec: %s", exc)
            try:
                mem_bytes = limits.memory_mb * 1024 * 1024
                resource.setrlimit(
                    resource.RLIMIT_AS, (mem_bytes, mem_bytes)
                )
            except (ValueError, OSError, resource.error) as exc:
                logger.warning("RLIMIT_AS setrlimit failed in preexec: %s", exc)
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.config.workspace_root),
            preexec_fn=_preexec_apply_rlimits,
            start_new_session=True,
        )
        return await self._run_with_cancel(process, timeout, cancel_check, "none")

    @staticmethod
    async def _terminate_process(process: asyncio.subprocess.Process) -> None:
        """Terminate a running subprocess tree, escalating to SIGKILL if needed.

        Subprocesses are started with ``start_new_session=True`` so they lead
        their own process group; we signal the whole group so child processes
        spawned by the shell (e.g. ``sleep``) are killed too, instead of being
        orphaned and keeping the output pipes open.
        """
        def _kill_group(sig: int) -> None:
            try:
                os.killpg(os.getpgid(process.pid), sig)
            except (ProcessLookupError, PermissionError):
                try:
                    process.send_signal(sig)
                except ProcessLookupError:
                    pass

        try:
            _kill_group(signal.SIGTERM)
            await asyncio.wait_for(process.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            _kill_group(signal.SIGKILL)
            await process.wait()
        except ProcessLookupError:
            pass

    async def _run_with_cancel(
        self,
        process: asyncio.subprocess.Process,
        timeout: int,
        cancel_check: Callable[[], bool] | None,
        sandbox: str,
    ) -> dict:
        """Await ``process.communicate()`` while polling ``cancel_check`` so a
        user cancel actually terminates the running command instead of blocking
        until it finishes naturally or hits ``timeout``.

        ``process`` must already be started.
        """
        communicate_task = asyncio.ensure_future(process.communicate())
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout if timeout else None
        try:
            while not communicate_task.done():
                if cancel_check is not None and cancel_check():
                    await self._terminate_process(process)
                    try:
                        await communicate_task
                    except Exception:
                        pass
                    return {"success": False, "error": "Cancelled", "sandbox": sandbox}
                if deadline is not None and loop.time() >= deadline:
                    await self._terminate_process(process)
                    try:
                        await communicate_task
                    except Exception:
                        pass
                    return {"success": False, "error": "Command timed out", "sandbox": sandbox}
                await asyncio.sleep(CANCEL_POLL_INTERVAL)
            stdout, stderr = await communicate_task
        except asyncio.CancelledError:
            # A cancelled parent turn must not leave the child process running.
            # Cancelling ``process.communicate()`` alone does NOT kill the
            # subprocess, so terminate it explicitly before re-raising.
            communicate_task.cancel()
            await self._terminate_process(process)
            try:
                await communicate_task
            except Exception:
                pass
            raise
        except Exception as e:
            await self._terminate_process(process)
            return {"success": False, "error": str(e), "sandbox": sandbox}
        stdout = stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else stdout
        stderr = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else stderr
        return {
            "success": process.returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": process.returncode,
            "sandbox": sandbox,
        }

    async def _exec_bwrap_async(
        self, cmd: str, timeout: int,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict:
        bwrap_cmd = self._build_bwrap_cmd(cmd)
        process = await asyncio.create_subprocess_exec(
            *bwrap_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.config.workspace_root),
            start_new_session=True,
        )
        return await self._run_with_cancel(process, timeout, cancel_check, "bwrap")

    def _exec_bwrap(self, cmd: str, timeout: int) -> dict:
        bwrap_cmd = self._build_bwrap_cmd(cmd)

        try:
            result = subprocess.run(
                bwrap_cmd,
                capture_output=True,
                text=True,
                cwd=str(self.config.workspace_root),
                timeout=timeout,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "sandbox": "bwrap",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timed out", "sandbox": "bwrap"}
        except FileNotFoundError:
            return {"success": False, "error": "bwrap not installed", "sandbox": "bwrap"}
        except Exception as e:
            return {"success": False, "error": str(e), "sandbox": "bwrap"}

    def _exec_docker(self, cmd: str, timeout: int) -> dict:
        import docker

        ws = str(self.config.workspace_root.resolve())

        docker_cmd = [
            "sh", "-c",
            f"cd /workspace && {cmd}"
        ]

        try:
            client = docker.from_env()
            container = client.containers.run(
                "alpine:latest",
                docker_cmd,
                detach=True,
                mem_limit=f"{self.config.resource_limits.memory_mb}m",
                cpu_period=100000,
                cpu_quota=self.config.resource_limits.cpu_time * 1000,
                network_mode="none" if not self.config.network_enabled else "bridge",
                volumes={ws: {"bind": "/workspace", "mode": "rw"}},
                working_dir="/workspace",
                user=f"{os.getuid()}:{os.getgid()}",
                remove=True,
            )
            result = container.wait(timeout=timeout)
            logs = container.logs().decode("utf-8", errors="replace")
            return {
                "success": result["StatusCode"] == 0,
                "stdout": logs,
                "stderr": "",
                "returncode": result["StatusCode"],
                "sandbox": "docker",
            }
        except docker.errors.DockerException:
            return {"success": False, "error": "Docker not available", "sandbox": "docker"}
        except docker.errors.TimeoutError:
            return {"success": False, "error": "Container timed out", "sandbox": "docker"}
        except Exception as e:
            return {"success": False, "error": str(e), "sandbox": "docker"}

    async def _exec_docker_async(
        self, cmd: str, timeout: int,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict:
        import docker

        ws = str(self.config.workspace_root.resolve())
        docker_cmd = ["sh", "-c", f"cd /workspace && {cmd}"]
        loop = asyncio.get_event_loop()

        try:
            client = await loop.run_in_executor(None, docker.from_env)
            container = await loop.run_in_executor(
                None,
                lambda: client.containers.run(
                    "alpine:latest",
                    docker_cmd,
                    detach=True,
                    mem_limit=f"{self.config.resource_limits.memory_mb}m",
                    cpu_period=100000,
                    cpu_quota=self.config.resource_limits.cpu_time * 1000,
                    network_mode="none" if not self.config.network_enabled else "bridge",
                    volumes={ws: {"bind": "/workspace", "mode": "rw"}},
                    working_dir="/workspace",
                    user=f"{os.getuid()}:{os.getgid()}",
                    remove=True,
                ),
            )

            deadline = loop.time() + timeout
            while True:
                if cancel_check and cancel_check():
                    await loop.run_in_executor(None, container.stop)
                    return {"success": False, "error": "Cancelled", "sandbox": "docker"}
                if loop.time() >= deadline:
                    await loop.run_in_executor(None, container.stop)
                    return {"success": False, "error": "Container timed out", "sandbox": "docker"}
                await asyncio.sleep(1)
                await loop.run_in_executor(None, container.reload)
                if container.status == "exited":
                    break

            exit_code = container.attrs["State"]["ExitCode"]
            logs = container.logs().decode("utf-8", errors="replace")
            return {
                "success": exit_code == 0,
                "stdout": logs,
                "stderr": "",
                "returncode": exit_code,
                "sandbox": "docker",
            }
        except docker.errors.DockerException:
            return {"success": False, "error": "Docker not available", "sandbox": "docker"}
        except Exception as e:
            return {"success": False, "error": str(e), "sandbox": "docker"}


def create_sandbox(
    workspace_root: Path,
    mode: str = "auto",
    **kwargs,
) -> Sandbox:
    if mode == "auto":
        sandbox_mode = SandboxMode.NONE
        if Path("/usr/bin/bwrap").exists():
            sandbox_mode = SandboxMode.BUBBLEWRAP
        elif Path("/var/run/docker.sock").exists():
            try:
                subprocess.run(["docker", "info"], capture_output=True, check=True)
                sandbox_mode = SandboxMode.DOCKER
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
    elif mode == "bwrap":
        sandbox_mode = SandboxMode.BUBBLEWRAP
    elif mode == "docker":
        sandbox_mode = SandboxMode.DOCKER
    else:
        sandbox_mode = SandboxMode.NONE

    config = SandboxConfig(
        workspace_root=workspace_root,
        mode=sandbox_mode,
        resource_limits=ResourceLimits(**kwargs) if kwargs else ResourceLimits(),
    )

    return Sandbox(config)
