"""GuideNPC — decides when and what companion bubbles to show."""

from __future__ import annotations

import random
import time

from agent_core.companion.memory import CompanionMemory
from agent_core.companion.observer import SilentObserver
from agent_core.companion.templates import (
    BondLevel,
    breed_talkativeness,
    compute_bond,
    pick_greeting,
    pick_idle_tip,
    pick_tool_note,
)

from agent_core.companion.types import CompanionBubble


def _days_ago(timestamp: float) -> int:
    return int((time.time() - timestamp) / 86400)


class GuideNPC:
    """Rule engine for companion bubbles — breed-aware, no LLM involved."""

    def __init__(self, memory: CompanionMemory, observer: SilentObserver, breed: str = "orange_tabby"):
        self._memory = memory
        self._observer = observer
        self._breed = breed
        self._greeted = False

    async def decide_bubble(self, uid: str) -> CompanionBubble | None:
        bond = compute_bond(self._observer)
        talk = breed_talkativeness(self._breed)

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
            text = pick_greeting(bond, days_away, self._breed)
            return CompanionBubble(text, ttl_ms=12_000, priority="greeting")

        # -- repeated tool use (breed-specific observation) --
        if self._observer.repeated_tool("bash", 3):
            note = pick_tool_note(self._breed, "bash")
            if note:
                return CompanionBubble(note, ttl_ms=10_000, priority="suggestion")

        # -- long session reminder --
        if self._observer.session_duration() > 3600:
            return CompanionBubble(
                "你已经连续聊了 1 小时，要不要休息一下？咪兔也有点困了...",
                ttl_ms=10_000,
                priority="care",
            )

        # -- random tip (probability scaled by talkativeness) --
        base_chance = 0.03 * (0.5 + talk)  # 话唠猫气泡更频繁
        if random.random() < base_chance:
            return CompanionBubble(
                pick_idle_tip(self._breed, self._observer.prompt_count),
                ttl_ms=8_000,
                priority="low",
            )

        return None
