"""Companion system — deterministic pet generation and configuration."""

from agent_core.companion.bones import CompanionBones, roll_companion
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
    RARITY_COLORS,
    RARITY_STARS,
    RARITY_WEIGHTS,
    STAT_NAMES,
)

__all__ = [
    "CompanionBones",
    "roll_companion",
    "ACCENTS",
    "BREED_NAMES",
    "BREED_RARITY_GATE",
    "BREED_WEIGHTS",
    "BREEDS",
    "COLOR_PALETTES",
    "EARS",
    "EYES",
    "HATS",
    "QUIRK_BREED_BONUS",
    "QUIRKS",
    "RARITIES",
    "RARITY_COLORS",
    "RARITY_STARS",
    "RARITY_WEIGHTS",
    "STAT_NAMES",
]
