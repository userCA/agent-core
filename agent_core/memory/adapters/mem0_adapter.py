from __future__ import annotations

import asyncio
from typing import Any

from agent_core.memory.base import MemoryRecord


class Mem0MemoryStore:
    def __init__(self, memory: Any | None = None) -> None:
        self._memory = memory
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._memory is not None:
            return self._memory
        if self._client is None:
            from mem0 import Memory

            self._client = Memory()
        return self._client

    async def remember(self, *, session_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        client = self._get_client()
        messages = [{"role": "user", "content": text}]
        await asyncio.to_thread(client.add, messages, user_id=session_id, metadata=metadata or {})

    async def recall(self, *, session_id: str, query: str, limit: int = 10) -> list[MemoryRecord]:
        client = self._get_client()
        result = await asyncio.to_thread(
            client.search, query, filters={"user_id": session_id}, top_k=limit
        )
        records: list[MemoryRecord] = []
        for item in result.get("results", []):
            text = item.get("memory") or item.get("text") or item.get("content", "")
            records.append(
                MemoryRecord(
                    text=text,
                    session_id=session_id,
                    metadata=item.get("metadata", {}) or {},
                )
            )
        return records

    async def forget(self, *, session_id: str) -> None:
        client = self._get_client()
        await asyncio.to_thread(client.delete_all, user_id=session_id)
