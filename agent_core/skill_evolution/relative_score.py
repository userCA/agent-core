"""Group-relative advantage assignment (GRPO-style, no gradients)."""

from __future__ import annotations

from .reward import HybridReward, heuristic_reward
from .types import SkillEvolutionTrace


def assign_advantages(
    group: list[SkillEvolutionTrace],
    *,
    fill_missing_reward: bool = True,
    eps: float = 1e-8,
    normalize_by_std: bool = False,
) -> list[SkillEvolutionTrace]:
    """Set trace.advantage = reward - group_mean (optionally / std).

    Traces without reward are filled via heuristic_reward when fill_missing_reward.
    Returns the same list for chaining.
    """
    if not group:
        return group

    rewards: list[float] = []
    for t in group:
        if t.reward is None and fill_missing_reward:
            t.reward = heuristic_reward(t)
        if t.reward is None:
            rewards.append(0.0)
        else:
            rewards.append(float(t.reward))

    mean_r = sum(rewards) / len(rewards)
    if normalize_by_std and len(rewards) > 1:
        var = sum((r - mean_r) ** 2 for r in rewards) / len(rewards)
        std = var ** 0.5
    else:
        std = 0.0

    for t, r in zip(group, rewards):
        adv = r - mean_r
        if normalize_by_std:
            adv = adv / (std + eps)
        t.advantage = adv

    return group


async def score_group(
    group: list[SkillEvolutionTrace],
    rewarder: HybridReward | None = None,
    **advantage_kwargs,
) -> list[SkillEvolutionTrace]:
    """Compute hybrid rewards then advantages for a group."""
    rewarder = rewarder or HybridReward(judge=None)
    for t in group:
        await rewarder.compute(t, write_back=True)
    return assign_advantages(group, fill_missing_reward=False, **advantage_kwargs)
