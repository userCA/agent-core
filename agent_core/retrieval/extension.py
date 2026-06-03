"""Extension that auto-injects retrieved context before each LLM call."""

from __future__ import annotations

import asyncio
from typing import Any

from agent_core.providers.llm_message_utils import inject_system_message_at_latest_user, latest_user_text
from agent_core.retrieval.base import Query, Retriever


class AutoRetrievalExtension:
    name = "auto_retrieval"

    def __init__(self, *, retriever: Retriever, top_k: int = 5) -> None:
        self._retriever = retriever
        self._top_k = top_k

    async def on_event(self, ctx: Any, evt: Any) -> None: ...
    async def on_before_tool_call(self, ctx: Any, tool_call: Any) -> dict[str, Any] | None: return None
    async def on_after_tool_call(self, ctx: Any, tool_call: Any, result: Any, is_error: bool) -> dict[str, Any] | None: return None

    async def transform_context(self, llm_messages: list[dict[str, Any]], signal: asyncio.Event | None) -> list[dict[str, Any]]:
        query_text = latest_user_text(llm_messages)
        if not query_text:
            return llm_messages

        chunks = await self._retriever.retrieve(Query(text=query_text, top_k=self._top_k))
        if not chunks:
            return llm_messages

        body_lines = ["Relevant context retrieved for the latest user query:"]
        for i, c in enumerate(chunks, 1):
            tag = f" [{c.source}]" if c.source else ""
            body_lines.append(f"[{i}]{tag} {c.text}")
        return inject_system_message_at_latest_user(llm_messages, "\n".join(body_lines))
