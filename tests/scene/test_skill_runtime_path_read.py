"""Tests for path-read skill activation hook."""

from __future__ import annotations

import pytest

from agent_core.resources.skill_activation import SkillActivationTracker
from agent_core.resources.types import Skill, SourceInfo
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.core.state import AgentState
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


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setenv("AGENT_SKILL_PATH_READ_ACTIVATION", "1")
    harness = AgentHarness(
        provider=object(),
        auth_source=object(),
        store=InMemoryStore(),
        session_id="s1",
        initial_state=AgentState(system_prompt="", model=None, tools=[]),
    )
    emitted: list[str] = []

    async def handler(evt):
        emitted.append(evt.skill_name)

    rt = SkillRuntime([_skill()], harness, cwd="/tmp")
    rt.bind_handlers([handler])
    return rt, emitted


@pytest.mark.asyncio
async def test_read_skill_md_activates_skill(runtime):
    rt, emitted = runtime
    tool_call = type("TC", (), {"name": "read", "id": "tc1"})()
    await rt.before_tool_call({"tool_call": tool_call, "input": {"path": "/tmp/demo-skill/SKILL.md"}})
    assert emitted == ["demo-skill"]
    assert rt.harness.skill_activations == [("demo-skill", "path_read")]


@pytest.mark.asyncio
async def test_read_unrelated_file_does_not_activate(runtime):
    rt, emitted = runtime
    tool_call = type("TC", (), {"name": "read", "id": "tc1"})()
    await rt.before_tool_call({"tool_call": tool_call, "input": {"path": "/tmp/readme.md"}})
    assert emitted == []
    assert rt.harness.skill_activations == []
