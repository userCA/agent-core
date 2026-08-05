"""Agent definition loading from .pi/agents/*.json."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentTools:
    builtin: list[str] | None = None
    shared_mcp: list[str] = field(default_factory=list)
    private_mcp: list[str] = field(default_factory=list)


@dataclass
class AgentKnowledge:
    shared: list[str] = field(default_factory=list)
    private: list[str] = field(default_factory=list)
    shared_mcp_knowledge: list[str] = field(default_factory=list)
    private_mcp_knowledge: list[str] = field(default_factory=list)


@dataclass
class AgentDefinition:
    id: str
    name: str
    description: str
    system_prompt: str
    tools: AgentTools | None = None
    knowledge: AgentKnowledge | None = None


def _parse_tools(data: dict[str, Any] | None) -> AgentTools | None:
    if data is None:
        return None
    return AgentTools(
        builtin=data.get("builtin"),
        shared_mcp=data.get("shared_mcp") or [],
        private_mcp=data.get("private_mcp") or [],
    )


def _parse_knowledge(data: dict[str, Any] | None) -> AgentKnowledge | None:
    if data is None:
        return None
    return AgentKnowledge(
        shared=data.get("shared") or [],
        private=data.get("private") or [],
        shared_mcp_knowledge=data.get("shared_mcp_knowledge") or [],
        private_mcp_knowledge=data.get("private_mcp_knowledge") or [],
    )


def load_agents(cwd: str = "") -> list[AgentDefinition]:
    """Load agent definitions from .pi/agents/*.json and ~/.pi/agent/agents/*.json."""
    search_dirs: list[str] = []

    cwd = cwd or os.getcwd()
    local_dir = os.path.join(cwd, ".pi", "agents")
    if os.path.isdir(local_dir):
        search_dirs.append(local_dir)

    home_dir = os.path.expanduser("~/.pi/agent/agents")
    if os.path.isdir(home_dir):
        search_dirs.append(home_dir)

    agents: list[AgentDefinition] = []
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

            aid = data.get("id", "")
            if not aid or aid in seen_ids:
                continue
            seen_ids.add(aid)

            agents.append(
                AgentDefinition(
                    id=aid,
                    name=data.get("name", aid),
                    description=data.get("description", ""),
                    system_prompt=data.get("system_prompt", ""),
                    tools=_parse_tools(data.get("tools")),
                    knowledge=_parse_knowledge(data.get("knowledge")),
                )
            )

    return agents


def get_agent(agent_id: str, cwd: str = "") -> AgentDefinition | None:
    """Load a single agent definition by ID."""
    for a in load_agents(cwd):
        if a.id == agent_id:
            return a
    return None


def _agents_dir(cwd: str = "") -> str:
    return os.path.join(cwd or os.getcwd(), ".pi", "agents")


def _tools_data(tools: AgentTools) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if tools.builtin is not None:
        data["builtin"] = tools.builtin
    if tools.shared_mcp:
        data["shared_mcp"] = tools.shared_mcp
    if tools.private_mcp:
        data["private_mcp"] = tools.private_mcp
    return data


def _knowledge_data(knowledge: AgentKnowledge) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if knowledge.shared:
        data["shared"] = knowledge.shared
    if knowledge.private:
        data["private"] = knowledge.private
    if knowledge.shared_mcp_knowledge:
        data["shared_mcp_knowledge"] = knowledge.shared_mcp_knowledge
    if knowledge.private_mcp_knowledge:
        data["private_mcp_knowledge"] = knowledge.private_mcp_knowledge
    return data


def save_agent(agent: AgentDefinition, cwd: str = "") -> None:
    """Save (create or update) an agent definition JSON file."""
    directory = _agents_dir(cwd)
    os.makedirs(directory, exist_ok=True)
    filepath = os.path.join(directory, f"{agent.id}.json")
    data: dict[str, Any] = {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
    }
    if agent.tools is not None:
        data["tools"] = _tools_data(agent.tools)
    if agent.knowledge is not None:
        data["knowledge"] = _knowledge_data(agent.knowledge)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def delete_agent(agent_id: str, cwd: str = "") -> bool:
    """Delete an agent definition JSON file. Returns True if found."""
    directory = _agents_dir(cwd)
    filepath = os.path.join(directory, f"{agent_id}.json")
    try:
        os.unlink(filepath)
        return True
    except FileNotFoundError:
        return False
