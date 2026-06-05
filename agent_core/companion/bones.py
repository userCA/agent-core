"""Deterministic companion generation from user id.

FNV-1a hash + mulberry32 PRNG — same algorithm as Claude Code buddy.

Roll order is append-only: new fields must be added AFTER existing rolls
to preserve the PRNG sequence for existing users.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from agent_core.companion.species import (
    ACCENTS,
    BREED_NAMES,
    BREED_RARITY_GATE,
    BREED_WEIGHTS,
    BREEDS,
    COLOR_PALETTES,
    EARS,
    EYES,
    HATS,
    QUIRK_BREED_BONUS,
    QUIRKS,
    RARITIES,
    RARITY_WEIGHTS,
    STAT_NAMES,
)

SALT = "mitu-2026-companion"


@dataclass
class CompanionBones:
    uid: str
    breed: str = "orange_tabby"
    rarity: str = "common"
    eye: str = "·"
    ear: str = "cat"
    accent: str = "none"
    hat: str = "none"
    quirk: str = "night_owl"
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


# ---- breed (appended after original rolls) ----------------------------


def _rarity_rank(rarity: str) -> int:
    return RARITIES.index(rarity)


def _roll_breed(rng: Callable[[], float], rarity: str) -> str:
    """Roll breed filtered by rarity gate, then weighted."""
    min_rank = {
        "common": 0, "uncommon": 1, "rare": 2, "epic": 3, "legendary": 4,
    }.get(rarity, 0)
    eligible = [
        b for b in BREEDS
        if _rarity_rank(BREED_RARITY_GATE.get(b) or "common") <= min_rank
    ]
    if not eligible:
        eligible = [b for b in BREEDS if BREED_RARITY_GATE.get(b) is None]
    total = sum(BREED_WEIGHTS.get(b, 10) for b in eligible)
    roll = rng() * total
    for b in eligible:
        roll -= BREED_WEIGHTS.get(b, 10)
        if roll < 0:
            return b
    return eligible[-1]


# ---- hat (appended after breed) ---------------------------------------


def _roll_hat(rng: Callable[[], float], rarity: str) -> str:
    thresholds = {"common": 0.0, "uncommon": 0.3, "rare": 0.6, "epic": 0.85, "legendary": 1.0}
    cutoff = int(len(HATS) * thresholds.get(rarity, 0.0))
    if cutoff <= 0:
        return "none"
    return _pick(rng, HATS[: max(1, cutoff)])


# ---- quirk (appended after hat) ---------------------------------------


def _roll_quirk(rng: Callable[[], float], breed: str) -> str:
    base_weight = 10
    weighted: list[str] = []
    for q in QUIRKS:
        bonus = QUIRK_BREED_BONUS.get(q, {}).get(breed, 1.0)
        count = int(base_weight * bonus)
        weighted.extend([q] * count)
    return _pick(rng, weighted)


# ---- public API -------------------------------------------------------


def roll_companion(uid: str) -> CompanionBones:
    rng = _mulberry32(_hash_uid(uid))
    rarity = _roll_rarity(rng)
    eye = _pick(rng, EYES)
    ear = _pick(rng, EARS)
    accent = "none" if rarity == "common" else _pick(rng, ACCENTS)
    shiny = rng() < 0.01 or rarity == "legendary"
    color = _pick(rng, COLOR_PALETTES)
    stats = _roll_stats(rng, rarity)
    # new fields appended after original roll sequence
    breed = _roll_breed(rng, rarity)
    hat = _roll_hat(rng, rarity)
    quirk = _roll_quirk(rng, breed)
    return CompanionBones(
        uid=uid,
        breed=breed,
        rarity=rarity,
        eye=eye,
        ear=ear,
        accent=accent,
        hat=hat,
        quirk=quirk,
        shiny=shiny,
        color=color,
        stats=stats,
    )
