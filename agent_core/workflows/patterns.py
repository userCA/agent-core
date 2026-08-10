"""Orchestration pattern helpers for Dynamic Workflows."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent_core.workflows.runtime import WorkflowContext


async def fanout_synthesize(
    ctx: WorkflowContext,
    items: list[Any],
    *,
    map_prompt: Callable[[Any, int], str],
    synthesize_prompt: Callable[[list[Any]], str],
    map_profile: str | None = None,
    synthesize_profile: str | None = None,
) -> Any:
    """Map items in parallel via sub-agents, then synthesize into one result."""

    async def _map(item: Any, index: int) -> Any:
        return await ctx.agent(map_prompt(item, index), profile=map_profile)

    mapped = await ctx.pipeline(items, _map)
    return await ctx.agent(
        synthesize_prompt(mapped),
        profile=synthesize_profile,
    )


async def adversarial_verify(
    ctx: WorkflowContext,
    draft: str,
    rubric: str,
    *,
    max_rounds: int = 2,
    author_profile: str | None = None,
    critic_profile: str | None = None,
) -> dict[str, Any]:
    """Author/critic loop until approved or max_rounds exhausted.

    Returns ``{final, rounds: [{draft, critique, revised}], converged}``.
    """

    rounds: list[dict[str, str]] = []
    current = draft
    converged = False

    for _ in range(max_rounds):
        critique = await ctx.agent(
            (
                "Review this draft against the rubric.\n\n"
                f"Rubric:\n{rubric}\n\n"
                f"Draft:\n{current}\n\n"
                "If the draft meets the rubric, respond with APPROVED only. "
                "Otherwise provide specific critique."
            ),
            profile=critic_profile,
        )

        if "APPROVED" in critique.upper():
            rounds.append({"draft": current, "critique": critique, "revised": current})
            converged = True
            break

        revised = await ctx.agent(
            (
                "Revise this draft based on the critique.\n\n"
                f"Draft:\n{current}\n\n"
                f"Critique:\n{critique}"
            ),
            profile=author_profile,
        )
        rounds.append({"draft": current, "critique": critique, "revised": revised})
        current = revised

    return {"final": current, "rounds": rounds, "converged": converged}


async def generate_and_filter(
    ctx: WorkflowContext,
    n: int,
    *,
    gen_prompt: Callable[[int], str],
    score_prompt: Callable[[str], str],
    top_k: int = 1,
) -> list[Any]:
    """Generate *n* candidates in parallel, score them, return top *k*."""

    async def _generate(index: int, _i: int) -> str:
        return await ctx.agent(gen_prompt(index))

    candidates: list[str] = await ctx.pipeline(list(range(n)), _generate)

    async def _score(candidate: str, _i: int) -> tuple[float, str]:
        raw = await ctx.agent(score_prompt(candidate))
        try:
            score = float(str(raw).strip())
        except ValueError:
            score = 0.0
        return score, candidate

    scored: list[tuple[float, str]] = await ctx.pipeline(candidates, _score)
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [candidate for _, candidate in scored[:top_k]]


async def tournament(
    ctx: WorkflowContext,
    candidates: list[str],
    *,
    compare_prompt: Callable[[str, str], str],
    profile: str | None = None,
) -> str:
    """Single-elimination bracket; compare_prompt picks the winner each round."""

    if not candidates:
        return ""
    current = list(candidates)
    while len(current) > 1:
        next_round: list[str] = []
        index = 0
        while index < len(current):
            if index + 1 >= len(current):
                next_round.append(current[index])
                break
            left, right = current[index], current[index + 1]
            verdict = await ctx.agent(compare_prompt(left, right), profile=profile)
            if right in verdict and left not in verdict:
                next_round.append(right)
            else:
                next_round.append(left)
            index += 2
        current = next_round
    return current[0]


async def classify_and_execute(
    ctx: WorkflowContext,
    text: str,
    routes: dict[str, Callable[[WorkflowContext, str], Awaitable[Any]]],
    *,
    classify_prompt: Callable[[str], str] | None = None,
) -> Any:
    """Classify *text* into a route key, then invoke the matching handler."""

    if not routes:
        raise ValueError("routes must not be empty")

    if classify_prompt is None:
        keys = ", ".join(routes.keys())

        def classify_prompt(t: str) -> str:
            return (
                f"Classify the following text into exactly one of: {keys}\n\n"
                f"Text:\n{t}\n\n"
                "Respond with the route key only."
            )

    raw_key = str(await ctx.agent(classify_prompt(text))).strip()
    route_key = raw_key
    if route_key not in routes:
        for key in routes:
            if key in raw_key:
                route_key = key
                break
        else:
            raise ValueError(f"Unknown route: {raw_key!r}")

    return await routes[route_key](ctx, text)


async def loop_until(
    ctx: WorkflowContext,
    step: Callable[[WorkflowContext, int], Awaitable[Any]],
    done: Callable[[Any], bool],
    *,
    max_iters: int = 10,
) -> Any:
    """Run *step* until *done* returns True or *max_iters* is reached."""

    result: Any = None
    for iteration in range(max_iters):
        result = await step(ctx, iteration)
        if done(result):
            return result
    return result
