"""working_memory tool — write pinned facts and rolling insights."""

from __future__ import annotations

from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import ToolContext, ToolDefinition, ToolResult
from agent_core.working_memory.store import WorkingMemoryStore


class WorkingMemoryTool:
    def __init__(
        self,
        *,
        store: WorkingMemoryStore,
        name: str = "working_memory",
    ) -> None:
        self._store = store
        self.definition = ToolDefinition(
            name=name,
            description=(
                "Write short durable notes for this session. "
                "action=write_pinned: replace the pinned fact block (always in system prompt). "
                "action=write_insight: append a rolling insight (newest first; older ones scroll out). "
                "action=clear_pinned: clear the pinned block."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["write_pinned", "write_insight", "clear_pinned"],
                    },
                    "content": {
                        "type": "string",
                        "description": "Text for write_pinned / write_insight",
                    },
                },
                "required": ["action"],
            },
            prompt_snippet=(
                "Use working_memory to pin durable constraints or record short insights "
                "so they survive later turns without re-stating them in every reply."
            ),
        )

    async def execute(
        self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext
    ) -> ToolResult:
        action = str(params.get("action") or "").strip()
        content = str(params.get("content") or "")
        if action == "write_pinned":
            if not content.strip():
                return self._error("write_pinned requires non-empty content")
            self._store.write_pinned(content)
            return ToolResult(
                content=[TextContent(text="pinned updated")],
                details={"working_memory": {"action": action, "pinned": self._store.pinned}},
            )
        if action == "write_insight":
            if not content.strip():
                return self._error("write_insight requires non-empty content")
            self._store.write_insight(content)
            return ToolResult(
                content=[TextContent(text=f"insight stored ({len(self._store.insights)} total)")],
                details={
                    "working_memory": {
                        "action": action,
                        "insights_count": len(self._store.insights),
                    }
                },
            )
        if action == "clear_pinned":
            self._store.clear_pinned()
            return ToolResult(
                content=[TextContent(text="pinned cleared")],
                details={"working_memory": {"action": action}},
            )
        return self._error(f"unknown action: {action}")

    def _error(self, message: str) -> ToolResult:
        return ToolResult(content=[TextContent(text=message)])
