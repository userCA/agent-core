"""Load project context files (AGENTS.md, CLAUDE.md) from cwd and ancestors."""

from __future__ import annotations

import os
from pathlib import Path

from agent_core.resources.types import ContextFile

DEFAULT_FILENAMES = ["AGENTS.md", "CLAUDE.md"]


def load_project_context_files(
    cwd: str,
    *,
    filenames: list[str] | None = None,
    max_depth: int = 20,
) -> list[ContextFile]:
    """Walk from cwd up to ancestors collecting context files.

    Nearest files come first. Stops at .git directory boundary.
    """
    filenames = filenames or DEFAULT_FILENAMES
    results: list[ContextFile] = []
    current = Path(cwd).resolve()
    depth = 0

    while current and depth < max_depth:
        for name in filenames:
            file_path = current / name
            if file_path.is_file():
                try:
                    content = file_path.read_text(encoding="utf-8")
                    results.append(
                        ContextFile(
                            path=str(file_path),
                            content=content,
                            source="ancestor" if depth > 0 else "cwd",
                        )
                    )
                except Exception:
                    pass

        # Stop at git boundary
        if (current / ".git").is_dir():
            break

        parent = current.parent
        if parent == current:
            break
        current = parent
        depth += 1

    return results
