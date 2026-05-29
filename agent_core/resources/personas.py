"""Persona (agent role) loading from .pi/personas/*.json."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class Persona:
    id: str
    name: str
    description: str
    system_prompt: str
    enabled_tools: list[str] | None = None


def load_personas(cwd: str = "") -> list[Persona]:
    """Load persona definitions from .pi/personas/*.json and ~/.pi/agent/personas/*.json."""
    search_dirs: list[str] = []

    cwd = cwd or os.getcwd()
    local_dir = os.path.join(cwd, ".pi", "personas")
    if os.path.isdir(local_dir):
        search_dirs.append(local_dir)

    home_dir = os.path.expanduser("~/.pi/agent/personas")
    if os.path.isdir(home_dir):
        search_dirs.append(home_dir)

    personas: list[Persona] = []
    seen_ids: set[str] = set()

    for directory in search_dirs:
        for filename in sorted(os.listdir(directory)):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(directory, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            pid = data.get("id", "")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)

            personas.append(
                Persona(
                    id=pid,
                    name=data.get("name", pid),
                    description=data.get("description", ""),
                    system_prompt=data.get("system_prompt", ""),
                    enabled_tools=data.get("enabled_tools"),
                )
            )

    return personas


def get_persona(persona_id: str, cwd: str = "") -> Persona | None:
    """Load a single persona by ID."""
    for p in load_personas(cwd):
        if p.id == persona_id:
            return p
    return None
