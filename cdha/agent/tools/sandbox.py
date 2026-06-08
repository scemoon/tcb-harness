from __future__ import annotations

import enum
import os
import resource
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


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
        os.chdir(ws)

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

        env = " ".join(f"{k}={v}" for k, v in os.environ.items() if k in self.config.env_whitelist or k.startswith("LC_"))
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
            except (ValueError, OSError, resource.error):
                pass
            try:
                mem_bytes = limits.memory_mb * 1024 * 1024
                resource.setrlimit(
                    resource.RLIMIT_AS, (mem_bytes, mem_bytes)
                )
            except (ValueError, OSError, resource.error):
                pass
            try:
                resource.setrlimit(
                    resource.RLIMIT_NPROC, (limits.max_procs, limits.max_procs + 5)
                )
            except (ValueError, OSError, resource.error):
                pass
            try:
                resource.setrlimit(
                    resource.RLIMIT_NOFILE,
                    (limits.max_open_files, limits.max_open_files + 10),
                )
            except (ValueError, OSError, resource.error):
                pass

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

    def _exec_bwrap(self, cmd: str, timeout: int) -> dict:
        bwrap_cmd = self._build_bwrap_cmd(cmd)

        try:
            result = subprocess.run(
                bwrap_cmd,
                capture_output=True,
                text=True,
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
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Container timed out", "sandbox": "docker"}
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
