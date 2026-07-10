"""Skill discovery, loading, and formatting for system prompts.

.. deprecated::
    This module is superseded by :mod:`agent_core.resources.skills` and
    :mod:`agent_core.resources.types`, which provide a richer ``Skill`` type
    (including ``content`` and ``SourceInfo``).  All production code should
    use the ``resources`` package instead.
"""

from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "agent_core.skills is deprecated; use agent_core.resources.skills / "
    "agent_core.resources.types instead.",
    DeprecationWarning,
    stacklevel=2,
)

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Skill:
    name: str
    description: str
    file_path: str
    base_dir: str
    disable_model_invocation: bool = False


@dataclass
class LoadSkillsResult:
    skills: list[Skill]
    diagnostics: list[dict[str, Any]]


MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024


def _validate_name(name: str, parent_dir_name: str) -> list[str]:
    errors: list[str] = []
    if name != parent_dir_name:
        errors.append(f'name "{name}" does not match parent directory "{parent_dir_name}"')
    if len(name) > MAX_NAME_LENGTH:
        errors.append(f"name exceeds {MAX_NAME_LENGTH} characters ({len(name)})")
    if not re.match(r"^[a-z0-9-]+$", name):
        errors.append("name contains invalid characters (must be lowercase a-z, 0-9, hyphens only)")
    if name.startswith("-") or name.endswith("-"):
        errors.append("name must not start or end with a hyphen")
    if "--" in name:
        errors.append("name must not contain consecutive hyphens")
    return errors


def _validate_description(description: str | None) -> list[str]:
    errors: list[str] = []
    if not description or description.strip() == "":
        errors.append("description is required")
    elif len(description) > MAX_DESCRIPTION_LENGTH:
        errors.append(f"description exceeds {MAX_DESCRIPTION_LENGTH} characters ({len(description)})")
    return errors


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML-like frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    raw = parts[1].strip()
    body = parts[2].strip()
    frontmatter: dict[str, Any] = {}
    for line in raw.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value.lower() == "true":
                frontmatter[key] = True
            elif value.lower() == "false":
                frontmatter[key] = False
            else:
                frontmatter[key] = value
    return frontmatter, body


def load_skill_from_file(file_path: str) -> tuple[Skill | None, list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()
    except Exception as exc:
        diagnostics.append({"type": "warning", "message": str(exc), "path": file_path})
        return None, diagnostics

    frontmatter, _ = _parse_frontmatter(raw_content)
    skill_dir = os.path.dirname(file_path)
    parent_dir_name = os.path.basename(skill_dir)

    desc_errors = _validate_description(frontmatter.get("description"))
    for error in desc_errors:
        diagnostics.append({"type": "warning", "message": error, "path": file_path})

    name = frontmatter.get("name") or parent_dir_name
    name_errors = _validate_name(name, parent_dir_name)
    for error in name_errors:
        diagnostics.append({"type": "warning", "message": error, "path": file_path})

    if not frontmatter.get("description") or str(frontmatter.get("description", "")).strip() == "":
        return None, diagnostics

    return (
        Skill(
            name=name,
            description=frontmatter["description"],
            file_path=file_path,
            base_dir=skill_dir,
            disable_model_invocation=frontmatter.get("disable-model-invocation") is True,
        ),
        diagnostics,
    )


def load_skills_from_dir(dir: str) -> LoadSkillsResult:  # noqa: A002
    skills: list[Skill] = []
    diagnostics: list[dict[str, Any]] = []

    path = Path(dir)
    if not path.exists():
        return LoadSkillsResult(skills=skills, diagnostics=diagnostics)

    # If directory contains SKILL.md, treat it as a skill root and do not recurse further
    skill_md = path / "SKILL.md"
    if skill_md.is_file():
        skill, diag = load_skill_from_file(str(skill_md))
        diagnostics.extend(diag)
        if skill:
            skills.append(skill)
        return LoadSkillsResult(skills=skills, diagnostics=diagnostics)

    # Otherwise, load direct .md children and recurse into subdirectories
    for entry in sorted(path.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.name == "node_modules":
            continue
        if entry.is_dir():
            sub = load_skills_from_dir(str(entry))
            skills.extend(sub.skills)
            diagnostics.extend(sub.diagnostics)
        elif entry.is_file() and entry.suffix == ".md":
            skill, diag = load_skill_from_file(str(entry))
            diagnostics.extend(diag)
            if skill:
                skills.append(skill)

    return LoadSkillsResult(skills=skills, diagnostics=diagnostics)


def load_skills(
    *,
    cwd: str | None = None,
    agent_dir: str | None = None,
    skill_paths: list[str] | None = None,
    include_defaults: bool = True,
) -> LoadSkillsResult:
    cwd = cwd or os.getcwd()
    agent_dir = agent_dir or os.path.expanduser("~/.pi/agent")
    skill_paths = skill_paths or []

    skill_map: dict[str, Skill] = {}
    all_diagnostics: list[dict[str, Any]] = []

    def add_skills(result: LoadSkillsResult) -> None:
        nonlocal all_diagnostics
        all_diagnostics.extend(result.diagnostics)
        for skill in result.skills:
            existing = skill_map.get(skill.name)
            if existing:
                all_diagnostics.append(
                    {
                        "type": "collision",
                        "message": f'name "{skill.name}" collision',
                        "path": skill.file_path,
                        "collision": {
                            "resource_type": "skill",
                            "name": skill.name,
                            "winner_path": existing.file_path,
                            "loser_path": skill.file_path,
                        },
                    }
                )
            else:
                skill_map[skill.name] = skill

    if include_defaults:
        user_skills_dir = os.path.join(agent_dir, "skills")
        project_skills_dir = os.path.join(cwd, ".pi", "skills")
        add_skills(load_skills_from_dir(user_skills_dir))
        add_skills(load_skills_from_dir(project_skills_dir))

    for raw_path in skill_paths:
        resolved = os.path.expanduser(raw_path)
        if not os.path.isabs(resolved):
            resolved = os.path.join(cwd, resolved)
        if not os.path.exists(resolved):
            all_diagnostics.append(
                {"type": "warning", "message": "skill path does not exist", "path": resolved}
            )
            continue
        if os.path.isdir(resolved):
            add_skills(load_skills_from_dir(resolved))
        elif os.path.isfile(resolved) and resolved.endswith(".md"):
            skill, diag = load_skill_from_file(resolved)
            all_diagnostics.extend(diag)
            if skill:
                add_skills(LoadSkillsResult(skills=[skill], diagnostics=[]))
        else:
            all_diagnostics.append(
                {"type": "warning", "message": "skill path is not a markdown file", "path": resolved}
            )

    return LoadSkillsResult(skills=list(skill_map.values()), diagnostics=all_diagnostics)


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def format_skills_for_prompt(skills: list[Skill]) -> str:
    visible = [s for s in skills if not s.disable_model_invocation]
    if not visible:
        return ""

    lines = [
        "\n\nThe following skills provide specialized instructions for specific tasks.",
        "Use the read tool to load a skill's file when the task matches its description.",
        "When a skill file references a relative path, resolve it against the skill directory "
        "(parent of SKILL.md / dirname of the path) and use that absolute path in tool commands.",
        "",
        "<available_skills>",
    ]
    for skill in visible:
        lines.append("  <skill>")
        lines.append(f"    <name>{_escape_xml(skill.name)}</name>")
        lines.append(f"    <description>{_escape_xml(skill.description)}</description>")
        lines.append(f"    <location>{_escape_xml(skill.file_path)}</location>")
        lines.append("  </skill>")
    lines.append("</available_skills>")

    return "\n".join(lines)
