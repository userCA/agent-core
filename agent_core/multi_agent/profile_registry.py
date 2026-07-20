"""Expert agent profile registry and system-prompt formatting."""

from __future__ import annotations

from agent_core.multi_agent.types import AgentProfile


class AgentProfileRegistry:
    def __init__(self) -> None:
        self._profiles: dict[str, AgentProfile] = {}

    def register(self, profile: AgentProfile) -> None:
        self._profiles[profile.name] = profile

    def unregister(self, name: str) -> None:
        self._profiles.pop(name, None)

    def resolve(self, name: str) -> AgentProfile | None:
        return self._profiles.get(name)

    def list(self) -> list[AgentProfile]:
        return list(self._profiles.values())

    def format_for_system_prompt(self) -> str:
        lines = ["<available_agents>"]
        for p in self._profiles.values():
            lines.append("  <agent>")
            lines.append(f"    <name>{p.name}</name>")
            lines.append(f"    <description>{p.description}</description>")
            lines.append("  </agent>")
        lines.append("</available_agents>")
        return "\n".join(lines)
