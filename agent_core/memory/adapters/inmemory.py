"""In-memory MemoryStore — token-overlap ranking, recency fallback."""

from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from typing import Any

from agent_core.memory.base import MemoryRecord

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text)}


class InMemoryMemoryStore:
    def __init__(self) -> None:
        self._records: dict[str, list[MemoryRecord]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def remember(self, *, session_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        async with self._lock:
            self._records[session_id].append(MemoryRecord(text=text, session_id=session_id, metadata=metadata or {}))

    async def recall(self, *, session_id: str, query: str, limit: int = 10) -> list[MemoryRecord]:
        async with self._lock:
            records = list(self._records.get(session_id, []))
        if not records:
            return []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return list(reversed(records))[:limit]
        scored = [(len(q_tokens & _tokenize(r.text)), i, r) for i, r in enumerate(records)]
        scored.sort(key=lambda t: (-t[0], -t[1]))
        return [r for _, _, r in scored[:limit]]

    async def forget(self, *, session_id: str) -> None:
        async with self._lock:
            self._records.pop(session_id, None)
