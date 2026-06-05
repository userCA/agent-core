"""Companion system — deterministic pet generation and configuration."""

from agent_core.companion.bones import CompanionBones, roll_companion
from agent_core.companion.species import (
    ACCENTS,
    COLOR_PALETTES,
    EARS,
    EYES,
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
    "COLOR_PALETTES",
    "EARS",
    "EYES",
    "RARITIES",
    "RARITY_COLORS",
    "RARITY_STARS",
    "RARITY_WEIGHTS",
    "STAT_NAMES",
]
