"""Theme discovery and loading."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.types import SourceInfo, Theme


def load_theme_from_file(file_path: str, diagnostics: ResourceDiagnostics) -> Theme | None:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        diagnostics.warning(f"Invalid JSON: {exc}", source_path=file_path)
        return None
    except Exception as exc:
        diagnostics.warning(str(exc), source_path=file_path)
        return None

    name = data.get("name")
    if not name:
        diagnostics.warning("Missing 'name' field", source_path=file_path)
        return None

    return Theme(
        name=name,
        definition=data,
        source=SourceInfo(
            source="project",
            scope="project",
            origin=file_path,
            base_dir=os.path.dirname(file_path),
        ),
    )
