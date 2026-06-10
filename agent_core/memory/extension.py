"""Extension that persists user messages and recalls relevant memory."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent_core.providers.llm_message_utils import inject_system_message_at_latest_user, latest_user_text
from agent_core.core.content import TextContent
from agent_core.core.events import MessageEnd, TurnEnd
from agent_core.memory.base import MemoryStore

logger = logging.getLogger(__name__)

_MAX_PENDING = 100


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
            if len(self._pending) > _MAX_PENDING:
                self._pending.pop(0)
        elif isinstance(evt, TurnEnd):
            session_id = self._session_id
            if not session_id or not self._pending:
                return
            for text in self._pending:
                try:
                    await self._store.remember(session_id=session_id, text=text)
                except Exception:
                    logger.warning("memory remember failed for session %s", session_id, exc_info=True)
            self._pending.clear()

    async def on_before_tool_call(self, ctx: Any, tool_call: Any) -> dict[str, Any] | None: return None
    async def on_after_tool_call(self, ctx: Any, tool_call: Any, result: Any, is_error: bool) -> dict[str, Any] | None: return None

    async def transform_context(self, llm_messages: list[dict[str, Any]], signal: asyncio.Event | None) -> list[dict[str, Any]]:
        session_id = self._session_id
        if not session_id:
            return llm_messages
        query_text = latest_user_text(llm_messages) or ""
        if not query_text:
            return llm_messages

        try:
            records = await self._store.recall(session_id=session_id, query=query_text, limit=self._top_k)
        except Exception:
            logger.warning("memory recall failed for session %s", session_id, exc_info=True)
            return llm_messages

        if signal is not None and signal.is_set():
            return llm_messages

        if not records:
            return llm_messages

        body_lines = ["Recalled memory for this session:"]
        for i, r in enumerate(records, 1):
            body_lines.append(f"[{i}] {r.text}")
        return inject_system_message_at_latest_user(llm_messages, "\n".join(body_lines))
