"""Compactor Protocol and LLMSummaryCompactor implementation."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Awaitable, Callable, Protocol

from pydantic import BaseModel

from agent_core.compaction.cut_point import find_safe_cutoff
from agent_core.compaction.strategies import should_compact_threshold, total_tokens


class CompactionResult(BaseModel):
    summary: str
    first_kept_entry_id: str
    tokens_before: int
    tokens_after: int
    kept_count: int = 0


SummarizeFn = Callable[..., Awaitable[str]]


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
    """Default compactor: keep recent N messages, summarize older ones.

    Uses a safe cut-point so the kept window never starts on a ``tool_result``.
    *summarize_fn* may be ``async (messages)`` or ``async (messages, instructions=...)``.
    """

    def __init__(
        self,
        *,
        summarize_fn: SummarizeFn | None = None,
        threshold: float = 0.8,
        keep_recent: int = 10,
        min_keep: int = 6,
        min_delete: int = 2,
    ) -> None:
        self._summarize_fn = summarize_fn
        self._threshold = threshold
        self._keep_recent = keep_recent
        self._min_keep = min_keep
        self._min_delete = min_delete

    def should_compact(self, messages: list[Any], *, context_window: int) -> bool:
        return should_compact_threshold(
            messages, context_window=context_window, threshold=self._threshold
        )

    async def _call_summarize(
        self, messages: list[Any], instructions: str | None
    ) -> str:
        assert self._summarize_fn is not None
        fn = self._summarize_fn
        try:
            sig = inspect.signature(fn)
            if "instructions" in sig.parameters:
                return await fn(messages, instructions=instructions)
        except (TypeError, ValueError):
            pass
        return await fn(messages)

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
        cutoff = find_safe_cutoff(
            messages,
            self._keep_recent,
            min_keep=self._min_keep,
            min_delete=self._min_delete,
        )
        if cutoff is None:
            return CompactionResult(
                summary="",
                first_kept_entry_id="",
                tokens_before=tokens_before,
                tokens_after=tokens_before,
                kept_count=len(messages),
            )

        to_compact = messages[:cutoff]
        to_keep = messages[cutoff:]

        summary = ""
        if to_compact and self._summarize_fn is not None:
            if signal is not None and signal.is_set():
                summary = "[aborted]"
            else:
                summary = await self._call_summarize(to_compact, instructions)

        first_kept_id = getattr(to_keep[0], "id", "") if to_keep else ""
        tokens_after = total_tokens(to_keep) + len(summary) // 4

        return CompactionResult(
            summary=summary,
            first_kept_entry_id=first_kept_id,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            kept_count=len(to_keep),
        )


def create_default_compactor(
    *,
    threshold: float = 0.8,
    keep_recent: int = 10,
) -> LLMSummaryCompactor:
    """Compactor with deterministic structured handoff (no extra LLM call)."""
    from agent_core.compaction.summarize import structured_handoff_summary

    async def _summarize(messages: list[Any], instructions: str | None = None) -> str:
        return structured_handoff_summary(messages, instructions=instructions)

    return LLMSummaryCompactor(
        summarize_fn=_summarize,
        threshold=threshold,
        keep_recent=keep_recent,
    )
