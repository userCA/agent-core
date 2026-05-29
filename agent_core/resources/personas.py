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
    knowledge_bases: list[str] | None = None


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
                    knowledge_bases=data.get("knowledge_bases"),
                )
            )

    return personas


def get_persona(persona_id: str, cwd: str = "") -> Persona | None:
    """Load a single persona by ID."""
    for p in load_personas(cwd):
        if p.id == persona_id:
            return p
    return None


def _personas_dir(cwd: str = "") -> str:
    return os.path.join(cwd or os.getcwd(), ".pi", "personas")


def save_persona(persona: Persona, cwd: str = "") -> None:
    """Save (create or update) a persona JSON file."""
    directory = _personas_dir(cwd)
    os.makedirs(directory, exist_ok=True)
    filepath = os.path.join(directory, f"{persona.id}.json")
    data: dict[str, Any] = {
        "id": persona.id,
        "name": persona.name,
        "description": persona.description,
        "system_prompt": persona.system_prompt,
    }
    if persona.enabled_tools is not None:
        data["enabled_tools"] = persona.enabled_tools
    if persona.knowledge_bases is not None:
        data["knowledge_bases"] = persona.knowledge_bases
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def delete_persona(persona_id: str, cwd: str = "") -> bool:
    """Delete a persona JSON file. Returns True if found."""
    directory = _personas_dir(cwd)
    filepath = os.path.join(directory, f"{persona_id}.json")
    try:
        os.unlink(filepath)
        return True
    except FileNotFoundError:
        return False
