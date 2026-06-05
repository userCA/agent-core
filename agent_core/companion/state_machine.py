"""Emotion state machine — 6-state FSM with transitions, decay, and stacking.

Input: agent events (TurnStart, ToolEnd, etc.)
Output: current emotion + eye override for sprite rendering
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

# ---- states ----------------------------------------------------------------


class Emotion:
    NEUTRAL = "NEUTRAL"
    HAPPY = "HAPPY"
    EXCITED = "EXCITED"
    SLEEPY = "SLEEPY"
    WORRIED = "WORRIED"
    ANNOYED = "ANNOYED"

    ALL = [NEUTRAL, HAPPY, EXCITED, SLEEPY, WORRIED, ANNOYED]


# ---- transition table ------------------------------------------------------
# (current_state, event_type) → target_state
# event_type: "pet" | "tool_ok" | "tool_fail" | "swear" | "idle_30s" | "idle_5min" | "fail_streak_3"

TRANSITIONS: dict[tuple[str, str], str] = {
    # NEUTRAL
    (Emotion.NEUTRAL, "pet"):           Emotion.HAPPY,
    (Emotion.NEUTRAL, "tool_ok"):       Emotion.NEUTRAL,
    (Emotion.NEUTRAL, "tool_fail"):     Emotion.WORRIED,
    (Emotion.NEUTRAL, "swear"):         Emotion.ANNOYED,
    (Emotion.NEUTRAL, "idle_30s"):      Emotion.SLEEPY,
    (Emotion.NEUTRAL, "idle_5min"):     Emotion.SLEEPY,
    (Emotion.NEUTRAL, "fail_streak_3"): Emotion.WORRIED,
    # HAPPY
    (Emotion.HAPPY, "pet"):             Emotion.EXCITED,
    (Emotion.HAPPY, "tool_ok"):         Emotion.HAPPY,
    (Emotion.HAPPY, "tool_fail"):       Emotion.NEUTRAL,
    (Emotion.HAPPY, "swear"):           Emotion.ANNOYED,
    (Emotion.HAPPY, "idle_30s"):        Emotion.NEUTRAL,
    (Emotion.HAPPY, "idle_5min"):       Emotion.SLEEPY,
    (Emotion.HAPPY, "fail_streak_3"):   Emotion.WORRIED,
    # EXCITED
    (Emotion.EXCITED, "pet"):           Emotion.EXCITED,
    (Emotion.EXCITED, "tool_ok"):       Emotion.HAPPY,
    (Emotion.EXCITED, "tool_fail"):     Emotion.NEUTRAL,
    (Emotion.EXCITED, "swear"):         Emotion.ANNOYED,
    (Emotion.EXCITED, "idle_30s"):      Emotion.HAPPY,
    (Emotion.EXCITED, "idle_5min"):     Emotion.SLEEPY,
    (Emotion.EXCITED, "fail_streak_3"): Emotion.NEUTRAL,
    # SLEEPY
    (Emotion.SLEEPY, "pet"):            Emotion.HAPPY,
    (Emotion.SLEEPY, "tool_ok"):        Emotion.NEUTRAL,
    (Emotion.SLEEPY, "tool_fail"):      Emotion.WORRIED,
    (Emotion.SLEEPY, "swear"):          Emotion.NEUTRAL,
    (Emotion.SLEEPY, "idle_30s"):       Emotion.SLEEPY,
    (Emotion.SLEEPY, "idle_5min"):      Emotion.SLEEPY,
    (Emotion.SLEEPY, "fail_streak_3"):  Emotion.WORRIED,
    # WORRIED
    (Emotion.WORRIED, "pet"):           Emotion.HAPPY,
    (Emotion.WORRIED, "tool_ok"):       Emotion.HAPPY,
    (Emotion.WORRIED, "tool_fail"):     Emotion.WORRIED,
    (Emotion.WORRIED, "swear"):         Emotion.ANNOYED,
    (Emotion.WORRIED, "idle_30s"):      Emotion.NEUTRAL,
    (Emotion.WORRIED, "idle_5min"):     Emotion.SLEEPY,
    (Emotion.WORRIED, "fail_streak_3"): Emotion.ANNOYED,
    # ANNOYED
    (Emotion.ANNOYED, "pet"):           Emotion.NEUTRAL,
    (Emotion.ANNOYED, "tool_ok"):       Emotion.NEUTRAL,
    (Emotion.ANNOYED, "tool_fail"):     Emotion.ANNOYED,
    (Emotion.ANNOYED, "swear"):         Emotion.ANNOYED,
    (Emotion.ANNOYED, "idle_30s"):      Emotion.NEUTRAL,
    (Emotion.ANNOYED, "idle_5min"):     Emotion.SLEEPY,
    (Emotion.ANNOYED, "fail_streak_3"): Emotion.ANNOYED,
}

# ---- decay to NEUTRAL ------------------------------------------------------

DECAY_SECONDS: dict[str, float] = {
    Emotion.EXCITED:  15,
    Emotion.HAPPY:    60,
    Emotion.WORRIED:  90,
    Emotion.ANNOYED:  45,
    Emotion.SLEEPY:   -1,  # never auto-decay — needs event to wake
}

# ---- eye override per emotion ----------------------------------------------

EMOTION_EYE: dict[str, str | None] = {
    Emotion.NEUTRAL:  None,   # use bones.eye
    Emotion.HAPPY:    "♥",
    Emotion.EXCITED:  "✦",
    Emotion.SLEEPY:   "-",
    Emotion.WORRIED:  "◉",
    Emotion.ANNOYED:  "▼",
}

# ---- emotion → frontend mood mapping ---------------------------------------

EMOTION_TO_MOOD: dict[str, str] = {
    Emotion.NEUTRAL:  "awake",
    Emotion.HAPPY:    "happy",
    Emotion.EXCITED:  "happy",
    Emotion.SLEEPY:   "sleeping",
    Emotion.WORRIED:  "concerned",
    Emotion.ANNOYED:  "concerned",
}

# ---- breed emotional params (from §12 breed profiles) ----------------------

BREED_EMOTION_PARAMS: dict[str, dict[str, float]] = {
    "orange_tabby":    {"annoy_resistance": 85, "excite_ease": 45, "worry_tendency": 25},
    "tuxedo":          {"annoy_resistance": 60, "excite_ease": 80, "worry_tendency": 20},
    "calico":          {"annoy_resistance": 40, "excite_ease": 55, "worry_tendency": 50},
    "siamese":         {"annoy_resistance": 55, "excite_ease": 70, "worry_tendency": 60},
    "black_cat":       {"annoy_resistance": 70, "excite_ease": 30, "worry_tendency": 40},
    "ragdoll":         {"annoy_resistance": 90, "excite_ease": 55, "worry_tendency": 70},
    "scottish_fold":   {"annoy_resistance": 80, "excite_ease": 35, "worry_tendency": 60},
}


# ---- EmotionFSM ------------------------------------------------------------


@dataclass
class EmotionState:
    emotion: str = Emotion.NEUTRAL
    mood: float = 50.0       # 0-100, 50=neutral
    last_event: str = ""
    last_event_at: float = 0
    streak: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    eye_override: str | None = None
    frontend_mood: str = "awake"


class EmotionFSM:
    """Per-companion emotion state machine.

    Call process(event_type) on each agent-event trigger, then read
    current state. Decay is checked via check_decay() which should be
    called periodically (e.g. per tick or per TurnEnd).
    """

    def __init__(self, breed: str = "orange_tabby"):
        self._state = EmotionState()
        self._breed = breed
        self._params = BREED_EMOTION_PARAMS.get(breed, BREED_EMOTION_PARAMS["orange_tabby"])

    # -- read ----------------------------------------------------------------

    @property
    def emotion(self) -> str:
        return self._state.emotion

    @property
    def mood(self) -> float:
        return self._state.mood

    @property
    def eye_override(self) -> str | None:
        return self._state.eye_override

    @property
    def frontend_mood(self) -> str:
        return self._state.frontend_mood

    @property
    def state(self) -> EmotionState:
        return self._state

    # -- event processing ----------------------------------------------------

    def process(self, event_type: str) -> list[str]:
        """Feed an event, return list of significant changes (for logging)."""
        changes: list[str] = []

        # update streak
        now = time.time()
        if self._state.last_event == event_type and now - self._state.last_event_at < 30:
            self._state.streak[event_type] += 1
        else:
            self._state.streak[event_type] = 1
        self._state.last_event = event_type
        self._state.last_event_at = now

        # check streak threshold
        effective_event = event_type
        if event_type == "tool_fail" and self._state.streak.get("tool_fail", 0) >= 3:
            effective_event = "fail_streak_3"

        # apply breed modifiers to transition probability
        target = self._apply_modifiers(effective_event)
        if target and target != self._state.emotion:
            old = self._state.emotion
            self._state.emotion = target
            self._apply_mood_change(effective_event)
            self._update_derived()
            changes.append(f"{old}→{target}")

        return changes

    def _apply_modifiers(self, event_type: str) -> str | None:
        """Apply breed-specific emotional modifiers to transition choice."""
        key = (self._state.emotion, event_type)
        target = TRANSITIONS.get(key)
        if target is None:
            return None

        # annoy_resistance: reduce chance of ANNOYED transitions
        if target == Emotion.ANNOYED:
            resist = self._params.get("annoy_resistance", 50) / 100
            import random
            if random.random() > (1.0 - resist * 0.5):
                return self._state.emotion  # resisted

        # excite_ease: NEUTRAL→HAPPY can skip to EXCITED
        if target == Emotion.HAPPY and self._state.emotion == Emotion.NEUTRAL:
            if self._params.get("excite_ease", 50) > 70:
                return Emotion.EXCITED

        # worry_tendency: NEUTRAL→WORRIED more likely
        if target == Emotion.WORRIED:
            worry = self._params.get("worry_tendency", 50) / 100
            import random
            if worry < 0.3 and random.random() < 0.5:
                return self._state.emotion  # too carefree to worry

        return target

    def _apply_mood_change(self, event_type: str) -> None:
        """Adjust mood value based on event."""
        deltas = {
            "pet": +20, "tool_ok": +5, "tool_fail": -10,
            "swear": -25, "fail_streak_3": -20,
            "idle_30s": 0, "idle_5min": 0,
        }
        delta = deltas.get(event_type, 0)
        self._state.mood = max(0, min(100, self._state.mood + delta))

    def _update_derived(self) -> None:
        """Sync eye_override and frontend_mood from current emotion."""
        self._state.eye_override = EMOTION_EYE.get(self._state.emotion)
        self._state.frontend_mood = EMOTION_TO_MOOD.get(self._state.emotion, "awake")

    # -- decay ---------------------------------------------------------------

    def check_decay(self, idle_seconds: float) -> list[str]:
        """Check and apply natural decay. Call per tick or per TurnEnd."""
        changes: list[str] = []

        if self._state.emotion in (Emotion.NEUTRAL, Emotion.SLEEPY):
            return changes

        decay_s = DECAY_SECONDS.get(self._state.emotion, -1)
        if decay_s <= 0:
            return changes

        if idle_seconds >= decay_s:
            old = self._state.emotion
            self._state.emotion = Emotion.NEUTRAL
            self._state.mood = 50
            self._update_derived()
            changes.append(f"{old}→NEUTRAL (decay)")

        return changes

    # -- idle -----------------------------------------------------------------

    def mark_idle(self, idle_seconds: float) -> list[str]:
        """Mark idle duration, trigger SLEEPY if needed."""
        changes: list[str] = []
        if idle_seconds >= 300 and self._state.emotion not in (Emotion.SLEEPY,):
            old = self._state.emotion
            self._state.emotion = Emotion.SLEEPY
            self._state.mood = max(0, self._state.mood - 20)
            self._update_derived()
            changes.append(f"{old}→SLEEPY (idle {idle_seconds:.0f}s)")
        return changes

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "emotion": self._state.emotion,
            "mood": self._state.mood,
            "eye_override": self._state.eye_override,
            "frontend_mood": self._state.frontend_mood,
        }
