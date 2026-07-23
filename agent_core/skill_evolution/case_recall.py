"""Inject top-k skill path cases into LLM context (P4)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from agent_core.providers.llm_message_utils import (
    inject_system_message_at_latest_user,
    latest_user_text,
)

from .cases import (
    format_cases_for_prompt,
    load_cases,
    select_top_k_cases,
)


class SkillCaseRecallExtension:
    """Optional extension: recall distilled path cases for the latest user query."""

    name = "skill_case_recall"

    def __init__(
        self,
        *,
        skill_dir: str | Path,
        skill_names: list[str] | None = None,
        top_k: int = 3,
        max_chars: int = 2000,
        enabled: bool = True,
    ) -> None:
        self.skill_dir = Path(skill_dir)
        self.skill_names = list(skill_names or [])
        self.top_k = top_k
        self.max_chars = max_chars
        self.enabled = enabled

    async def on_event(self, ctx: Any, evt: Any) -> None:
        return None

    async def on_before_tool_call(self, ctx: Any, tool_call: Any) -> dict[str, Any] | None:
        return None

    async def on_after_tool_call(
        self, ctx: Any, tool_call: Any, result: Any, is_error: bool
    ) -> dict[str, Any] | None:
        return None

    async def transform_context(
        self,
        llm_messages: list[dict[str, Any]],
        signal: asyncio.Event | None,
    ) -> list[dict[str, Any]]:
        if not self.enabled or not self.skill_names:
            return llm_messages
        query_text = latest_user_text(llm_messages)
        if not query_text:
            return llm_messages

        pool = []
        for name in self.skill_names:
            pool.extend(load_cases(self.skill_dir, name))
        selected = select_top_k_cases(query_text, pool, k=self.top_k)
        body = format_cases_for_prompt(selected, max_chars=self.max_chars)
        if not body:
            return llm_messages
        return inject_system_message_at_latest_user(llm_messages, body)
