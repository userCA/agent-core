"""Prompt template discovery and loading."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.types import PromptTemplate, SourceInfo


def load_prompt_from_file(file_path: str, diagnostics: ResourceDiagnostics) -> PromptTemplate | None:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()
    except Exception as exc:
        diagnostics.warning(str(exc), source_path=file_path)
        return None

    if not raw_content.startswith("---"):
        diagnostics.warning("Missing YAML frontmatter", source_path=file_path)
        return None

    parts = raw_content.split("---", 2)
    if len(parts) < 3:
        diagnostics.warning("Invalid frontmatter format", source_path=file_path)
        return None

    try:
        frontmatter = yaml.safe_load(parts[1].strip()) or {}
    except yaml.YAMLError as exc:
        diagnostics.warning(f"Invalid YAML: {exc}", source_path=file_path)
        return None

    name = frontmatter.get("name")
    if not name:
        diagnostics.warning("Missing 'name' in frontmatter", source_path=file_path)
        return None

    return PromptTemplate(
        name=name,
        description=frontmatter.get("description", ""),
        template=parts[2].strip(),
        parameters=frontmatter.get("parameters", []),
        source=SourceInfo(
            source="project",
            scope="project",
            origin=file_path,
            base_dir=os.path.dirname(file_path),
        ),
    )
