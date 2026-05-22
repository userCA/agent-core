"""Extension that persists user messages and recalls relevant memory."""

from __future__ import annotations

import asyncio
from typing import Any

from agent_core._llm_message_utils import latest_user_index, latest_user_text
from agent_core.core.content import TextContent
from agent_core.core.events import MessageEnd, TurnEnd
from agent_core.memory.base import MemoryStore


class MemoryExtension:
    name = "memory"

    def __init__(self, *, store: MemoryStore, session_id: str | None = None, top_k: int = 5) -> None:
        self._store = store
        self._session_id = session_id
        self._top_k = top_k
        self._pending: list[str] = []

    async def on_event(self, ctx: Any, evt: Any) -> None:
        if isinstance(evt, MessageEnd):
            msg = evt.message
            if getattr(msg, "role", None) != "user":
                return
            text_parts = [c.text for c in getattr(msg, "content", []) if isinstance(c, TextContent)]
            if not text_parts:
                return
            self._pending.append("\n".join(text_parts))
        elif isinstance(evt, TurnEnd):
            session_id = self._session_id
            if not session_id:
                return
            for text in self._pending:
                await self._store.remember(session_id=session_id, text=text)
            self._pending.clear()

    async def on_before_tool_call(self, ctx: Any, tool_call: Any) -> dict[str, Any] | None: return None
    async def on_after_tool_call(self, ctx: Any, tool_call: Any, result: Any, is_error: bool) -> dict[str, Any] | None: return None

    async def transform_context(self, llm_messages: list[dict[str, Any]], signal: asyncio.Event | None) -> list[dict[str, Any]]:
        session_id = self._session_id
        if not session_id:
            return llm_messages
        query_text = latest_user_text(llm_messages) or ""
        records = await self._store.recall(session_id=session_id, query=query_text, limit=self._top_k)
        if not records:
            return llm_messages

        body_lines = ["Recalled memory for this session:"]
        for i, r in enumerate(records, 1):
            body_lines.append(f"[{i}] {r.text}")
        system_msg = {"role": "system", "content": "\n".join(body_lines)}
        insert_at = latest_user_index(llm_messages)
        return [*llm_messages[:insert_at], system_msg, *llm_messages[insert_at:]]
