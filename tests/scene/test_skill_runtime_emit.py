"""Tests that SkillRuntime emits SkillStart/End via harness, not bind_handlers."""

from __future__ import annotations

import pytest

from agent_core.core.state import AgentState
from agent_core.resources.types import Skill, SourceInfo
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore
from scene.skill_runtime import SkillRuntime


def _skill() -> Skill:
    return Skill(
        name="demo-skill",
        description="Demo",
        content="---\nname: demo\n---\n\nBody\n",
        source=SourceInfo(
            source="project",
            scope="project",
            origin="/tmp/demo-skill/SKILL.md",
            base_dir="/tmp/demo-skill",
        ),
    )


@pytest.mark.asyncio
async def test_emit_skill_start_does_not_call_bind_handlers_directly():
    harness = AgentHarness(
        provider=object(),
        auth_source=object(),
        store=InMemoryStore(),
        session_id="s1",
        initial_state=AgentState(system_prompt="", model=None, tools=[]),
    )
    direct: list[str] = []
    bus: list[str] = []
    rt = SkillRuntime([_skill()], harness, cwd="/tmp")
    rt.bind_handlers([lambda e: direct.append(getattr(e, "skill_name", ""))])
    harness.subscribe(lambda e: bus.append(getattr(e, "type", "")))
    await rt._emit_skill_start(_skill(), source="load_skill")
    assert direct == []
    assert "skill_start" in bus
    assert harness.skill_activations == [("demo-skill", "load_skill")]
