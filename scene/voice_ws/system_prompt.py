"""System prompt builder for the scene chat assistant."""

from __future__ import annotations

from agent_core.skills import Skill, format_skills_for_prompt


def build_system_prompt(
    *,
    cwd: str,
    skills: list[Skill] | None = None,
    custom_prompt: str | None = None,
    tool_names: list[str] | None = None,
) -> str:
    """Build a system prompt for the chat assistant.

    Includes skill descriptions, tool hints, and any custom prompt content.
    """
    lines: list[str] = []

    base = custom_prompt or (
        "You are a helpful assistant with access to tools. "
        "When you need to perform actions on the user's system, use the available tools. "
        "Always prefer using tools over guessing when file or system information is needed."
    )
    lines.append(base)

    if tool_names:
        lines.append("")
        lines.append("Available tools:")
        for name in sorted(tool_names):
            lines.append(f"  - {name}")

    if skills:
        skill_text = format_skills_for_prompt(skills)
        if skill_text:
            lines.append(skill_text)

    lines.append("")
    lines.append(f"Current working directory: {cwd}")

    return "\n".join(lines)
