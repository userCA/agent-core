"""CompanionMemory — structured observations about user behavior.

Uses uid as session_id in the underlying MemoryStore so observations
persist across HTTP sessions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from agent_core.memory.base import MemoryStore

MAX_OBS_PER_USER = 200


@dataclass
class CompanionObservation:
    type: str  # "user_prompt" | "tool_use" | "idle_return"
    timestamp: float
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)


class CompanionMemory:
    """Lightweight structured memory for companion, separate from agent memory.

    Uses uid as the store session_id so observations survive across
    HTTP sessions.
    """

    def __init__(self, store: MemoryStore):
        self._store = store

    async def observe(self, uid: str, event: CompanionObservation) -> None:
        await self._store.remember(
            session_id=uid,
            text=event.summary,
            metadata={
                "obs_type": event.type,
                "ts": event.timestamp,
                **event.metadata,
            },
        )

    async def recall(self, uid: str, limit: int = 10) -> list[CompanionObservation]:
        records = await self._store.recall(
            session_id=uid,
            query="",
            limit=limit,
        )
        result: list[CompanionObservation] = []
        for r in records:
            meta = r.metadata or {}
            result.append(CompanionObservation(
                type=meta.get("obs_type", ""),
                timestamp=meta.get("ts", r.timestamp),
                summary=r.text,
                metadata={k: v for k, v in meta.items() if k not in ("obs_type", "ts")},
            ))
        return result
