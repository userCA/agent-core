"""Tests for scene chat assistant."""

from __future__ import annotations

import os
import tempfile

from agent_core.prompts.builder import SystemPromptBuilder
from agent_core.resources.skill_activation import SkillActivationTracker, expand_skill_command
from agent_core.resources.loader import ResourceLoader
from agent_core.resources.types import Skill, SourceInfo


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


def test_expand_skill_command():
    """Skill command expansion is now handled by skill_activation.expand_skill_command."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = os.path.join(tmpdir, "my-skill")
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write("---\ndescription: My skill\n---\n\nSkill content here.\n")

        loader = ResourceLoader(cwd=tmpdir, extra_skill_paths=[skill_dir])
        skills, _ = loader.load_skills()

        tracker = SkillActivationTracker()
        expanded, should_emit = expand_skill_command(
            "/skill:my-skill hello", skills, tracker
        )
        assert "Skill content here" in expanded
        assert "hello" in expanded
        assert should_emit is True
        assert "my-skill" in tracker.activated_names


def test_expand_unknown_skill():
    """Unknown skill commands pass through unchanged."""
    tracker = SkillActivationTracker()
    text, should_emit = expand_skill_command("/skill:unknown hello", [], tracker)
    assert text == "/skill:unknown hello"
    assert should_emit is False
    assert len(tracker.activated_names) == 0
