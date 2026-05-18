"""Tool rendering protocol for frontend display."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel

from agent_core.tools.base import ToolResult


class RenderedOutput(BaseModel):
    """Rendered output of a tool call or result for frontend consumption."""

    text: str
    display: dict[str, Any] | None = None
    mime_type: str = "text/plain"


class ToolRenderer(Protocol):
    """Optional rendering protocol for tools."""

    async def render_call(
        self, tool_call_id: str, name: str, arguments: dict[str, Any]
    ) -> str:
        """Render a short summary of the tool call (e.g. 'read /path/to/file')."""
        ...

    async def render_result(
        self,
        tool_call_id: str,
        name: str,
        result: ToolResult,
        is_error: bool,
    ) -> RenderedOutput:
        """Render the tool execution result."""
        ...
