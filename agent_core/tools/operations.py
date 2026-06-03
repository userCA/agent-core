"""Pluggable operations protocols for file and bash execution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable, Protocol


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
    full_output_path: str | None = None
    truncation_info: dict | None = None


class BashOperations(Protocol):
    """Abstract bash execution. Allows local, SSH, or container backends."""

    async def execute(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
        on_data: Callable[[bytes], None] | None = None,
        signal: asyncio.Event | None = None,
    ) -> BashResult: ...


@dataclass
class SandboxQuota:
    """Resource limits for sandboxed execution."""
    cpu_cores: float = 1.0
    memory_mb: int = 512
    timeout_seconds: int = 120
    disk_mb: int = 100
    network_allowed: bool = True
    allow_write_paths: list[str] = field(default_factory=list)
    deny_paths: list[str] = field(default_factory=list)


class SandboxBackend(Protocol):
    """Sandbox backend providing isolated file and bash execution.

    Implementations (Docker, gVisor, etc.) combine this with
    FileOperations and BashOperations.
    """

    quota: SandboxQuota

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def health_check(self) -> bool: ...
    async def restart(self) -> None: ...
