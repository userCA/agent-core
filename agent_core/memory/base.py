"""MemoryStore Protocol and MemoryRecord type."""

from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class MemoryRecord(BaseModel):
    text: str
    session_id: str
    timestamp: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class MemoryStore(Protocol):
    async def remember(self, *, session_id: str, text: str, metadata: dict[str, Any] | None = None) -> None: ...
    async def recall(self, *, session_id: str, query: str, limit: int = 10) -> list[MemoryRecord]: ...
    async def forget(self, *, session_id: str) -> None: ...
