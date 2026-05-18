"""Local filesystem and bash implementations of operations protocols."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

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
    ) -> BashResult:
        work_dir = cwd or self._cwd
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                env={**os.environ, **(env or {})},
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            return BashResult(
                stdout=stdout,
                stderr=stderr,
                returncode=proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return BashResult(
                stdout="",
                stderr=f"Command timed out after {timeout} seconds",
                returncode=-1,
                truncated=True,
            )
