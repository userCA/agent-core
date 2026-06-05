"""Companion species definitions — enums, weights, and visual traits."""

from __future__ import annotations

# -- rarity -----------------------------------------------------------

RARITY_WEIGHTS: dict[str, int] = {
    "common": 60,
    "uncommon": 25,
    "rare": 10,
    "epic": 4,
    "legendary": 1,
}

RARITY_COLORS: dict[str, str] = {
    "common": "#8e8e93",
    "uncommon": "#30d158",
    "rare": "#409cff",
    "epic": "#bf5af2",
    "legendary": "#ff9f0a",
}

RARITY_STARS: dict[str, str] = {
    "common": "*",
    "uncommon": "**",
    "rare": "***",
    "epic": "****",
    "legendary": "*****",
}

RARITIES: list[str] = list(RARITY_WEIGHTS)

# -- visual traits (append-only, never delete/reorder/insert) ----------

EYES: list[str] = ["·", "✦", "◉", "o", "♥", "☆"]
EARS: list[str] = ["cat", "rabbit", "mix"]
ACCENTS: list[str] = ["none", "bow", "scarf", "glasses", "crown", "bell"]
COLOR_PALETTES: list[str] = [
    "warm_gray", "cool_gray", "cream", "charcoal", "snow",
]

# -- stats (cosmetic, deterministically generated from uid) -------------

STAT_NAMES: list[str] = ["好奇", "耐心", "创造", "粘人", "幸运"]
