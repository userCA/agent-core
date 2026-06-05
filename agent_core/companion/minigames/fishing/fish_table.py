"""Fish definitions — rarity tiers and appearance weights."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FishDef:
    name: str
    emoji: str
    rarity: str
    rarity_rank: int
    food_value: int
    appear_weight: int
    sprite: str


FISH_TABLE: list[FishDef] = [
    FishDef("小虾米", "🦐", "common", 0, 5, 40, "~ <><"),
    FishDef("鲫鱼", "🐟", "common", 0, 8, 30, "<><"),
    FishDef("小螃蟹", "🦀", "common", 0, 6, 20, "~ v.v ~"),
    FishDef("鲤鱼", "🐠", "uncommon", 1, 15, 40, "><>"),
    FishDef("鱿鱼", "🦑", "uncommon", 1, 18, 30, "~<O>~"),
    FishDef("金鱼", "🔶", "uncommon", 1, 12, 25, "~<><~"),
    FishDef("三文鱼", "🐡", "rare", 2, 30, 35, "><<<>"),
    FishDef("灯笼鱼", "🎃", "rare", 2, 35, 25, "~<O>~"),
    FishDef("电鳗", "⚡", "epic", 3, 60, 40, "~zzZ~"),
    FishDef("锦鲤", "🎏", "epic", 3, 50, 35, "><<<>>"),
    FishDef("金龙鱼", "🐉", "legendary", 4, 100, 50, "~<O>~"),
    FishDef("美人鱼", "🧜", "legendary", 4, 120, 30, "><O><"),
]


def roll_fish_table(rng, bonus: int = 0) -> list[FishDef]:
    """Generate a pond — companion rarity bonus shifts weights toward rarer fish."""
    pond: list[FishDef] = []
    for f in FISH_TABLE:
        weight = f.appear_weight + (bonus if f.rarity_rank > 0 else 0)
        for _ in range(weight):
            pond.append(f)
    return pond


def roll_fish(pond: list[FishDef], rng) -> FishDef:
    return pond[int(rng() * len(pond))]
