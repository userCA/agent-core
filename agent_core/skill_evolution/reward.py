"""Hybrid reward for skill-path evolution (heuristic + judge + human)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .types import ExecutionOutcome, SkillEvolutionTrace

JudgeFn = Callable[[SkillEvolutionTrace], Awaitable[float | None] | float | None]


@dataclass
class RewardBreakdown:
    """Per-component reward and effective weights after renormalization."""

    r: float
    r_h: float | None
    r_j: float | None
    r_u: float | None
    weights: dict[str, float]


def heuristic_reward(trace: SkillEvolutionTrace) -> float:
    """Deterministic path reward in [0, 1]."""
    outcome = trace.execution_outcome
    if isinstance(outcome, str):
        try:
            outcome = ExecutionOutcome(outcome)
        except ValueError:
            outcome = ExecutionOutcome.SUCCESS

    if outcome == ExecutionOutcome.SUCCESS:
        score = 0.7
    elif outcome == ExecutionOutcome.PARTIAL:
        score = 0.4
    else:
        score = 0.1

    error_steps = sum(1 for s in (trace.steps or []) if s.is_error)
    score -= 0.1 * error_steps

    n_steps = len(trace.steps or [])
    if n_steps > 8:
        score -= 0.02 * (n_steps - 8)

    return max(0.0, min(1.0, score))


def human_reward(trace: SkillEvolutionTrace) -> float | None:
    """Map human_signal / user_feedback to [-1, 1], or None if absent."""
    signal = trace.human_signal
    if isinstance(signal, dict):
        vote = signal.get("vote") or signal.get("polarity")
        if vote in ("like", "up", "+1", "positive"):
            return 1.0
        if vote in ("dislike", "down", "-1", "negative"):
            return -1.0
        if "score" in signal and signal["score"] is not None:
            return max(-1.0, min(1.0, float(signal["score"])))

    fb = (trace.user_feedback or "").lower()
    if not fb:
        return None
    if "helpful" in fb or "good" in fb or "like" in fb:
        return 1.0
    if "unhelpful" in fb or "bad" in fb or "dislike" in fb:
        return -1.0
    return None


class HybridReward:
    """Combine heuristic, optional LLM judge, and human signals."""

    def __init__(
        self,
        w_h: float = 0.4,
        w_j: float = 0.4,
        w_u: float = 0.2,
        judge: JudgeFn | None = None,
    ):
        self.w_h = w_h
        self.w_j = w_j
        self.w_u = w_u
        self.judge = judge

    async def compute(self, trace: SkillEvolutionTrace, write_back: bool = True) -> RewardBreakdown:
        r_h = heuristic_reward(trace)
        r_j = await self._maybe_judge(trace)
        r_u = human_reward(trace)

        components: list[tuple[str, float, float]] = [("h", self.w_h, r_h)]
        if r_j is not None:
            components.append(("j", self.w_j, r_j))
        if r_u is not None:
            # Map [-1,1] human into [0,1] for blending with heuristic/judge defaults
            components.append(("u", self.w_u, (r_u + 1.0) / 2.0))

        total_w = sum(w for _, w, _ in components) or 1.0
        weights = {name: w / total_w for name, w, _ in components}
        r = sum(weights[name] * val for name, _, val in components)

        if write_back:
            trace.reward = r

        return RewardBreakdown(
            r=r,
            r_h=r_h,
            r_j=r_j,
            r_u=r_u,
            weights=weights,
        )

    async def _maybe_judge(self, trace: SkillEvolutionTrace) -> float | None:
        if self.judge is None:
            return None
        result = self.judge(trace)
        if isinstance(result, Awaitable):
            result = await result
        if result is None:
            return None
        return max(0.0, min(1.0, float(result)))
