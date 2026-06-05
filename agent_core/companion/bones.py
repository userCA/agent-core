"""Deterministic companion generation from user id.

FNV-1a hash + mulberry32 PRNG — same algorithm as Claude Code buddy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from agent_core.companion.species import (
    ACCENTS,
    COLOR_PALETTES,
    EARS,
    EYES,
    RARITIES,
    RARITY_WEIGHTS,
    STAT_NAMES,
)

SALT = "mitu-2026-companion"


@dataclass
class CompanionBones:
    uid: str
    species: str = "mitu"
    rarity: str = "common"
    eye: str = "·"
    ear: str = "cat"
    accent: str = "none"
    shiny: bool = False
    color: str = "warm_gray"
    stats: dict[str, int] = field(default_factory=dict)


# ---- hash / PRNG ------------------------------------------------------


def _hash_uid(uid: str) -> int:
    h = 2166136261
    for ch in uid + SALT:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def _mulberry32(seed: int):
    a = seed & 0xFFFFFFFF

    def next_float() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = ((a ^ (a >> 15)) * (1 | a)) & 0xFFFFFFFF
        t = ((t + (t ^ (t >> 7)) * (61 | t)) ^ t) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return next_float


def _pick(rng: Callable[[], float], arr: list[str]) -> str:
    return arr[int(rng() * len(arr))]


# ---- rarity roll ------------------------------------------------------


def _roll_rarity(rng: Callable[[], float]) -> str:
    total = sum(RARITY_WEIGHTS.values())
    roll = rng() * total
    for rarity in RARITIES:
        roll -= RARITY_WEIGHTS[rarity]
        if roll < 0:
            return rarity
    return "common"


# ---- stats ------------------------------------------------------------


def _roll_stats(rng: Callable[[], float], rarity: str) -> dict[str, int]:
    rarity_floor = {"common": 5, "uncommon": 15, "rare": 25, "epic": 35, "legendary": 50}
    floor = rarity_floor.get(rarity, 5)
    stats: dict[str, int] = {}
    for name in STAT_NAMES:
        stats[name] = floor + int(rng() * 40)
    # one peak, one dump
    peak = int(rng() * len(STAT_NAMES))
    dump = int(rng() * len(STAT_NAMES))
    while dump == peak:
        dump = int(rng() * len(STAT_NAMES))
    peak_name = STAT_NAMES[peak]
    dump_name = STAT_NAMES[dump]
    stats[peak_name] = min(100, stats[peak_name] + 50 + int(rng() * 30))
    stats[dump_name] = max(1, stats[dump_name] - 15)
    return stats


# ---- public API -------------------------------------------------------


def roll_companion(uid: str) -> CompanionBones:
    rng = _mulberry32(_hash_uid(uid))
    rarity = _roll_rarity(rng)
    return CompanionBones(
        uid=uid,
        species="mitu",
        rarity=rarity,
        eye=_pick(rng, EYES),
        ear=_pick(rng, EARS),
        accent="none" if rarity == "common" else _pick(rng, ACCENTS),
        shiny=rng() < 0.01,
        color=_pick(rng, COLOR_PALETTES),
        stats=_roll_stats(rng, rarity),
    )
