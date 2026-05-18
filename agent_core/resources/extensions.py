"""ExtensionSpec discovery without dynamic import."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.types import ExtensionSpec, SourceInfo


def discover_extension_specs(
    search_paths: list[str],
    diagnostics: ResourceDiagnostics,
) -> list[ExtensionSpec]:
    """Discover extension specs from directories without importing them."""
    specs: list[ExtensionSpec] = []
    seen: set[str] = set()

    for search_path in search_paths:
        path = Path(search_path)
        if not path.exists():
            continue
        for entry in path.rglob("*.py"):
            resolved = str(entry.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            # Simple heuristic: look for extension.py or files containing Extension class
            if entry.name == "extension.py" or "extension" in entry.stem:
                specs.append(
                    ExtensionSpec(
                        name=entry.stem,
                        module_path=str(entry.parent) if (entry.parent / "__init__.py").exists() else str(entry)[:-3].replace(os.sep, "."),
                        source=SourceInfo(
                            source="project",
                            scope="project",
                            origin=str(entry),
                            base_dir=str(path),
                        ),
                    )
                )

    return specs
