"""Docker sandbox backend — isolated FileOperations + BashOperations."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from typing import Callable

from agent_core.tools.operations import (
    BashResult,
    FileInfo,
    SandboxBackend,
    SandboxQuota,
)

logger = logging.getLogger(__name__)


class DockerSandboxBackend(SandboxBackend):
    """Docker-based sandbox implementing FileOperations and BashOperations.

    A single instance provides both file and bash execution through
    a dedicated Docker container, with cgroup-based resource limits
    and a three-zone filesystem model.
    """

    def __init__(
        self,
        image: str = "python:3.11-slim",
        quota: SandboxQuota | None = None,
        host_output_dir: str | None = None,
    ) -> None:
        self.quota = quota or SandboxQuota()
        self._image = image
        self._container_id: str | None = None
        self._host_output_dir = host_output_dir or tempfile.mkdtemp(prefix="sandbox-output-")
        self._output_dir = "/mnt/output"
        self._tmp_dir = "/tmp"

    # ── SandboxBackend ──────────────────────────────────────────────

    async def start(self) -> None:
        if self._container_id is not None:
            return

        os.makedirs(self._host_output_dir, exist_ok=True)

        args = [
            "docker", "run", "-d",
            "--cpus", str(self.quota.cpu_cores),
            "--memory", f"{self.quota.memory_mb}m",
            "--memory-swap", f"{self.quota.memory_mb}m",
            "--storage-opt", f"size={self.quota.disk_mb}M",
            "-v", f"{self._host_output_dir}:{self._output_dir}",
            "--workdir", self._output_dir,
        ]

        if not self.quota.network_allowed:
            args.append("--network=none")

        args.append(self._image)
        args.extend(["tail", "-f", "/dev/null"])

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to start sandbox container: {stderr.decode()}")

        self._container_id = stdout.decode().strip()[:12]
        logger.info("Sandbox container started: %s", self._container_id)

    async def stop(self) -> None:
        if self._container_id is None:
            return
        await self._docker("stop", self._container_id)
        await self._docker("rm", "-f", self._container_id)
        self._container_id = None

    async def health_check(self) -> bool:
        if self._container_id is None:
            return False
        proc = await asyncio.create_subprocess_exec(
            "docker", "inspect", "-f", "{{.State.Running}}", self._container_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip() == "true"

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    # ── FileOperations ──────────────────────────────────────────────

    async def read(self, path: str, *, offset: int = 0, limit: int | None = None) -> str:
        self._validate_path(path)
        if offset or limit is not None:
            cmd = f"tail -n +{offset + 1} {self._safe(path)}"
            if limit is not None:
                cmd += f" | head -n {limit}"
            result = await self._docker_exec(["bash", "-c", cmd])
            return result.stdout
        result = await self._docker_exec(["cat", self._safe(path)])
        return result.stdout

    async def write(self, path: str, content: str) -> None:
        full_path = self._validate_path(path, writing=True)
        parent = os.path.dirname(full_path)
        await self._docker_exec(["mkdir", "-p", parent])
        # Write via stdin to avoid shell escaping issues
        await self._docker_exec_with_stdin(
            ["tee", self._safe(path)], content.encode("utf-8")
        )

    async def edit(self, path: str, old_text: str, new_text: str) -> bool:
        self._validate_path(path, writing=True)
        current = await self.read(path)
        if old_text not in current:
            return False
        updated = current.replace(old_text, new_text, 1)
        await self.write(path, updated)
        return True

    async def ls(self, path: str) -> list[FileInfo]:
        self._validate_path(path)
        safe = self._safe(path)
        result = await self._docker_exec(
            ["bash", "-c", f"ls -la {safe} | tail -n +2"]
        )
        entries: list[FileInfo] = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) < 9:
                continue
            name = " ".join(parts[8:])
            is_dir = parts[0].startswith("d")
            size = int(parts[4]) if not is_dir else 0
            entries.append(FileInfo(
                name=name,
                path=os.path.join(path, name),
                is_dir=is_dir,
                size=size,
            ))
        return entries

    async def grep(self, pattern: str, path: str, *, recursive: bool = False) -> list[str]:
        self._validate_path(path)
        args = ["grep", "-n"]
        if recursive:
            args.append("-r")
        args.extend([pattern, self._safe(path)])
        result = await self._docker_exec(args)
        return [l for l in result.stdout.split("\n") if l.strip()]

    async def find(self, path: str, *, name_pattern: str | None = None) -> list[str]:
        self._validate_path(path)
        args = ["find", self._safe(path), "-type", "f"]
        if name_pattern:
            args.extend(["-name", name_pattern])
        result = await self._docker_exec(args)
        return [l for l in result.stdout.split("\n") if l.strip()]

    # ── BashOperations ──────────────────────────────────────────────

    async def execute(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
        on_data: Callable[[bytes], None] | None = None,
        signal: asyncio.Event | None = None,
    ) -> BashResult:
        work_dir = self._safe(cwd) if cwd else self._safe(self._output_dir)
        effective_timeout = timeout or self.quota.timeout_seconds

        env_args: list[str] = []
        if env:
            for k, v in env.items():
                env_args.extend(["-e", f"{k}={v}"])

        exec_args = ["docker", "exec"]
        if work_dir:
            exec_args.extend(["-w", work_dir])
        exec_args.extend(env_args)
        exec_args.append(self._container_id)
        exec_args.extend(["bash", "-c", command])

        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        proc = None

        try:
            proc = await asyncio.create_subprocess_exec(
                *exec_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async def _read(stream, chunks, is_stderr=False):
                while True:
                    chunk = await stream.read(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    if on_data:
                        on_data(chunk)

            read_stdout = asyncio.create_task(_read(proc.stdout, stdout_chunks))
            read_stderr = asyncio.create_task(_read(proc.stderr, stderr_chunks))
            read_task = asyncio.gather(read_stdout, read_stderr)

            if signal is not None:
                abort_task = asyncio.create_task(signal.wait())
                done, pending = await asyncio.wait(
                    [read_task, abort_task],
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=effective_timeout,
                )
                if not done:
                    abort_task.cancel()
                    raise asyncio.TimeoutError()
                abort_task.cancel()
                if abort_task in done and proc.returncode is None:
                    await self._docker("kill", self._container_id)
                    read_task.cancel()
                    try:
                        await read_task
                    except asyncio.CancelledError:
                        pass
                    partial = b"".join(stdout_chunks).decode("utf-8", errors="replace")
                    return BashResult(stdout=partial, stderr="", returncode=-1)
                await read_task
            else:
                await asyncio.wait_for(read_task, timeout=effective_timeout)

            await proc.wait()
            stdout = b"".join(stdout_chunks).decode("utf-8", errors="replace")
            stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")
            return BashResult(stdout=stdout, stderr=stderr, returncode=proc.returncode or 0)

        except asyncio.TimeoutError:
            if proc is not None and proc.returncode is None:
                await self._docker("kill", self._container_id)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
            partial_stdout = b"".join(stdout_chunks).decode("utf-8", errors="replace")
            partial_stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")
            return BashResult(
                stdout=partial_stdout,
                stderr=partial_stderr + f"\nCommand timed out after {effective_timeout} seconds",
                returncode=-1,
                truncated=True,
            )

    # ── Internal helpers ────────────────────────────────────────────

    def _safe(self, path: str) -> str:
        """Escape a path for shell/shell command use by quoting."""
        return f"'{path}'"

    def _validate_path(self, path: str, *, writing: bool = False) -> str:
        """Ensure path is within allowed sandbox zones."""
        resolved = os.path.normpath(os.path.join("/", path))

        if resolved.startswith(self._output_dir):
            return resolved
        if resolved.startswith("/tmp"):
            return resolved
        # System dirs are read-only
        if not writing and (
            resolved.startswith("/usr")
            or resolved.startswith("/lib")
            or resolved.startswith("/bin")
            or resolved.startswith("/etc")
            or resolved.startswith("/opt")
        ):
            return resolved

        raise PermissionError(
            f"Path '{path}' is outside sandbox. Allowed: {self._output_dir}, /tmp, system dirs (read-only)."
        )

    async def _docker(self, *args: str) -> None:
        cmd = ["docker", *args]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

    async def _docker_exec(self, args: list[str]) -> BashResult:
        if self._container_id is None:
            raise RuntimeError("Sandbox container not started")

        cmd = ["docker", "exec", self._container_id, *args]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return BashResult(
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            returncode=proc.returncode or 0,
        )

    async def _docker_exec_with_stdin(self, args: list[str], data: bytes) -> BashResult:
        if self._container_id is None:
            raise RuntimeError("Sandbox container not started")

        cmd = ["docker", "exec", "-i", self._container_id, *args]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=data)
        return BashResult(
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            returncode=proc.returncode or 0,
        )
