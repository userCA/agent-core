"""Session-scoped KV store for parameterBindings (H3)."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol


class SessionStateStore(Protocol):
    async def get(self, session_id: str, key: str) -> Any | None:
        """Return value for *key*, or None if missing."""
        ...

    async def has(self, session_id: str, key: str) -> bool:
        """Return True if *key* is present (even when value is None)."""
        ...

    async def set(self, session_id: str, key: str, value: Any) -> None:
        """Upsert *key* → *value* for the session."""
        ...

    async def delete(self, session_id: str, key: str) -> None:
        """Remove *key* if present."""
        ...

    async def clear(self, session_id: str) -> None:
        """Drop all keys for the session."""
        ...


class InMemorySessionStateStore:
    """Process-local session KV (MVP). Lost on process restart."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, session_id: str, key: str) -> Any | None:
        async with self._lock:
            bucket = self._data.get(session_id)
            if bucket is None:
                return None
            return bucket.get(key)

    async def has(self, session_id: str, key: str) -> bool:
        async with self._lock:
            bucket = self._data.get(session_id)
            return bucket is not None and key in bucket

    async def set(self, session_id: str, key: str, value: Any) -> None:
        async with self._lock:
            self._data.setdefault(session_id, {})[key] = value

    async def delete(self, session_id: str, key: str) -> None:
        async with self._lock:
            bucket = self._data.get(session_id)
            if bucket is not None:
                bucket.pop(key, None)

    async def clear(self, session_id: str) -> None:
        async with self._lock:
            self._data.pop(session_id, None)
