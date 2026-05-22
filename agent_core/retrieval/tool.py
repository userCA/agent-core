"""Wrap a Retriever as an LLM-callable Tool."""

from __future__ import annotations

from typing import Any

from agent_core.core.content import TextContent
from agent_core.retrieval.base import Query, Retriever
from agent_core.tools.base import ToolContext, ToolDefinition, ToolResult


class RetrieverTool:
    def __init__(self, *, retriever: Retriever, name: str = "retrieve", description: str = "Retrieve relevant context for a query.") -> None:
        self._retriever = retriever
        self.definition = ToolDefinition(
            name=name,
            description=description,
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural-language query."},
                    "top_k": {"type": "integer", "description": "Maximum number of chunks to return.", "default": 5},
                    "filters": {"type": "object", "description": "Optional metadata equality filters.", "default": {}},
                },
                "required": ["query"],
            },
        )

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = Query(text=params["query"], top_k=params.get("top_k", 5), filters=params.get("filters", {}))
        chunks = await self._retriever.retrieve(query)
        if not chunks:
            return ToolResult(content=[TextContent(text="No matching results.")])
        lines: list[str] = []
        for i, c in enumerate(chunks, 1):
            tag = f" [{c.source}]" if c.source else ""
            lines.append(f"[{i}] (score={c.score:.3f}){tag}\n{c.text}")
        return ToolResult(content=[TextContent(text="\n\n".join(lines))])
