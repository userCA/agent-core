"""Local filesystem and bash implementations of operations protocols."""

from __future__ import annotations

import asyncio
import os
import platform
import re
import signal as os_signal
from typing import Any, Callable

from agent_core.tools.operations import BashOperations, BashResult, FileInfo, FileOperations


class LocalFileOperations(FileOperations):
    """Default local file system implementation."""

    def __init__(self, cwd: str | None = None) -> None:
        self._cwd = cwd or os.getcwd()

    def _resolve(self, path: str) -> str:
        if not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        return os.path.normpath(path)

    async def read(self, path: str, *, offset: int = 0, limit: int | None = None) -> str:
        path = self._resolve(path)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            if offset or limit is not None:
                lines = f.readlines()
                start = offset
                end = start + (limit or len(lines))
                return "".join(lines[start:end])
            return f.read()

    async def write(self, path: str, content: str) -> None:
        path = self._resolve(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    async def edit(self, path: str, old_text: str, new_text: str) -> bool:
        path = self._resolve(path)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if old_text not in content:
            return False
        content = content.replace(old_text, new_text, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True

    async def ls(self, path: str) -> list[FileInfo]:
        path = self._resolve(path)
        entries: list[FileInfo] = []
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            entries.append(
                FileInfo(
                    name=name,
                    path=full,
                    is_dir=os.path.isdir(full),
                    size=os.path.getsize(full) if os.path.isfile(full) else 0,
                )
            )
        return entries

    async def grep(self, pattern: str, path: str, *, recursive: bool = False) -> list[str]:
        path = self._resolve(path)
        results: list[str] = []
        compiled = re.compile(pattern)

        def scan_file(file_path: str) -> None:
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if compiled.search(line):
                            results.append(f"{file_path}:{i}:{line.rstrip()}")
            except (IsADirectoryError, PermissionError, OSError):
                pass

        if os.path.isfile(path):
            scan_file(path)
        elif recursive:
            for root, _, files in os.walk(path):
                for name in files:
                    scan_file(os.path.join(root, name))
        else:
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                if os.path.isfile(full):
                    scan_file(full)
        return results

    async def find(self, path: str, *, name_pattern: str | None = None) -> list[str]:
        path = self._resolve(path)
        results: list[str] = []
        if os.path.isfile(path):
            return [path]
        for root, _, files in os.walk(path):
            for name in files:
                if name_pattern is None or re.search(name_pattern, name):
                    results.append(os.path.join(root, name))
        return results


def _kill_process_tree(pid: int) -> None:
    """Kill a process and all its children."""
    system = platform.system()
    try:
        if system == "Linux":
            os.kill(-pid, os_signal.SIGKILL)
        else:
            # macOS / BSD: pkill children first, then kill parent
            os.system(f"pkill -P {pid} 2>/dev/null")
            os.kill(pid, os_signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass


class LocalBashOperations(BashOperations):
    """Default local bash execution implementation."""

    def __init__(self, cwd: str | None = None, shell: str | None = None) -> None:
        self._cwd = cwd or os.getcwd()
        self._shell = shell or "/bin/bash"

    async def execute(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout: float | None = 60.0,
        env: dict[str, str] | None = None,
        on_data: Callable[[bytes], None] | None = None,
        signal: asyncio.Event | None = None,
    ) -> BashResult:
        work_dir = cwd or self._cwd
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        proc: asyncio.subprocess.Process | None = None

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                env={**os.environ, **(env or {})},
                start_new_session=True,
            )

            async def _read_stream(stream: asyncio.StreamReader | None, chunks: list[bytes]) -> None:
                if stream is None:
                    return
                while True:
                    chunk = await stream.read(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    if on_data:
                        on_data(chunk)

            read_stdout = asyncio.create_task(_read_stream(proc.stdout, stdout_chunks))
            read_stderr = asyncio.create_task(_read_stream(proc.stderr, stderr_chunks))
            read_task = asyncio.gather(read_stdout, read_stderr)

            if signal is not None:
                abort_task = asyncio.create_task(signal.wait())
                done, pending = await asyncio.wait(
                    [read_task, abort_task],
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=timeout,
                )
                if not done:
                    # Timeout — neither completed within deadline
                    abort_task.cancel()
                    raise asyncio.TimeoutError()
                abort_task.cancel()
                if abort_task in done and proc.returncode is None:
                    _kill_process_tree(proc.pid)
                    read_task.cancel()
                    try:
                        await read_task
                    except asyncio.CancelledError:
                        pass
                    # Wait briefly for the process to terminate after kill
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        pass
                    partial_stdout = b"".join(stdout_chunks).decode("utf-8", errors="replace")
                    partial_stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")
                    text = partial_stdout
                    if partial_stderr:
                        text += f"\n{partial_stderr}"
                    if not text.strip():
                        text = "Command aborted"
                    return BashResult(
                        stdout=text,
                        stderr="",
                        returncode=-1,
                        truncated=False,
                    )

                await read_task
            else:
                await asyncio.wait_for(read_task, timeout=timeout)

            await proc.wait()
            stdout = b"".join(stdout_chunks).decode("utf-8", errors="replace")
            stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")
            return BashResult(
                stdout=stdout,
                stderr=stderr,
                returncode=proc.returncode or 0,
            )

        except asyncio.TimeoutError:
            if proc is not None and proc.returncode is None:
                _kill_process_tree(proc.pid)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
            partial_stdout = b"".join(stdout_chunks).decode("utf-8", errors="replace")
            partial_stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")
            return BashResult(
                stdout=partial_stdout,
                stderr=partial_stderr + f"\nCommand timed out after {timeout} seconds",
                returncode=-1,
                truncated=True,
            )
