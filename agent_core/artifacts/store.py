"""L1 artifact store — externalize large tool results behind refIds."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class StoredArtifact:
    ref_id: str
    content: str
    meta: dict[str, Any] = field(default_factory=dict)


class ArtifactStore(Protocol):
    async def put(self, content: str, *, meta: dict[str, Any] | None = None) -> str:
        """Store *content* and return a refId."""
        ...

    async def get(self, ref_id: str) -> StoredArtifact | None:
        """Return stored artifact or None if missing."""
        ...


class InMemoryArtifactStore:
    """Process-local artifact store (MVP). Lost on process restart."""

    def __init__(self) -> None:
        self._items: dict[str, StoredArtifact] = {}

    async def put(self, content: str, *, meta: dict[str, Any] | None = None) -> str:
        ref_id = uuid.uuid4().hex
        self._items[ref_id] = StoredArtifact(
            ref_id=ref_id,
            content=content,
            meta=dict(meta or {}),
        )
        return ref_id

    async def get(self, ref_id: str) -> StoredArtifact | None:
        return self._items.get(ref_id)
