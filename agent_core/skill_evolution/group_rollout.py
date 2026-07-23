"""Active G-sample group rollout for GRPO-style skill path exploration.

Library-only: the host supplies a per-index runner (prompt/harness call).
Does not train model weights; only tags traces with a shared group_id.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .collector import SkillTraceCollector
from .grouping import normalize_task_key

_log = logging.getLogger(__name__)

# runner(index, query) -> result
RolloutRunner = Callable[[int, str], Awaitable[Any]]


@dataclass
class GroupRolloutResult:
    group_id: str
    task_key: str
    g: int
    results: list[Any] = field(default_factory=list)
    errors: list[BaseException | None] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for e in self.errors if e is None)


def should_trigger_group_rollout(
    *,
    enabled: bool,
    consecutive_failures: int = 0,
    failure_threshold: int = 2,
    high_value_skill: bool = False,
) -> bool:
    """Decide whether to spend G online samples.

    Default policy: only when explicitly enabled AND (enough consecutive
    failures OR marked high-value skill).
    """
    if not enabled:
        return False
    if high_value_skill:
        return True
    return consecutive_failures >= failure_threshold


class GroupRollout:
    """Run the same query G times under one group_id for relative scoring."""

    def __init__(
        self,
        *,
        collector: SkillTraceCollector | None = None,
        g: int = 3,
        parallel: bool = True,
    ) -> None:
        if g < 2:
            raise ValueError("GroupRollout requires g >= 2")
        self.collector = collector
        self.g = g
        self.parallel = parallel

    async def run(
        self,
        query: str,
        runner: RolloutRunner,
        *,
        group_id: str | None = None,
    ) -> GroupRolloutResult:
        gid = group_id or str(uuid.uuid4())
        task_key = normalize_task_key(query)
        if self.collector is not None:
            self.collector.set_rollout_context(gid, task_key)

        results: list[Any] = []
        errors: list[BaseException | None] = []
        try:
            if self.parallel:
                raw = await asyncio.gather(
                    *[runner(i, query) for i in range(self.g)],
                    return_exceptions=True,
                )
                for item in raw:
                    if isinstance(item, BaseException):
                        results.append(None)
                        errors.append(item)
                    else:
                        results.append(item)
                        errors.append(None)
            else:
                for i in range(self.g):
                    try:
                        results.append(await runner(i, query))
                        errors.append(None)
                    except BaseException as exc:  # noqa: BLE001 — capture per-slot
                        results.append(None)
                        errors.append(exc)
        finally:
            if self.collector is not None:
                self.collector.clear_rollout_context()

        _log.info(
            "GroupRollout done group_id=%s g=%d ok=%d/%d",
            gid,
            self.g,
            sum(1 for e in errors if e is None),
            self.g,
        )
        return GroupRolloutResult(
            group_id=gid,
            task_key=task_key,
            g=self.g,
            results=results,
            errors=errors,
        )
