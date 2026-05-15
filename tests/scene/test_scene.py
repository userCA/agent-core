"""Tests for scene chat assistant."""

from __future__ import annotations

import asyncio
import os
import tempfile

from scene.cli.chat_assistant import ChatAssistant
from scene.cli.system_prompt import build_system_prompt


def test_build_system_prompt():
    prompt = build_system_prompt(cwd="/tmp", tool_names=["read", "bash"])
    assert "read" in prompt
    assert "bash" in prompt
    assert "/tmp" in prompt


def test_build_system_prompt_with_skills():
    from agent_core.skills import Skill

    skills = [
        Skill(
            name="python",
            description="Python skill",
            file_path="/skills/python/SKILL.md",
            base_dir="/skills/python",
        )
    ]
    prompt = build_system_prompt(cwd="/tmp", skills=skills)
    assert "python" in prompt
    assert "Python skill" in prompt


async def test_chat_assistant_expand_skill_command():
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = os.path.join(tmpdir, "my-skill")
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write("---\ndescription: My skill\n---\n\nSkill content here.\n")

        from agent_core.skills import load_skills

        skills_result = load_skills(
            cwd=tmpdir,
            include_defaults=False,
            skill_paths=[skill_dir],
        )

        assistant = ChatAssistant(
            agent=None,  # type: ignore[arg-type]
            skills=skills_result.skills,
            cwd=tmpdir,
        )

        expanded = assistant._expand_skill_command("/skill:my-skill hello")
        assert "Skill content here" in expanded
        assert "hello" in expanded


def test_chat_assistant_expand_unknown_skill():
    assistant = ChatAssistant(
        agent=None,  # type: ignore[arg-type]
        skills=[],
        cwd="/tmp",
    )
    text = assistant._expand_skill_command("/skill:unknown hello")
    assert text == "/skill:unknown hello"
