"""SilentObserver — writes structured observations to CompanionMemory."""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from agent_core.companion.memory import CompanionMemory, CompanionObservation
from agent_core.companion.topic_extractor import extract_topic_hint

TOOL_HISTORY_LEN = 10


class SilentObserver:
    """Observes agent events, writes facts to CompanionMemory.

    Does not interrupt agent flow — all hooks return immediately.
    """

    def __init__(self, memory: CompanionMemory):
        self._memory = memory
        self._first_seen_at: float | None = None
        self._session_count = 0
        self._prompt_count = 0
        self._tool_use_count = 0
        self._recent_tools: deque[str] = deque(maxlen=TOOL_HISTORY_LEN)
        self.last_active_at: float = 0
        self._last_topic: str | None = None

    # -- queries used by GuideNPC --

    def days_since_first_seen(self) -> int:
        if not self._first_seen_at:
            return 0
        return int((time.time() - self._first_seen_at) / 86400)

    @property
    def prompt_count(self) -> int:
        return self._prompt_count

    @property
    def session_count(self) -> int:
        return self._session_count

    def session_duration(self) -> float:
        return time.time() - (self.last_active_at or time.time())

    def repeated_tool(self, tool: str, count: int) -> bool:
        if len(self._recent_tools) < count:
            return False
        recent = list(self._recent_tools)[-count:]
        return all(t == tool for t in recent)

    @property
    def last_topic(self) -> str | None:
        return self._last_topic

    # -- lifecycle hooks --

    async def on_session_start(self, uid: str) -> None:
        if self._first_seen_at is None:
            self._first_seen_at = time.time()
        self._session_count += 1
        self.last_active_at = time.time()

    async def on_prompt(self, uid: str, prompt: str) -> None:
        self._prompt_count += 1
        topic = extract_topic_hint(prompt)
        if topic and topic != self._last_topic:
            self._last_topic = topic
            await self._memory.observe(uid, CompanionObservation(
                type="user_prompt",
                timestamp=time.time(),
                summary=topic,
                metadata={"len": len(prompt)},
            ))

    async def on_tool_start(self, uid: str, tool: str) -> None:
        self._tool_use_count += 1
        self._recent_tools.append(tool)

    async def on_turn_end(self, uid: str) -> None:
        self.last_active_at = time.time()

    async def on_idle_return(self, uid: str, away_seconds: float) -> None:
        await self._memory.observe(uid, CompanionObservation(
            type="idle_return",
            timestamp=time.time(),
            summary=f"离开 {away_seconds:.0f}s 后回来",
            metadata={"away_s": away_seconds},
        ))
