"""Inject pinned (system prompt) and insights (message tail)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent_core.extensions.base import ExtensionContext
from agent_core.working_memory.store import WorkingMemoryStore

logger = logging.getLogger(__name__)


class WorkingMemoryExtension:
    name = "working_memory"

    def __init__(self, store: WorkingMemoryStore) -> None:
        self._store = store

    @property
    def store(self) -> WorkingMemoryStore:
        return self._store

    async def on_event(self, ctx: ExtensionContext, evt: Any) -> None:
        return None

    async def on_before_agent_start(
        self, ctx: ExtensionContext, prompt: str, system_prompt: str
    ) -> dict[str, Any] | None:
        block = self._store.format_pinned_block()
        if not block:
            return None
        # Avoid duplicating if already appended this turn chain.
        if block in system_prompt:
            return None
        return {"system_prompt": f"{system_prompt.rstrip()}\n\n{block}"}

    async def on_before_tool_call(
        self, ctx: ExtensionContext, tool_call: Any
    ) -> dict[str, Any] | None:
        return None

    async def on_after_tool_call(
        self, ctx: ExtensionContext, tool_call: Any, result: Any, is_error: bool
    ) -> dict[str, Any] | None:
        return None

    async def transform_context(
        self, llm_messages: list[dict[str, Any]], signal: asyncio.Event | None
    ) -> list[dict[str, Any]]:
        block = self._store.format_insights_block()
        if not block:
            return llm_messages
        # Inject near latest user turn — never append bare role=system (Anthropic
        # converter would replace the whole system prompt).
        from agent_core.providers.llm_message_utils import inject_system_message_at_latest_user

        return inject_system_message_at_latest_user(llm_messages, block)
