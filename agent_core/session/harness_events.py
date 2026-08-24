"""Event handling and compaction helpers for AgentHarness."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from agent_core.core.context import AgentContext
from agent_core.core.events import (
    AgentEnd,
    AgentEvent,
    CompactionEvent,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    Settled,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
)
from agent_core.core.messages import AssistantMessage
from agent_core.core.state import AgentHarnessPhase

if TYPE_CHECKING:
    from agent_core.session.harness import AgentHarness

logger = logging.getLogger(__name__)


class HarnessEventsMixin:
    """Mixin: emit-sink event handling and compaction side effects."""

    async def _handle_event(self: AgentHarness, evt: AgentEvent, context: AgentContext | None = None) -> None:
        if isinstance(evt, MessageStart):
            if isinstance(evt.message, AssistantMessage):
                self.state.streaming_message = evt.message
        elif isinstance(evt, MessageUpdate):
            self.state.streaming_message = evt.message
        elif isinstance(evt, MessageEnd):
            self.state.streaming_message = None
            self.state.messages.append(evt.message)
        elif isinstance(evt, TurnEnd):
            msg = evt.message
            if isinstance(msg, AssistantMessage) and msg.error_message:
                self.state.error_message = msg.error_message
            for tool_result in evt.tool_results:
                self.state.messages.append(tool_result)
        elif isinstance(evt, AgentEnd):
            self.state.streaming_message = None
            await self.flush_pending_writes()
            self.phase = AgentHarnessPhase.IDLE
            # Run threshold compaction BEFORE notifying AgentEnd,
            # so CompactionEvent reaches the SSE stream before it closes.
            if self._compactor is not None:
                await self._maybe_threshold_compact()

        if isinstance(evt, ToolExecutionStart):
            self._pending_tool_calls.add(evt.tool_call_id)
        elif isinstance(evt, ToolExecutionEnd):
            self._pending_tool_calls.discard(evt.tool_call_id)

        if isinstance(evt, MessageEnd):
            await self._persistence.persist_message(evt.message)
        elif isinstance(evt, ToolExecutionEnd):
            await self._persistence.persist_tool_result(evt)

        if self._ext_runner is not None:
            await self._ext_runner.on_event(evt)

        await self._notify_listeners(evt)
        if isinstance(evt, AgentEnd):
            await self._notify_listeners(Settled(next_turn_count=self._next_turn.item_count))

    def _make_overflow_compact_callback(self: AgentHarness) -> Any:
        async def _on_overflow_compact(messages: list[Any]) -> bool:
            try:
                compacted = await self._compactor.compact(
                    messages, reason="overflow", signal=None,
                )
                if compacted.summary and compacted.kept_count > 0:
                    await self._apply_compaction_result(compacted, messages)
                    await self._notify_listeners(CompactionEvent(
                        tokens_before=compacted.tokens_before,
                        tokens_after=compacted.tokens_after,
                        reason="overflow",
                    ))
                    return True
                return False
            except Exception as exc:
                logger.warning("Overflow compaction failed for session %s: %s", self._session_id, exc)
                return False
        return _on_overflow_compact

    async def _apply_compaction_result(
        self: AgentHarness, compacted: Any, messages: list[Any],
    ) -> None:
        await self._persistence.persist_compaction(compacted)
        from agent_core.core.messages import CustomMessage
        summary_msg = CustomMessage(
            custom_type="compaction_summary",
            content=compacted.summary,
            timestamp=time.time(),
        )
        kept = messages[-compacted.kept_count:]
        messages.clear()
        messages.append(summary_msg)
        messages.extend(kept)
        self.state.messages = list(messages)

    async def _maybe_threshold_compact(self: AgentHarness) -> None:
        if self._compactor is None:
            return
        try:
            model = getattr(self.state, "model", None)
            context_window = getattr(model, "context_window", 0) if model else 0
            messages = list(self.state.messages)
            from agent_core.compaction.strategies import total_tokens as _tt
            _current_tokens = _tt(messages)
            _compactor_threshold = getattr(self._compactor, '_threshold', 0.8)
            _threshold_tokens = int(context_window * _compactor_threshold) if context_window else 0
            logger.info(
                "[Compaction] Check: messages=%d tokens=%d threshold=%d (window=%d, ratio=%.2f) needs_compact=%s",
                len(messages), _current_tokens, _threshold_tokens, context_window, _compactor_threshold,
                _current_tokens >= _threshold_tokens if _threshold_tokens else False,
            )
            if not context_window or not self._compactor.should_compact(
                messages, context_window=context_window,
            ):
                return
            if self._phase != AgentHarnessPhase.IDLE:
                logger.info("[Compaction] Skipped: phase=%s (not IDLE)", self._phase)
                return
            logger.info("[Compaction] Executing threshold compaction...")
            self.phase = AgentHarnessPhase.COMPACTION
            try:
                compacted = await self._compactor.compact(
                    messages, reason="threshold", signal=None,
                )
                logger.info(
                    "[Compaction] Result: summary=%d chars kept=%d tokens %d->%d",
                    len(compacted.summary), compacted.kept_count,
                    compacted.tokens_before, compacted.tokens_after,
                )
                if compacted.summary and compacted.kept_count > 0:
                    await self._apply_compaction_result(compacted, messages)
                    await self._notify_listeners(CompactionEvent(
                        tokens_before=compacted.tokens_before,
                        tokens_after=compacted.tokens_after,
                        reason="threshold",
                    ))
                    logger.info("[Compaction] Applied successfully")
                else:
                    logger.info("[Compaction] Not applied: summary_empty=%s kept=%d",
                                not compacted.summary, compacted.kept_count)
            finally:
                self.phase = AgentHarnessPhase.IDLE
        except Exception as exc:
            logger.warning("Compaction failed for session %s: %s", self._session_id, exc)
