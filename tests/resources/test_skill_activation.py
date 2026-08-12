"""Tests for skill activation helpers."""

from agent_core.resources.skill_activation import (
    SkillActivationTracker,
    expand_skill_command,
    format_skill_block,
    strip_skill_frontmatter,
)
from agent_core.resources.types import Skill, SourceInfo


def _skill(name: str = "demo-skill", content: str = "---\nname: demo\n---\n\nBody\n") -> Skill:
    return Skill(
        name=name,
        description="Demo",
        content=content,
        source=SourceInfo(
            source="project",
            scope="project",
            origin=f"/tmp/{name}/SKILL.md",
            base_dir=f"/tmp/{name}",
        ),
    )


def test_strip_skill_frontmatter():
    assert strip_skill_frontmatter("---\na: b\n---\n\nHello") == "Hello"


def test_format_skill_block_excludes_frontmatter():
    block = format_skill_block(_skill())
    assert "Body" in block
    assert "name: demo" not in block


def test_expand_skill_command_records_activation():
    tracker = SkillActivationTracker()
    expanded, should_emit = expand_skill_command("/skill:demo-skill run this", [_skill()], tracker)
    assert should_emit is True
    assert '<skill name="demo-skill"' in expanded
    assert "run this" in expanded
    assert tracker.activated_names == ["demo-skill"]

    _, should_emit_again = expand_skill_command("/skill:demo-skill again", [_skill()], tracker)
    assert should_emit_again is False
