"""CompanionExtension — hooks agent lifecycle to drive companion mood and bubbles."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from agent_core.companion.bones import roll_companion
from agent_core.companion.daily_rhythm import get_period, zzz_threshold_minutes
from agent_core.companion.state_machine import Emotion, EmotionFSM
from agent_core.companion.types import CompanionBubble
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

DECAY_CHECK_INTERVAL = 10  # seconds between decay checks


# ---- wire-format types ------------------------------------------------------


@dataclass
class CompanionEvent:
    type: str  # "ear_perk" | "busy" | "happy" | "sleeping" | "concerned" | "emotion"
    uid: str
    timestamp: float = field(default_factory=time.time)
    emotion: str = ""           # current emotion state
    eye_override: str | None = None  # sprite eye override
    frontend_mood: str = "awake"


@dataclass
class CompanionBubbleEvent:
    uid: str
    bubble: CompanionBubble
    type: str = "companion_bubble"


def companion_event_to_sse(evt: CompanionEvent | CompanionBubbleEvent) -> dict[str, object]:
    """Convert companion events to SSE-safe dicts."""
    if isinstance(evt, CompanionBubbleEvent):
        return {
            "event": "companion_bubble",
            "uid": evt.uid,
            "text": evt.bubble.text,
            "ttl_ms": evt.bubble.ttl_ms,
            "priority": evt.bubble.priority,
        }
    return {
        "event": "companion",
        "type": evt.type,
        "uid": evt.uid,
        "emotion": evt.emotion,
        "eye_override": evt.eye_override,
        "frontend_mood": evt.frontend_mood,
    }


# ---- extension --------------------------------------------------------------


class CompanionExtension:
    """Observes agent events and emits companion mood / bubble events.

    Drives a per-companion EmotionFSM for 6-state emotional depth.
    Always enables observer + guide for memory-driven bubbles.
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
        self._last_bubble_at: float = 0
        self._last_event_at: float = time.time()
        self._decay_task: asyncio.Task[Any] | None = None

        # deterministic bones for breed-specific emotion params
        bones = roll_companion(uid)
        self._bones = bones
        self._fsm = EmotionFSM(breed=bones.breed)

        # Phase 4: observer + guide
        if memory_store is None:
            from agent_core.memory.adapters.inmemory import InMemoryMemoryStore
            memory_store = InMemoryMemoryStore()
        from agent_core.companion.memory import CompanionMemory
        from agent_core.companion.observer import SilentObserver
        from agent_core.companion.guide import GuideNPC

        cm = CompanionMemory(memory_store)
        self._observer = SilentObserver(cm)
        self._guide = GuideNPC(cm, self._observer, breed=bones.breed)

    # -- protocol hooks -------------------------------------------------------

    async def on_event(self, ctx: Any, evt: AgentEvent) -> None:
        now = time.time()
        idle_s = now - self._last_event_at if self._last_event_at else 0

        if isinstance(evt, TurnStart):
            self._fsm.process("pet")  # user engagement = positive
            self._fsm.check_decay(idle_s)
            self._emit_state("ear_perk")
            prompt = ctx.metadata.get("prompt", "")
            await self._observer.on_prompt(self._uid, prompt)

        elif isinstance(evt, ToolExecutionStart):
            self._emit_state("busy")
            await self._observer.on_tool_start(self._uid, evt.tool_name)

        elif isinstance(evt, ToolExecutionEnd):
            if evt.is_error:
                self._fsm.process("tool_fail")
                self._emit_state("concerned")
                self._send(CompanionBubbleEvent(
                    self._uid,
                    CompanionBubble(_error_comfort(self._bones.breed), ttl_ms=8000, priority="care"),
                ))
            else:
                self._fsm.process("tool_ok")

        elif isinstance(evt, (TurnEnd, AgentEnd)):
            self._fsm.check_decay(idle_s)
            if idle_s >= 300:
                self._fsm.mark_idle(idle_s)
            self._emit_state("happy" if self._fsm.emotion in (Emotion.HAPPY, Emotion.EXCITED) else None)
            await self._observer.on_turn_end(self._uid)
            await self._check_bubble_and_idle()
            if isinstance(evt, AgentEnd):
                self._stop_decay_loop()

        self._last_event_at = time.time()

    async def on_before_agent_start(
        self, ctx: Any, prompt: str, system_prompt: str
    ) -> dict[str, Any] | None:
        await self._observer.on_session_start(self._uid)
        self._start_decay_loop()
        return None

    def _start_decay_loop(self) -> None:
        """Start background task that periodically decays emotion → NEUTRAL."""
        if self._decay_task is not None:
            return

        async def _loop() -> None:
            prev_emotion = ""
            while True:
                await asyncio.sleep(DECAY_CHECK_INTERVAL)
                idle_s = time.time() - self._last_event_at
                changed = bool(self._fsm.check_decay(idle_s))
                if changed or self._fsm.emotion != prev_emotion:
                    prev_emotion = self._fsm.emotion
                    self._emit_state(None)

        self._decay_task = asyncio.ensure_future(_loop())

    def _stop_decay_loop(self) -> None:
        if self._decay_task is not None:
            self._decay_task.cancel()
            self._decay_task = None

    async def on_before_tool_call(self, ctx: Any, tool_call: Any) -> dict[str, Any] | None:
        return None

    async def on_after_tool_call(
        self, ctx: Any, tool_call: Any, result: Any, is_error: bool
    ) -> dict[str, Any] | None:
        return None

    # -- internal -------------------------------------------------------------

    def _emit_state(self, event_type: str | None) -> None:
        """Send current FSM state as CompanionEvent."""
        state = self._fsm.to_dict()
        self._send(CompanionEvent(
            type=event_type or state["frontend_mood"],
            uid=self._uid,
            emotion=state["emotion"],
            eye_override=state["eye_override"],
            frontend_mood=state["frontend_mood"],
        ))

    async def _check_bubble_and_idle(self) -> None:
        now = time.time()
        gap = now - self._observer.last_active_at
        zzz_s = zzz_threshold_minutes(self._bones.quirk) * 60
        if gap > zzz_s:
            await self._observer.on_idle_return(self._uid, gap)
            self._fsm.mark_idle(gap)
            self._emit_state("sleeping")
        self._observer.last_active_at = now

        period = get_period()
        if now - self._last_bubble_at < 30:
            return
        bubble = await self._guide.decide_bubble(self._uid)
        if bubble:
            self._last_bubble_at = now
            self._send(CompanionBubbleEvent(self._uid, bubble))


# ---- breed-specific error comfort ------------------------------------------

_ERROR_COMFORT: dict[str, str] = {
    "orange_tabby": "出错了喵...别急，先趴会儿再试？",
    "tuxedo": "啊啊啊报错了!!! 没事没事再试一次!!!",
    "calico": "...哼。这不是我的问题。不过...再试一次？",
    "siamese": "这个报错我记得！上周也出现过，当时改了三行就好了喵！",
    "black_cat": "...错误是代码在和你说话。听它说了什么。",
    "ragdoll": "没关系的呢...慢慢来，我陪你~",
    "scottish_fold": "那个...出错了呢...但是别放弃喵...",
}


def _error_comfort(breed: str) -> str:
    return _ERROR_COMFORT.get(breed, "刚才好像出错了...")
