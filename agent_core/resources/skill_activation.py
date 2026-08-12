"""Skill activation tracking and formatting for progressive disclosure."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from agent_core.resources.types import Skill


def skill_progressive_enabled() -> bool:
    return os.environ.get("AGENT_SKILL_PROGRESSIVE", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def skill_legacy_tool_map_enabled() -> bool:
    return os.environ.get("AGENT_SKILL_LEGACY_TOOL_MAP", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def strip_skill_frontmatter(content: str) -> str:
    body = content
    if body.startswith("---"):
        parts = body.split("---", 2)
        if len(parts) >= 3:
            body = parts[2].strip()
    return body


def format_skill_block(skill: Skill) -> str:
    body = strip_skill_frontmatter(skill.content)
    return (
        f'<skill name="{skill.name}" location="{skill.source.origin}">\n'
        f"References are relative to {skill.source.base_dir}.\n\n"
        f"{body}\n"
        f"</skill>"
    )


def find_skill(skills: list[Skill], name: str) -> Skill | None:
    return next((s for s in skills if s.name == name), None)


def expand_skill_command(
    text: str,
    skills: list[Skill],
    tracker: SkillActivationTracker,
    *,
    source: str = "injected",
) -> tuple[str, bool]:
    """Expand ``/skill:name`` and record activation.

    Returns ``(expanded_text, should_emit_skill_start)``.
    """
    if not text.startswith("/skill:"):
        return text, False

    space_idx = text.find(" ")
    skill_name = text[7:space_idx] if space_idx != -1 else text[7:]
    args = text[space_idx + 1 :].strip() if space_idx != -1 else ""

    skill = find_skill(skills, skill_name)
    if skill is None:
        return text, False

    skill_block = format_skill_block(skill)
    expanded = f"{skill_block}\n\n{args}" if args else skill_block
    should_emit = tracker.activate(skill.name, source=source)
    return expanded, should_emit


@dataclass
class SkillActivationTracker:
    """Tracks activated skills within a run/session."""

    _activated: set[str] = field(default_factory=set)
    _sources: dict[str, str] = field(default_factory=dict)

    def activate(self, name: str, *, source: str) -> bool:
        """Record activation. Returns True if this is the first activation."""
        first = name not in self._activated
        self._activated.add(name)
        self._sources[name] = source
        return first

    @property
    def activated_names(self) -> list[str]:
        return sorted(self._activated)

    def source_for(self, name: str) -> str:
        return self._sources.get(name, "")

    def sources_summary(self) -> str:
        return ",".join(f"{name}:{self._sources[name]}" for name in sorted(self._activated))

    def activation_records(self) -> list[tuple[str, str]]:
        return [(name, self._sources[name]) for name in sorted(self._activated)]

    def clear(self) -> None:
        self._activated.clear()
        self._sources.clear()
