"""Compactor Protocol and LLMSummaryCompactor implementation."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Protocol

from pydantic import BaseModel

from agent_core.compaction.strategies import should_compact_threshold, total_tokens


class CompactionResult(BaseModel):
    summary: str
    first_kept_entry_id: str
    tokens_before: int
    tokens_after: int


SummarizeFn = Callable[[list[Any]], Awaitable[str]]


class Compactor(Protocol):
    def should_compact(self, messages: list[Any], *, context_window: int) -> bool: ...

    async def compact(
        self,
        messages: list[Any],
        *,
        reason: str,
        instructions: str | None = None,
        signal: asyncio.Event | None = None,
    ) -> CompactionResult: ...


class LLMSummaryCompactor:
    """Default compactor: keep recent N messages, summarize older ones via LLM."""

    def __init__(
        self,
        *,
        summarize_fn: SummarizeFn | None = None,
        threshold: float = 0.8,
        keep_recent: int = 4,
    ) -> None:
        self._summarize_fn = summarize_fn
        self._threshold = threshold
        self._keep_recent = keep_recent

    def should_compact(self, messages: list[Any], *, context_window: int) -> bool:
        return should_compact_threshold(
            messages, context_window=context_window, threshold=self._threshold
        )

    async def compact(
        self,
        messages: list[Any],
        *,
        reason: str,
        instructions: str | None = None,
        signal: asyncio.Event | None = None,
    ) -> CompactionResult:
        if not messages:
            return CompactionResult(
                summary="",
                first_kept_entry_id="",
                tokens_before=0,
                tokens_after=0,
            )

        tokens_before = total_tokens(messages)
        cutoff = max(0, len(messages) - self._keep_recent)
        to_compact = messages[:cutoff]
        to_keep = messages[cutoff:]

        summary = ""
        if to_compact and self._summarize_fn is not None:
            if signal is not None and signal.is_set():
                summary = "[aborted]"
            else:
                summary = await self._summarize_fn(to_compact)

        first_kept_id = getattr(to_keep[0], "id", "") if to_keep else ""
        tokens_after = total_tokens(to_keep) + len(summary) // 4

        return CompactionResult(
            summary=summary,
            first_kept_entry_id=first_kept_id,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
        )
