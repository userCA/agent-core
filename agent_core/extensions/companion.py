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

    Designed to be zero-coupling with MemoryExtension — both react to the
    same TurnEnd independently.
    """

    name = "companion"

    def __init__(self, uid: str, send_event: Callable[..., None]):
        self._uid = uid
        self._send = send_event
        self._mood = "idle"
        self._last_bubble_at: float = 0

    # -- protocol hooks -------------------------------------------------------

    async def on_event(self, ctx: Any, evt: AgentEvent) -> None:
        if isinstance(evt, TurnStart):
            self._mood = "listening"
            self._send(CompanionEvent("ear_perk", self._uid))

        elif isinstance(evt, ToolExecutionStart):
            self._mood = "working"
            self._send(CompanionEvent("busy", self._uid))

        elif isinstance(evt, ToolExecutionEnd) and evt.is_error:
            self._mood = "concerned"
            self._send(CompanionBubbleEvent(
                self._uid,
                CompanionBubble("刚才好像出错了...", ttl_ms=8000, priority="care"),
            ))

        elif isinstance(evt, (TurnEnd, AgentEnd)):
            self._mood = "happy"
            self._send(CompanionEvent("happy", self._uid))

    async def on_before_agent_start(
        self, ctx: Any, prompt: str, system_prompt: str
    ) -> dict[str, Any] | None:
        return None

    async def on_before_tool_call(self, ctx: Any, tool_call: Any) -> dict[str, Any] | None:
        return None

    async def on_after_tool_call(
        self, ctx: Any, tool_call: Any, result: Any, is_error: bool
    ) -> dict[str, Any] | None:
        return None
