"""Tests for scene chat assistant."""

from __future__ import annotations

import asyncio
import os
import tempfile

from agent_core.prompts.builder import SystemPromptBuilder
from agent_core.resources.loader import ResourceLoader
from agent_core.resources.types import Skill, SourceInfo
from scene.skill_runtime import SkillRuntime


def test_system_prompt_builder():
    prompt = SystemPromptBuilder().build(
        cwd="/tmp",
        active_tools=[],
        skills=[],
        context_files=[],
    )
    assert "/tmp" in prompt.text


def test_system_prompt_builder_with_skills():
    skills = [
        Skill(
            name="python",
            description="Python skill",
            content="---\ndescription: Python skill\n---\n\nContent",
            source=SourceInfo(
                source="project",
                scope="project",
                origin="/skills/python/SKILL.md",
                base_dir="/skills/python",
            ),
        )
    ]
    prompt = SystemPromptBuilder().build(
        cwd="/tmp",
        active_tools=[],
        skills=skills,
        context_files=[],
    )
    assert "python" in prompt.text
    assert "Python skill" in prompt.text


class _StubHarness:
    """SkillRuntime 依赖的最小 harness 替身(仅供测试)。"""

    def __init__(self) -> None:
        self.activations: list[tuple[str, str]] = []

    def add_before_tool_call_hook(self, hook: object) -> None:
        pass

    def record_skill_activation(self, name: str, source: str) -> None:
        self.activations.append((name, source))


async def test_skill_runtime_expand_skill_command():
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = os.path.join(tmpdir, "my-skill")
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write("---\ndescription: My skill\n---\n\nSkill content here.\n")

        loader = ResourceLoader(cwd=tmpdir, extra_skill_paths=[skill_dir])
        skills, _ = loader.load_skills()

        harness = _StubHarness()
        runtime = SkillRuntime(skills, harness, cwd=tmpdir)  # type: ignore[arg-type]

        expanded = await runtime.expand_user_message("/skill:my-skill hello")
        assert "Skill content here" in expanded
        assert "hello" in expanded
        assert harness.activations == [("my-skill", "injected")]


async def test_skill_runtime_expand_unknown_skill():
    runtime = SkillRuntime([], _StubHarness(), cwd="/tmp")  # type: ignore[arg-type]
    text = await runtime.expand_user_message("/skill:unknown hello")
    assert text == "/skill:unknown hello"
