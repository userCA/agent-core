"""FeedingSystem — convert game rewards to companion reactions."""

from __future__ import annotations

from dataclasses import dataclass

from agent_core.companion.minigames.base import GameReward


@dataclass
class FeedingResult:
    reaction: str
    bubble: str
    bond_progress: float
    items: list[str]


class FeedingSystem:
    def feed(self, reward: GameReward) -> FeedingResult:
        exp_gain = reward.food_value * reward.bond_boost
        bond_progress = exp_gain * 0.5

        if reward.food_value >= 100:
            reaction = "im_so_full"
            bubble = "嗝... 太饱了喵... 但是超好吃！"
        elif reward.food_value >= 50:
            reaction = "yummy"
            bubble = "好吃！再来一条！"
        elif reward.food_value >= 10:
            reaction = "happy_eat"
            bubble = "啊~ 谢谢你！"
        else:
            reaction = "nibble"
            bubble = "虽然少但还是很开心~"

        items = reward.items or []
        if "金龙鱼" in items:
            bond_progress *= 2.0
            bubble = "!!!! 金色的鱼 !! 你是钓鱼天才吗 !!"
        if "美人鱼" in items:
            bond_progress = 999.0
            bubble = "..........美人鱼？! 你...你是认真的吗？"

        return FeedingResult(
            reaction=reaction,
            bubble=bubble,
            bond_progress=bond_progress,
            items=items,
        )
