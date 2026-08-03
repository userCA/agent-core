"""Tests for skill evolution background scheduler."""

from __future__ import annotations

from pathlib import Path

import pytest

from scene.http_sse.evolution_scheduler import (
    EvolutionScheduler,
    EvolutionSchedulerConfig,
    create_evolution_scheduler,
    evolution_scheduler_enabled,
)


@pytest.mark.asyncio
async def test_discover_candidates_prioritizes_failures(tmp_path: Path, monkeypatch):
    skill_dir = tmp_path / "skills"
    (skill_dir / "skill-a").mkdir(parents=True)
    (skill_dir / "skill-b").mkdir(parents=True)

    async def fake_get_trace_count(self, skill_name=None, outcome=None):
        data = {
            ("skill-a", None): 30,
            ("skill-a", "success"): 28,
            ("skill-a", "failure"): 2,
            ("skill-b", None): 25,
            ("skill-b", "success"): 10,
            ("skill-b", "failure"): 15,
        }
        return data.get((skill_name, outcome), 0)

    monkeypatch.setattr(
        "agent_core.skill_evolution.store.JsonlSkillEvolutionStore.get_trace_count",
        fake_get_trace_count,
    )

    sched = EvolutionScheduler(
        EvolutionSchedulerConfig(
            skill_dir=str(skill_dir),
            min_traces=20,
            max_skills_per_run=2,
            failure_priority=True,
        )
    )
    candidates = await sched.discover_candidates()
    names = [name for name, _ in candidates]
    assert names == ["skill-b", "skill-a"]


@pytest.mark.asyncio
async def test_run_once_calls_analyze(monkeypatch, tmp_path: Path):
    skill_dir = tmp_path / "skills"
    (skill_dir / "demo").mkdir(parents=True)

    calls: list[str] = []

    async def fake_analyze(**kwargs):
        calls.append(kwargs["skill_name"])
        return {"status": "completed", "proposals": [{"proposal_id": "p1"}]}

    async def fake_get_trace_count(self, skill_name=None, outcome=None):
        if skill_name == "demo" and outcome is None:
            return 25
        if skill_name == "demo" and outcome == "success":
            return 20
        if skill_name == "demo" and outcome == "failure":
            return 5
        return 0

    monkeypatch.setattr(
        "agent_core.skill_evolution.store.JsonlSkillEvolutionStore.get_trace_count",
        fake_get_trace_count,
    )
    monkeypatch.setattr(
        "scene.http_sse.evolution_service.run_skill_evolution_analyze",
        fake_analyze,
    )
    monkeypatch.setattr(
        "scene.http_sse.evolution_scheduler.scheduler_log_path",
        lambda: tmp_path / "scheduler.jsonl",
    )

    sched = EvolutionScheduler(
        EvolutionSchedulerConfig(skill_dir=str(skill_dir), min_traces=20, max_skills_per_run=1)
    )
    summary = await sched.run_once()
    assert calls == ["demo"]
    assert summary["skills_checked"] == 1
    assert summary["results"][0]["proposals"] == 1


def test_create_scheduler_respects_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ENABLE_EVOLUTION_SCHEDULER", "0")
    assert create_evolution_scheduler(str(tmp_path)) is None

    monkeypatch.setenv("ENABLE_EVOLUTION_SCHEDULER", "1")
    monkeypatch.setenv("ENABLE_SKILL_EVOLUTION", "1")
    sched = create_evolution_scheduler(str(tmp_path))
    assert sched is not None
    assert evolution_scheduler_enabled()
