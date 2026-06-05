"""Companion species definitions — breeds, rarity, stats, quirks, visual traits.

All lists are append-only: never delete, insert, or reorder existing entries.
"""

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

# -- breeds (append-only) ----------------------------------------------

BREED_WEIGHTS: dict[str, int] = {
    "orange_tabby": 30,
    "tuxedo": 20,
    "calico": 15,
    "siamese": 15,
    "black_cat": 10,
    "ragdoll": 8,
    "scottish_fold": 2,
}

BREED_NAMES: dict[str, str] = {
    "orange_tabby": "橘猫",
    "tuxedo": "奶牛猫",
    "calico": "三花猫",
    "siamese": "暹罗猫",
    "black_cat": "黑猫",
    "ragdoll": "布偶猫",
    "scottish_fold": "折耳猫",
}

BREED_RARITY_GATE: dict[str, str | None] = {
    "orange_tabby": None,
    "tuxedo": None,
    "calico": "uncommon",
    "siamese": None,
    "black_cat": None,
    "ragdoll": "rare",
    "scottish_fold": "epic",
}

BREEDS: list[str] = list(BREED_WEIGHTS)

# -- stats (5-axis personality, deterministically generated) -----------

STAT_NAMES: list[str] = ["CURIOSITY", "SOCIAL", "AFFECTION", "PLAYFUL", "LUCK"]

# -- quirks (append-only) ----------------------------------------------

QUIRKS: list[str] = [
    "night_owl",
    "picky_eater",
    "chatterbox",
    "shy",
    "collector",
    "hyperactive",
    "sleepyhead",
    "glass_heart",
    "foodie",
    "clean_freak",
    "tsundere_extreme",
    "philosopher",
    "comedian",
]

QUIRK_BREED_BONUS: dict[str, dict[str, float]] = {
    "night_owl":         {"black_cat": 2.0},
    "picky_eater":       {"siamese": 2.0},
    "chatterbox":        {"siamese": 3.0},
    "shy":               {"scottish_fold": 3.0, "black_cat": 2.0},
    "collector":         {},
    "hyperactive":       {"tuxedo": 2.0},
    "sleepyhead":        {"orange_tabby": 3.0},
    "glass_heart":       {"ragdoll": 2.0},
    "foodie":            {"orange_tabby": 4.0},
    "clean_freak":       {"calico": 2.0},
    "tsundere_extreme":  {"calico": 3.0},
    "philosopher":       {"black_cat": 3.0},
    "comedian":          {"tuxedo": 3.0},
}

# -- visual traits (append-only, never delete/reorder/insert) ----------

EYES: list[str] = ["·", "✦", "◉", "o", "♥", "☆"]
EARS: list[str] = ["cat", "rabbit", "mix"]
ACCENTS: list[str] = ["none", "bow", "scarf", "glasses", "crown", "bell"]
HATS: list[str] = [
    "none", "crown", "tophat", "propeller", "halo", "wizard", "beanie", "tinyduck",
]
COLOR_PALETTES: list[str] = [
    "warm_gray", "cool_gray", "cream", "charcoal", "snow",
]
