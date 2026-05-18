"""Unified resource loader for skills, prompts, themes, context files, and extensions."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agent_core.resources.context_files import load_project_context_files
from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.extensions import discover_extension_specs
from agent_core.resources.prompts import load_prompt_from_file
from agent_core.resources.skills import load_skill_from_file
from agent_core.resources.themes import load_theme_from_file
from agent_core.resources.types import (
    ContextFile,
    ExtensionSpec,
    PromptTemplate,
    ResourceDiagnostic,
    Skill,
    SourceInfo,
    Theme,
)


class ResourceLoader:
    """Discover and load skills, prompts, themes, context files, and extension specs."""

    def __init__(
        self,
        *,
        cwd: str | None = None,
        extra_skill_paths: list[str] | None = None,
        extra_prompt_paths: list[str] | None = None,
        extra_theme_paths: list[str] | None = None,
        ignore_patterns: list[str] | None = None,
    ) -> None:
        self._cwd = cwd or os.getcwd()
        self._extra_skill_paths = extra_skill_paths or []
        self._extra_prompt_paths = extra_prompt_paths or []
        self._extra_theme_paths = extra_theme_paths or []
        self._ignore_patterns = ignore_patterns or []

    # --- search paths ---

    def _search_paths(self, resource_type: str, extras: list[str]) -> list[Path]:
        paths: list[Path] = []
        for p in extras:
            paths.append(Path(os.path.expanduser(p)).resolve())
        paths.append(Path(self._cwd) / ".pi" / resource_type)
        agent_dir = Path.home() / ".pi" / "agent" / resource_type
        paths.append(agent_dir)
        env_var = os.environ.get(f"AGENT_CORE_{resource_type.upper()}_PATH")
        if env_var:
            for p in env_var.split(":"):
                paths.append(Path(os.path.expanduser(p)).resolve())
        return [p for p in paths if p.exists()]

    @property
    def skill_search_paths(self) -> list[Path]:
        return self._search_paths("skills", self._extra_skill_paths)

    @property
    def prompt_search_paths(self) -> list[Path]:
        return self._search_paths("prompts", self._extra_prompt_paths)

    @property
    def theme_search_paths(self) -> list[Path]:
        return self._search_paths("themes", self._extra_theme_paths)

    # --- load methods ---

    def load_skills(self) -> tuple[list[Skill], list[ResourceDiagnostic]]:
        diagnostics = ResourceDiagnostics()
        skills: dict[str, Skill] = {}
        seen_paths: set[str] = set()

        for search_path in self.skill_search_paths:
            for skill_md in search_path.rglob("SKILL.md"):
                resolved = str(skill_md.resolve())
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                skill = load_skill_from_file(str(skill_md), diagnostics)
                if skill is not None:
                    existing = skills.get(skill.name)
                    if existing:
                        diagnostics.collision(
                            f'Skill name "{skill.name}" collision',
                            winner_path=existing.source.origin,
                            loser_path=skill.source.origin,
                        )
                    else:
                        skills[skill.name] = skill

        return list(skills.values()), diagnostics.items

    def load_prompt_templates(self) -> tuple[list[PromptTemplate], list[ResourceDiagnostic]]:
        diagnostics = ResourceDiagnostics()
        prompts: dict[str, PromptTemplate] = {}

        for search_path in self.prompt_search_paths:
            for md_file in search_path.rglob("*.md"):
                pt = load_prompt_from_file(str(md_file), diagnostics)
                if pt is not None:
                    existing = prompts.get(pt.name)
                    if existing:
                        diagnostics.collision(
                            f'Prompt template "{pt.name}" collision',
                            winner_path=str(existing.source.origin) if existing.source else "",
                            loser_path=str(pt.source.origin) if pt.source else "",
                        )
                    else:
                        prompts[pt.name] = pt

        return list(prompts.values()), diagnostics.items

    def load_themes(self) -> tuple[list[Theme], list[ResourceDiagnostic]]:
        diagnostics = ResourceDiagnostics()
        themes: dict[str, Theme] = {}

        for search_path in self.theme_search_paths:
            for json_file in search_path.rglob("*.json"):
                theme = load_theme_from_file(str(json_file), diagnostics)
                if theme is not None:
                    existing = themes.get(theme.name)
                    if existing:
                        diagnostics.collision(
                            f'Theme "{theme.name}" collision',
                            winner_path=str(existing.source.origin) if existing.source else "",
                            loser_path=str(theme.source.origin) if theme.source else "",
                        )
                    else:
                        themes[theme.name] = theme

        return list(themes.values()), diagnostics.items

    def load_context_files(self) -> list[ContextFile]:
        return load_project_context_files(self._cwd)

    def load_extension_specs(self) -> tuple[list[ExtensionSpec], list[ResourceDiagnostic]]:
        diagnostics = ResourceDiagnostics()
        # Extension discovery from ~/.pi/agent/extensions and project .pi/extensions
        paths = self._search_paths("extensions", [])
        specs = discover_extension_specs([str(p) for p in paths], diagnostics)
        return specs, diagnostics.items
