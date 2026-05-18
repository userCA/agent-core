"""Resource types for discovery and loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ResourceDiagnostic:
    """Diagnostic emitted during resource loading."""
    type: Literal["warning", "error", "collision"]
    message: str
    source_path: str | None = None
    winner_path: str | None = None
    loser_path: str | None = None


@dataclass
class SourceInfo:
    """Source metadata for a loaded resource."""
    source: Literal["project", "user", "package", "explicit"]
    scope: Literal["global", "project", "session"]
    origin: str
    base_dir: str


@dataclass
class Skill:
    name: str
    description: str
    content: str
    source: SourceInfo
    disable_model_invocation: bool = False


@dataclass
class PromptTemplate:
    name: str
    description: str
    template: str
    parameters: list[str] = field(default_factory=list)
    source: SourceInfo | None = None


@dataclass
class Theme:
    name: str
    definition: dict[str, Any]
    source: SourceInfo | None = None


@dataclass
class ContextFile:
    path: str
    content: str
    source: Literal["cwd", "ancestor"]


@dataclass
class ExtensionSpec:
    name: str
    module_path: str
    source: SourceInfo
