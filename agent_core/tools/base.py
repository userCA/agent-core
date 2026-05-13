"""Tool abstractions: Tool, ToolResult, ToolDefinition, ToolRegistry."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from pydantic import BaseModel

from agent_core.core.content import ImageContent, TextContent


class ToolResult(BaseModel):
    content: list[TextContent | ImageContent]
    details: Any | None = None


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    prompt_snippet: str | None = None
    prompt_guidelines: list[str] = []


@dataclass
class ToolContext:
    signal: asyncio.Event
    on_update: Callable[[ToolResult], None] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Tool(Protocol):
    definition: ToolDefinition

    async def execute(
        self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext
    ) -> ToolResult: ...


@dataclass
class ToolInfo:
    name: str
    description: str
    parameters: dict[str, Any]
    source: Any | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._sources: dict[str, Any] = {}

    def register(self, tool: Tool, *, source: Any | None = None) -> None:
        name = tool.definition.name
        self._tools[name] = tool
        self._sources[name] = source

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[ToolInfo]:
        return [
            ToolInfo(
                name=t.definition.name,
                description=t.definition.description,
                parameters=t.definition.parameters,
                source=self._sources.get(name),
            )
            for name, t in self._tools.items()
        ]

    def to_definitions(self) -> list[ToolDefinition]:
        return [t.definition for t in self._tools.values()]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __iter__(self):
        return iter(self._tools)
