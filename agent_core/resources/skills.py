"""Skill discovery and loading."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.types import Skill, SourceInfo

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


def load_skill_from_file(file_path: str, diagnostics: ResourceDiagnostics) -> Skill | None:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()
    except Exception as exc:
        diagnostics.warning(str(exc), source_path=file_path)
        return None

    frontmatter, body = _parse_frontmatter(raw_content)
    skill_dir = os.path.dirname(file_path)
    parent_dir_name = os.path.basename(skill_dir)

    desc_errors = _validate_description(frontmatter.get("description"))
    for error in desc_errors:
        diagnostics.warning(error, source_path=file_path)

    name = frontmatter.get("name") or parent_dir_name
    name_errors = _validate_name(name, parent_dir_name)
    for error in name_errors:
        diagnostics.warning(error, source_path=file_path)

    if not frontmatter.get("description") or str(frontmatter.get("description", "")).strip() == "":
        return None

    return Skill(
        name=name,
        description=frontmatter["description"],
        content=raw_content,
        source=SourceInfo(
            source="project",
            scope="project",
            origin=file_path,
            base_dir=skill_dir,
        ),
        disable_model_invocation=frontmatter.get("disable-model-invocation") is True,
    )
