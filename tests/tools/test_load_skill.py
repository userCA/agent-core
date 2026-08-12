"""Tests for LoadSkillTool."""

from __future__ import annotations

import pytest

from agent_core.resources.skill_activation import SkillActivationTracker
from agent_core.resources.types import Skill, SourceInfo
from agent_core.tools.load_skill import create_load_skill_tool


def _skill(
    name: str = "demo-skill",
    *,
    disable_model_invocation: bool = False,
    content: str = "---\nname: demo-skill\ndescription: Demo\n---\n\n# Body\n",
) -> Skill:
    return Skill(
        name=name,
        description="Demo skill",
        content=content,
        source=SourceInfo(
            source="project",
            scope="project",
            origin=f"/tmp/{name}/SKILL.md",
            base_dir=f"/tmp/{name}",
        ),
        disable_model_invocation=disable_model_invocation,
    )


@pytest.fixture
def tracker():
    return SkillActivationTracker()


@pytest.mark.asyncio
async def test_unknown_skill_returns_error(tracker):
    tool = create_load_skill_tool([_skill()], tracker)
    result = await tool.execute("tc1", {"name": "missing"}, None)
    assert result.details and result.details.get("error") == "unknown_skill"
    assert tracker.activated_names == []


@pytest.mark.asyncio
async def test_success_returns_skill_block_without_frontmatter(tracker):
    tool = create_load_skill_tool([_skill()], tracker)
    result = await tool.execute("tc1", {"name": "demo-skill"}, None)
    text = result.content[0].text
    assert '<skill name="demo-skill"' in text
    assert "# Body" in text
    assert "name: demo-skill" not in text
    assert tracker.activated_names == ["demo-skill"]


@pytest.mark.asyncio
async def test_disable_model_invocation_rejects_model_load(tracker):
    tool = create_load_skill_tool(
        [_skill(disable_model_invocation=True)],
        tracker,
    )
    result = await tool.execute("tc1", {"name": "demo-skill"}, None)
    assert result.details and result.details.get("error") == "model_invocation_disabled"
    assert tracker.activated_names == []


@pytest.mark.asyncio
async def test_repeat_load_is_idempotent_for_activation_hook(tracker):
    emitted: list[str] = []

    async def on_activate(skill: Skill, source: str) -> None:
        emitted.append(f"{skill.name}:{source}")

    tool = create_load_skill_tool([_skill()], tracker, on_activate=on_activate)
    await tool.execute("tc1", {"name": "demo-skill"}, None)
    await tool.execute("tc2", {"name": "demo-skill"}, None)
    assert emitted == ["demo-skill:load_skill"]
    assert tracker.activated_names == ["demo-skill"]
