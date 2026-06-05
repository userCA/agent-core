"""GuideNPC — decides when and what companion bubbles to show."""

from __future__ import annotations

import random
import time

from agent_core.companion.memory import CompanionMemory
from agent_core.companion.observer import SilentObserver
from agent_core.companion.templates import (
    TOOL_SUGGESTIONS,
    BondLevel,
    compute_bond,
    pick_greeting,
    pick_idle_tip,
)

from agent_core.extensions.companion import CompanionBubble


def _days_ago(timestamp: float) -> int:
    return int((time.time() - timestamp) / 86400)


class GuideNPC:
    """Rule engine for companion bubbles — no LLM involved."""

    def __init__(self, memory: CompanionMemory, observer: SilentObserver):
        self._memory = memory
        self._observer = observer
        self._greeted = False

    async def decide_bubble(self, uid: str) -> CompanionBubble | None:
        bond = compute_bond(self._observer)

        # -- onboarding (low prompt count) --
        if self._observer.prompt_count <= 2:
            return CompanionBubble(
                "提示：按 / 可以切换模型，试试问我「帮我写一个脚本」吧！",
                ttl_ms=15_000,
                priority="onboarding",
            )

        # -- greeting on first turn of session --
        if not self._greeted:
            self._greeted = True
            observations = await self._memory.recall(uid, limit=5)
            days_away = 0
            if observations:
                last_ts = observations[-1].timestamp
                days_away = _days_ago(last_ts)
            text = pick_greeting(bond, days_away)
            return CompanionBubble(text, ttl_ms=12_000, priority="greeting")

        # -- repeated tool use --
        if self._observer.repeated_tool("bash", 3):
            return CompanionBubble(
                "你今天用了好多次终端呢，需要我帮你把这些命令写成脚本吗？",
                ttl_ms=10_000,
                priority="suggestion",
            )

        # -- long session reminder --
        if self._observer.session_duration() > 3600:
            return CompanionBubble(
                "你已经连续聊了 1 小时，要不要休息一下？咪兔也有点困了...",
                ttl_ms=10_000,
                priority="care",
            )

        # -- random tip (low probability) --
        if random.random() < 0.03:
            return CompanionBubble(
                pick_idle_tip(),
                ttl_ms=8_000,
                priority="low",
            )

        return None
