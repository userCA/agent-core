"""Background scheduler for periodic skill evolution analyze (proposals only)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


def evolution_scheduler_enabled() -> bool:
    return os.environ.get("ENABLE_EVOLUTION_SCHEDULER", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def scheduler_interval_sec() -> int:
    raw = os.environ.get("EVOLUTION_SCHEDULER_INTERVAL_SEC", "3600").strip()
    try:
        return max(60, int(raw))
    except ValueError:
        return 3600


def scheduler_min_traces() -> int:
    raw = os.environ.get("EVOLUTION_SCHEDULER_MIN_TRACES", "20").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 20


def scheduler_max_skills_per_run() -> int:
    raw = os.environ.get("EVOLUTION_SCHEDULER_MAX_SKILLS_PER_RUN", "3").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 3


def scheduler_failure_priority() -> bool:
    return os.environ.get("EVOLUTION_SCHEDULER_FAILURE_PRIORITY", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def scheduler_log_path() -> Path:
    return Path(
        os.environ.get(
            "EVOLUTION_SCHEDULER_LOG",
            "~/.agent-core/skill-evolution-scheduler.jsonl",
        )
    ).expanduser()


@dataclass
class EvolutionSchedulerConfig:
    skill_dir: str
    interval_sec: int = 3600
    min_traces: int = 20
    max_skills_per_run: int = 3
    failure_priority: bool = True


class EvolutionScheduler:
    """Periodically analyze skills with enough traces; never auto-applies."""

    def __init__(self, config: EvolutionSchedulerConfig) -> None:
        self._config = config
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self.last_run_at: float | None = None
        self.last_run_summary: dict[str, Any] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def discover_candidates(self) -> list[tuple[str, dict[str, int]]]:
        from agent_core.skill_evolution.store import JsonlSkillEvolutionStore
        from scene.http_sse.evolution_pending import has_pending_proposals

        store = JsonlSkillEvolutionStore()
        skill_dir = Path(self._config.skill_dir)
        if not skill_dir.is_dir():
            return []

        candidates: list[tuple[str, dict[str, int]]] = []
        for name in sorted(os.listdir(skill_dir)):
            path = skill_dir / name
            if not path.is_dir():
                continue
            # Skip skills with pending proposals
            if has_pending_proposals(name):
                _log.info("Skipping skill=%s: has pending proposals", name)
                continue
            total = await store.get_trace_count(skill_name=name)
            if total < self._config.min_traces:
                continue
            success = await store.get_trace_count(skill_name=name, outcome="success")
            failure = await store.get_trace_count(skill_name=name, outcome="failure")
            candidates.append((name, {"total": total, "success": success, "failure": failure}))

        if self._config.failure_priority:
            candidates.sort(key=lambda item: (item[1]["failure"], item[1]["total"]), reverse=True)
        else:
            candidates.sort(key=lambda item: item[1]["total"], reverse=True)

        return candidates[: self._config.max_skills_per_run]

    async def run_once(self) -> dict[str, Any]:
        from scene.http_sse.evolution_service import run_skill_evolution_analyze

        candidates = await self.discover_candidates()
        results: list[dict[str, Any]] = []
        for skill_name, counts in candidates:
            try:
                outcome = await run_skill_evolution_analyze(
                    skill_dir=self._config.skill_dir,
                    skill_name=skill_name,
                    min_traces=self._config.min_traces,
                )
                results.append({
                    "skill_name": skill_name,
                    "trace_counts": counts,
                    "status": outcome.get("status"),
                    "proposals": len(outcome.get("proposals") or []),
                    "reason": outcome.get("reason"),
                })
            except Exception as exc:
                _log.exception("Scheduler analyze failed for skill=%s", skill_name)
                results.append({
                    "skill_name": skill_name,
                    "trace_counts": counts,
                    "status": "error",
                    "error": str(exc),
                })

        summary = {
            "timestamp": time.time(),
            "skills_checked": len(candidates),
            "results": results,
        }
        self.last_run_at = summary["timestamp"]
        self.last_run_summary = summary
        self._append_log(summary)
        _log.info(
            "Evolution scheduler tick: checked=%d proposals=%s",
            len(candidates),
            [r.get("proposals", 0) for r in results],
        )
        return summary

    def _append_log(self, summary: dict[str, Any]) -> None:
        path = scheduler_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(summary, ensure_ascii=False) + "\n")

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:
                _log.exception("Evolution scheduler tick failed")
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._config.interval_sec,
                )
                break
            except asyncio.TimeoutError:
                continue

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="evolution-scheduler")
        _log.info(
            "Evolution scheduler started interval=%ss min_traces=%d max_skills=%d",
            self._config.interval_sec,
            self._config.min_traces,
            self._config.max_skills_per_run,
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        _log.info("Evolution scheduler stopped")


def create_evolution_scheduler(skill_dir: str) -> EvolutionScheduler | None:
    if not evolution_scheduler_enabled():
        return None
    if os.environ.get("ENABLE_SKILL_EVOLUTION", "1").strip().lower() in ("0", "false", "no", "off"):
        return None
    return EvolutionScheduler(
        EvolutionSchedulerConfig(
            skill_dir=skill_dir,
            interval_sec=scheduler_interval_sec(),
            min_traces=scheduler_min_traces(),
            max_skills_per_run=scheduler_max_skills_per_run(),
            failure_priority=scheduler_failure_priority(),
        )
    )
