"""CompanionExtension — hooks agent lifecycle to drive companion mood and bubbles."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from agent_core.core.events import (
    AgentEnd,
    AgentEvent,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
    TurnStart,
)
from agent_core.memory.base import MemoryStore

logger = logging.getLogger(__name__)


# ---- public types -----------------------------------------------------------


@dataclass
class CompanionEvent:
    type: str  # "ear_perk" | "busy" | "happy" | "sleeping" | "concerned"
    uid: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class CompanionBubble:
    text: str
    ttl_ms: int = 8000
    priority: str = "normal"


@dataclass
class CompanionBubbleEvent:
    uid: str
    bubble: CompanionBubble
    type: str = "companion_bubble"


# ---- extension --------------------------------------------------------------


class CompanionExtension:
    """Observes agent events and emits companion mood / bubble events.

    Optional observer + guide for memory-driven bubbles (Phase 4).
    If memory_store is provided, enables greeting bubbles, idle detection,
    tool-use suggestions, and session-duration reminders.
    """

    name = "companion"

    def __init__(
        self,
        uid: str,
        send_event: Callable[..., None],
        memory_store: MemoryStore | None = None,
    ):
        self._uid = uid
        self._send = send_event
        self._mood = "idle"
        self._last_bubble_at: float = 0
        self._last_active_at: float = 0

        # Phase 4: observer + guide (optional)
        self._observer = None
        self._guide = None
        if memory_store is not None:
            from agent_core.companion.memory import CompanionMemory
            from agent_core.companion.observer import SilentObserver
            from agent_core.companion.guide import GuideNPC

            cm = CompanionMemory(memory_store)
            self._observer = SilentObserver(cm)
            self._guide = GuideNPC(cm, self._observer)

    # -- protocol hooks -------------------------------------------------------

    async def on_event(self, ctx: Any, evt: AgentEvent) -> None:
        if isinstance(evt, TurnStart):
            self._mood = "listening"
            self._send(CompanionEvent("ear_perk", self._uid))
            if self._observer:
                prompt = ctx.metadata.get("prompt", "")
                await self._observer.on_prompt(self._uid, prompt)

        elif isinstance(evt, ToolExecutionStart):
            self._mood = "working"
            self._send(CompanionEvent("busy", self._uid))
            if self._observer:
                await self._observer.on_tool_start(self._uid, evt.tool_name)

        elif isinstance(evt, ToolExecutionEnd) and evt.is_error:
            self._mood = "concerned"
            self._send(CompanionBubbleEvent(
                self._uid,
                CompanionBubble("刚才好像出错了...", ttl_ms=8000, priority="care"),
            ))

        elif isinstance(evt, (TurnEnd, AgentEnd)):
            self._mood = "happy"
            self._send(CompanionEvent("happy", self._uid))
            if self._observer:
                await self._observer.on_turn_end(self._uid)
                await self._check_bubble_and_idle()

    async def on_before_agent_start(
        self, ctx: Any, prompt: str, system_prompt: str
    ) -> dict[str, Any] | None:
        if self._observer:
            await self._observer.on_session_start(self._uid)
        return None

    async def on_before_tool_call(self, ctx: Any, tool_call: Any) -> dict[str, Any] | None:
        return None

    async def on_after_tool_call(
        self, ctx: Any, tool_call: Any, result: Any, is_error: bool
    ) -> dict[str, Any] | None:
        return None

    # -- internal -------------------------------------------------------------

    async def _check_bubble_and_idle(self) -> None:
        now = time.time()
        gap = now - self._last_active_at
        if gap > 300 and self._observer:
            await self._observer.on_idle_return(self._uid, gap)
            self._mood = "sleeping"
            self._send(CompanionEvent("sleeping", self._uid))
        self._last_active_at = now

        if now - self._last_bubble_at < 30:
            return
        if self._guide:
            bubble = await self._guide.decide_bubble(self._uid)
            if bubble:
                self._last_bubble_at = now
                self._send(CompanionBubbleEvent(self._uid, bubble))
