"""Tests for legacy skill discovery, loading, and formatting.

These tests cover the deprecated ``agent_core.skills`` module.
The production skill system lives in ``agent_core.resources.skills``.
"""

from __future__ import annotations

import os
import tempfile
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from agent_core.skills import (
        Skill,
        format_skills_for_prompt,
        load_skill_from_file,
        load_skills,
        load_skills_from_dir,
    )


def test_load_skill_from_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = os.path.join(tmpdir, "test-skill")
        os.makedirs(skill_dir)
        path = os.path.join(skill_dir, "SKILL.md")
        with open(path, "w") as f:
            f.write("---\n")
            f.write("description: A test skill for unit testing\n")
            f.write("---\n\n")
            f.write("# Test Skill\n")

        skill, diagnostics = load_skill_from_file(path)
        assert skill is not None
        assert skill.description == "A test skill for unit testing"
        assert not skill.disable_model_invocation
        assert len(diagnostics) == 0


def test_load_skill_missing_description():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\n")
        f.write("name: no-desc\n")
        f.write("---\n\n")
        f.write("# No Description\n")
        f.flush()
        path = f.name

    try:
        skill, diagnostics = load_skill_from_file(path)
        assert skill is None
        assert any("description is required" in d["message"] for d in diagnostics)
    finally:
        os.unlink(path)


def test_load_skills_from_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a skill directory with SKILL.md
        skill_dir = os.path.join(tmpdir, "test-skill")
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write("---\n")
            f.write("description: A nested skill\n")
            f.write("---\n\n")
            f.write("# Nested Skill\n")

        result = load_skills_from_dir(tmpdir)
        assert len(result.skills) == 1
        assert result.skills[0].name == "test-skill"
        assert result.skills[0].description == "A nested skill"


def test_load_skills_collision():
    with tempfile.TemporaryDirectory() as tmpdir:
        d1 = os.path.join(tmpdir, "skill-a")
        d2 = os.path.join(tmpdir, "skill-a-copy")
        os.makedirs(d1)
        os.makedirs(d2)
        with open(os.path.join(d1, "SKILL.md"), "w") as f:
            f.write("---\nname: skill-a\ndescription: First skill\n---\n")
        with open(os.path.join(d2, "SKILL.md"), "w") as f:
            f.write("---\nname: skill-a\ndescription: Second skill\n---\n")

        result = load_skills(
            cwd=tmpdir,
            include_defaults=False,
            skill_paths=[d1, d2],
        )
        assert len(result.skills) == 1
        assert any("collision" in d["message"] for d in result.diagnostics)


def test_format_skills_for_prompt():
    skills = [
        Skill(
            name="python",
            description="Python coding skill",
            file_path="/skills/python/SKILL.md",
            base_dir="/skills/python",
        )
    ]
    prompt = format_skills_for_prompt(skills)
    assert "<available_skills>" in prompt
    assert "python" in prompt
    assert "Python coding skill" in prompt


def test_format_skills_disabled():
    skills = [
        Skill(
            name="hidden",
            description="Hidden skill",
            file_path="/skills/hidden/SKILL.md",
            base_dir="/skills/hidden",
            disable_model_invocation=True,
        )
    ]
    prompt = format_skills_for_prompt(skills)
    assert prompt == ""


def test_load_skills_with_paths():
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = os.path.join(tmpdir, "my-skill")
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write("---\n")
            f.write("description: My skill\n")
            f.write("---\n\n")
            f.write("# My Skill\n")

        result = load_skills(
            cwd=tmpdir,
            include_defaults=False,
            skill_paths=[os.path.join(skill_dir, "SKILL.md")],
        )
        assert len(result.skills) == 1
        assert result.skills[0].name == "my-skill"
