"""Pluggable operations protocols for file and bash execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class FileInfo:
    name: str
    path: str
    is_dir: bool
    size: int


class FileOperations(Protocol):
    """Abstract file operations. Allows local, SSH, or container backends."""

    async def read(self, path: str, *, offset: int = 0, limit: int | None = None) -> str: ...
    async def write(self, path: str, content: str) -> None: ...
    async def edit(self, path: str, old_text: str, new_text: str) -> bool: ...
    async def ls(self, path: str) -> list[FileInfo]: ...
    async def grep(self, pattern: str, path: str, *, recursive: bool = False) -> list[str]: ...
    async def find(self, path: str, *, name_pattern: str | None = None) -> list[str]: ...


@dataclass
class BashResult:
    stdout: str
    stderr: str
    returncode: int
    truncated: bool = False


class BashOperations(Protocol):
    """Abstract bash execution. Allows local, SSH, or container backends."""

    async def execute(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> BashResult: ...
