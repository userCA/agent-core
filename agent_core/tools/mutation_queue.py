"""Serialize concurrent file mutations per path."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncIterator

from agent_core.tools.operations import FileOperations


class FileMutationQueue:
    """Per-file async lock for serializing mutations."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    @asynccontextmanager
    async def acquire(self, path: str) -> AsyncIterator[None]:
        lock = self._locks[path]
        async with lock:
            yield

    async def read_locked(self, file_ops: FileOperations, path: str) -> str:
        async with self.acquire(path):
            return await file_ops.read(path)

    async def write_locked(self, file_ops: FileOperations, path: str, content: str) -> None:
        async with self.acquire(path):
            await file_ops.write(path, content)

    async def edit_locked(
        self, file_ops: FileOperations, path: str, old_text: str, new_text: str
    ) -> bool:
        async with self.acquire(path):
            return await file_ops.edit(path, old_text, new_text)
