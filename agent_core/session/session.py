"""AgentHarness — composition layer: Agent + Store + hooks + queues + event handling.

AgentSession is a deprecated alias kept for backward compatibility.
"""

from __future__ import annotations

import inspect
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from agent_core.compaction.compactor import Compactor, CompactionResult
from agent_core.core.errors import AgentHarnessError
from agent_core.core.events import (
    AbortEvent, AgentEnd, AgentEvent, MessageEnd, MessageStart, MessageUpdate,
    ModelUpdate, QueueUpdate, Settled, ThinkingLevelUpdate, ToolExecutionEnd,
    ToolExecutionStart, ToolsUpdate, TurnEnd,
)
from agent_core.core.hooks import AgentHooks, ContextHookEvent
from agent_core.core.messages import deserialize_message
from agent_core.core.pending_writes import PendingSessionWrite
from agent_core.core.queue import PendingMessageQueue, QueueMode
from agent_core.core.state import AgentHarnessPhase
from agent_core.extensions.base import ExtensionContext, ExtensionRunner
from agent_core.session.store import (
    ActiveToolsChangeEntry,
    CompactionEntry,
    MessageEntry,
    ModelChangeEntry,
    SessionHeader,
    SessionStore,
    ThinkingLevelChangeEntry,
)

logger = logging.getLogger(__name__)

Listener = Callable[[AgentEvent], Awaitable[None] | None]
Unsubscribe = Callable[[], None]


def _resolve_tool_name(tool: Any, index: int = 0) -> str:
    name = getattr(tool, "name", None)
    if name:
        return str(name)
    definition = getattr(tool, "definition", None)
    if definition is not None:
        def_name = getattr(definition, "name", None)
        if def_name:
            return str(def_name)
    return str(index)


class AgentHarness:
    def __init__(
        self,
        *,
        agent: Any,
        store: SessionStore,
        session_id: str,
        compactor: Compactor | None = None,
        extensions: list[Any] | None = None,
    ) -> None:
        self._agent = agent
        self._store = store
        self._session_id = session_id
        self._compactor = compactor
        self._extensions = extensions or []
        self._listeners: list[Listener] = []
        self._started = False
        self._closed = False
        self._ext_runner: ExtensionRunner | None = None
        self._compact_callback: Any | None = None
        self.hooks = AgentHooks()
        self._phase = AgentHarnessPhase.IDLE
        self._pending_writes: list[PendingSessionWrite] = []
        self._steering = PendingMessageQueue("one-at-a-time")
        self._follow_up = PendingMessageQueue("one-at-a-time")

    @property
    def phase(self) -> AgentHarnessPhase:
        return self._phase

    @phase.setter
    def phase(self, value: AgentHarnessPhase) -> None:
        self._phase = value
        self._agent._phase = value
        self._agent.state.phase = value

    async def start(self) -> None:
        """Create session in store and subscribe to agent events."""
        if self._started or self._closed:
            return
        header = SessionHeader(
            id=self._session_id,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            cwd=os.getcwd(),
        )
        try:
            snapshot = await self._store.load_session(self._session_id)
            self._restore_messages(snapshot)
        except KeyError:
            await self._store.create_session(self._session_id, header)
        except Exception as exc:
            logger.warning("Failed to load session %s: %s", self._session_id, exc)

        # Inject harness reference so Agent delegates hooks/phase to Session
        self._agent._harness = self

        # Merge agent's pre-existing hooks (from constructor) into session hooks
        for event_type, handlers in self._agent._hooks._handlers.items():
            for handler in handlers:
                self.hooks.on(event_type, handler)
        for observer in self._agent._hooks._observers:
            self.hooks.observe(observer)

        # Note: no need to subscribe to agent events — the emit sink
        # routes directly to session._handle_event when harness is set.
        if self._extensions:
            ext_ctx = ExtensionContext(
                session_id=self._session_id,
                agent=self._agent,
                store=self._store,
            )
            self._ext_runner = ExtensionRunner(self._extensions, ext_ctx)

            # Register extension hooks via the harness hook system
            from agent_core.core.hooks import ToolCallHookEvent, ToolResultHookEvent

            async def _tool_call_adapter(event: ToolCallHookEvent) -> Any:
                return await self._ext_runner.before_tool_call(event.call_ctx)

            async def _tool_result_adapter(event: ToolResultHookEvent) -> Any:
                return await self._ext_runner.after_tool_call(event.call_ctx)

            self.hooks.on("tool_call", _tool_call_adapter)
            self.hooks.on("tool_result", _tool_result_adapter)

            # Register extension transform_context hooks
            for ext in self._extensions:
                transform = getattr(ext, "transform_context", None)
                if callable(transform):
                    self._register_context_transform(transform)

        # Wire compaction callback for overflow auto-retry
        if self._compactor is not None:
            async def _on_overflow_compact(messages: list[Any]) -> bool:
                try:
                    compacted = await self._compactor.compact(
                        messages, reason="overflow", signal=None
                    )
                    if compacted.summary and compacted.kept_count > 0:
                        entry = CompactionEntry(
                            summary=compacted.summary,
                            first_kept_entry_id=compacted.first_kept_entry_id,
                            tokens_before=compacted.tokens_before,
                            id=f"compaction-{int(time.time() * 1000)}",
                        )
                        await self._store.append_entry(self._session_id, entry)

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

                        self._agent.state.messages = list(messages)
                        return True
                    return False
                except Exception as exc:
                    logger.warning("Overflow compaction failed for session %s: %s", self._session_id, exc)
                    return False

            self._compact_callback = _on_overflow_compact

        self._started = True

    # ---------- external listeners ----------
    def subscribe(self, listener: Listener) -> Unsubscribe:
        self._listeners.append(listener)

        def _unsub() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return _unsub

    # ---------- proxy to agent ----------
    @property
    def messages(self) -> list[Any]:
        return list(self._agent.state.messages)

    async def prompt(self, text: str, **opts: Any) -> None:
        self._check_ready()
        await self._agent.prompt(text, compact_callback=self._compact_callback, **opts)

    async def continue_(self) -> None:
        self._check_ready()
        await self._agent.continue_(compact_callback=self._compact_callback)

    async def compact(self, *, instructions: str | None = None) -> None:
        """Manually trigger compaction.  Delegates to agent.compact() for phase management."""
        self._check_ready()
        if self._compactor is None:
            return

        # Inject a manual compaction callback that handles persistence
        async def _manual_compact(messages: list[Any]) -> bool:
            compacted = await self._compactor.compact(
                messages, reason="manual", instructions=instructions, signal=None
            )
            if compacted.summary and compacted.kept_count > 0:
                entry = CompactionEntry(
                    summary=compacted.summary,
                    first_kept_entry_id=compacted.first_kept_entry_id,
                    tokens_before=compacted.tokens_before,
                    id=f"compaction-{int(time.time() * 1000)}",
                )
                await self._store.append_entry(self._session_id, entry)

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
                self._agent.state.messages = list(messages)
                return True
            return False

        old_cb = self._agent._compact_callback
        self._agent._compact_callback = _manual_compact
        try:
            await self._agent.compact(instructions=instructions)
        finally:
            self._agent._compact_callback = old_cb

    def abort(self) -> None:
        self._agent.abort()

    async def abort_and_wait(self) -> dict[str, Any]:
        """Abort the current run and wait for idle."""
        cleared_steer = self._steering.drain()
        cleared_follow_up = self._follow_up.drain()
        self._agent.abort()
        await self._agent.wait_for_idle()
        await self._notify_listeners(AbortEvent(
            cleared_steer=list(cleared_steer),
            cleared_follow_up=list(cleared_follow_up),
        ))
        return {
            "cleared_steer": list(cleared_steer),
            "cleared_follow_up": list(cleared_follow_up),
        }

    async def wait_for_idle(self) -> None:
        await self._agent.wait_for_idle()

    def provide_human_input(self, tool_call_id: str, values: dict[str, Any]) -> bool:
        return self._agent.provide_human_input(tool_call_id, values)

    async def dispose(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._agent._harness = None
        await self._store.close()

    def _check_ready(self) -> None:
        if self._closed:
            raise AgentHarnessError("invalid_state", "AgentHarness is disposed")
        if not self._started:
            raise AgentHarnessError("invalid_state", "AgentHarness not started; call start() first")

    # ---------- context transform hook ----------
    def _register_context_transform(self, handler: Any) -> None:
        """Register a context transform handler on the harness hooks."""
        async def _adapter(event: ContextHookEvent) -> Any:
            result = handler(event.messages, None)
            if inspect.isawaitable(result):
                result = await result
            if result is not None and result is not event.messages:
                return {"messages": result}
            return None
        self.hooks.on("context", _adapter)

    # ---------- queues (harness owns) ----------
    def steer(self, message: Any) -> None:
        self._steering.enqueue(message)
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._emit_queue_update())
        except RuntimeError:
            pass

    def follow_up(self, message: Any) -> None:
        self._follow_up.enqueue(message)
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._emit_queue_update())
        except RuntimeError:
            pass

    def clear_all_queues(self) -> None:
        self._steering.clear()
        self._follow_up.clear()

    @property
    def steering_mode(self) -> QueueMode:
        return self._steering.mode

    @steering_mode.setter
    def steering_mode(self, mode: QueueMode) -> None:
        self._steering.mode = mode

    @property
    def followup_mode(self) -> QueueMode:
        return self._follow_up.mode

    @followup_mode.setter
    def followup_mode(self, mode: QueueMode) -> None:
        self._follow_up.mode = mode

    def has_queued_messages(self) -> bool:
        return self._steering.has_items() or self._follow_up.has_items()

    async def _emit_queue_update(self) -> None:
        await self._notify_listeners(QueueUpdate(
            steer_count=self._steering.item_count,
            follow_up_count=self._follow_up.item_count,
        ))

    async def _drain_steering(self) -> list[Any]:
        return self._steering.drain()

    async def _drain_follow_up(self) -> list[Any]:
        return self._follow_up.drain()

    # ---------- pending writes (harness owns) ----------
    def _pending_write_to_entry(self, write: PendingSessionWrite) -> Any:
        entry_id = f"{write.type}-{int(time.time() * 1000)}"
        if write.type == "model_change":
            return ModelChangeEntry(
                provider=write.data["provider"],
                model_id=write.data["model_id"],
                id=entry_id,
            )
        if write.type == "thinking_level_change":
            return ThinkingLevelChangeEntry(
                level=write.data["thinking_level"],
                id=entry_id,
            )
        if write.type == "active_tools_change":
            return ActiveToolsChangeEntry(
                active_tool_names=list(write.data["active_tool_names"]),
                id=entry_id,
            )
        raise ValueError(f"Unknown pending write type: {write.type}")

    async def _persist_pending_write(self, write: PendingSessionWrite) -> None:
        entry = self._pending_write_to_entry(write)
        try:
            await self._store.append_entry(self._session_id, entry)
        except Exception as exc:
            raise AgentHarnessError(
                "session", f"Failed to persist {write.type}", cause=exc,
            ) from exc

    async def _flush_pending_writes(self) -> None:
        """Flush all queued session writes (FIFO)."""
        while self._pending_writes:
            write = self._pending_writes[0]
            await self._persist_pending_write(write)
            self._pending_writes.pop(0)

    async def _apply_config_write(self, write: PendingSessionWrite) -> None:
        """Persist immediately when idle, enqueue when busy."""
        if self.phase == AgentHarnessPhase.IDLE:
            await self._persist_pending_write(write)
        else:
            self._pending_writes.append(write)

    # ---------- config setters (harness owns) ----------
    def get_model(self) -> Any:
        return self._agent.state.model

    async def set_model(self, model: Any) -> None:
        previous_model = self._agent.state.model
        write = PendingSessionWrite(
            type="model_change",
            data={"provider": getattr(model, "provider", ""), "model_id": getattr(model, "id", "")},
        )
        await self._apply_config_write(write)
        self._agent.state.model = model
        await self._notify_listeners(ModelUpdate(
            model=model, previous_model=previous_model, source="set",
        ))

    def get_thinking_level(self) -> str:
        return self._agent.state.thinking_level

    async def set_thinking_level(self, level: str) -> None:
        previous_level = self._agent.state.thinking_level
        write = PendingSessionWrite(
            type="thinking_level_change",
            data={"thinking_level": level},
        )
        await self._apply_config_write(write)
        self._agent.state.thinking_level = level
        await self._notify_listeners(ThinkingLevelUpdate(
            level=level, previous_level=previous_level,
        ))

    def get_tools(self) -> list[Any]:
        return list(self._agent.state.tools)

    async def set_tools(self, tools: list[Any], active_tool_names: list[str] | None = None) -> None:
        names = [_resolve_tool_name(t, i) for i, t in enumerate(tools)]
        if len(names) != len(set(names)):
            raise AgentHarnessError("invalid_argument", "Duplicate tool name(s)")
        previous_tool_names = [
            _resolve_tool_name(t, i) for i, t in enumerate(self._agent.state.tools)
        ]
        if active_tool_names is None:
            active_tool_names = list(names)
        unknown = [n for n in active_tool_names if n not in names]
        if unknown:
            raise AgentHarnessError("invalid_argument", f"Unknown tool(s): {', '.join(unknown)}")
        write = PendingSessionWrite(
            type="active_tools_change",
            data={"active_tool_names": list(active_tool_names)},
        )
        await self._apply_config_write(write)
        self._agent.state.tools = list(tools)
        self._agent._active_tool_names = list(active_tool_names)
        await self._notify_listeners(ToolsUpdate(
            tool_names=names, previous_tool_names=previous_tool_names,
            active_tool_names=list(active_tool_names),
            previous_active_tool_names=previous_tool_names, source="set",
        ))

    async def set_active_tools(self, tool_names: list[str]) -> None:
        all_names = {
            _resolve_tool_name(t, i) for i, t in enumerate(self._agent.state.tools)
        }
        unknown = [n for n in tool_names if n not in all_names]
        if unknown:
            raise AgentHarnessError("invalid_argument", f"Unknown tool(s): {', '.join(unknown)}")
        previous_tool_names = [
            _resolve_tool_name(t, i) for i, t in enumerate(self._agent.state.tools)
        ]
        write = PendingSessionWrite(
            type="active_tools_change",
            data={"active_tool_names": list(tool_names)},
        )
        await self._apply_config_write(write)
        self._agent._active_tool_names = list(tool_names)
        await self._notify_listeners(ToolsUpdate(
            tool_names=previous_tool_names, previous_tool_names=previous_tool_names,
            active_tool_names=list(tool_names),
            previous_active_tool_names=previous_tool_names, source="set",
        ))

    def get_stream_options(self) -> dict[str, Any]:
        from agent_core.core.stream_options import clone_stream_options
        return clone_stream_options(self._agent._stream_options)

    def set_stream_options(self, options: dict[str, Any]) -> None:
        from agent_core.core.stream_options import clone_stream_options
        self._agent._stream_options = clone_stream_options(options)

    # ---------- listener notification (harness owns) ----------
    async def _notify_listeners(self, evt: AgentEvent) -> None:
        for listener in list(self._listeners):
            result = listener(evt)
            if inspect.isawaitable(result):
                await result

    def _restore_messages(self, snapshot: Any) -> None:
        """Hydrate agent.state.messages from a loaded SessionSnapshot."""
        restored: list[Any] = []
        for entry in snapshot.entries:
            if isinstance(entry, MessageEntry):
                try:
                    restored.append(deserialize_message(entry.message))
                except Exception as exc:
                    logger.warning(
                        "Failed to restore message %s in session %s: %s",
                        entry.id,
                        self._session_id,
                        exc,
                    )
        if restored:
            self._agent.state.messages = restored

    # ---------- event handling (harness authority) ----------
    async def _handle_event(self, evt: AgentEvent, context: Any = None) -> None:
        """Handle an event from the emit sink.

        This is the single entry point for all event handling when the
        session is the harness:  state updates → persistence → extensions
        → listener notification.
        """
        # -- state updates on agent.state --
        if isinstance(evt, MessageStart):
            if hasattr(evt, "message") and hasattr(evt.message, "role"):
                from agent_core.core.messages import AssistantMessage
                if isinstance(evt.message, AssistantMessage):
                    self._agent.state.streaming_message = evt.message
        elif isinstance(evt, MessageUpdate):
            self._agent.state.streaming_message = evt.message
        elif isinstance(evt, MessageEnd):
            self._agent.state.streaming_message = None
            self._agent.state.messages.append(evt.message)
        elif isinstance(evt, TurnEnd):
            msg = evt.message
            from agent_core.core.messages import AssistantMessage
            if isinstance(msg, AssistantMessage) and msg.error_message:
                self._agent.state.error_message = msg.error_message
            for tool_result in evt.tool_results:
                self._agent.state.messages.append(tool_result)
            await self._flush_pending_writes()
        elif isinstance(evt, AgentEnd):
            self._agent.state.streaming_message = None
            await self._flush_pending_writes()
            self.phase = AgentHarnessPhase.IDLE

        # Track executing tool calls
        if isinstance(evt, ToolExecutionStart):
            self._agent._pending_tool_calls.add(evt.tool_call_id)
        elif isinstance(evt, ToolExecutionEnd):
            self._agent._pending_tool_calls.discard(evt.tool_call_id)

        # -- persistence --
        if isinstance(evt, MessageEnd):
            await self._persist_message(evt.message)
        elif isinstance(evt, ToolExecutionEnd):
            await self._persist_tool_result(evt)
        elif isinstance(evt, AgentEnd):
            if self._compactor is not None:
                await self._maybe_compact()

        # -- extension notification --
        if self._ext_runner is not None:
            await self._ext_runner.on_event(evt)

        # -- listener notification --
        await self._notify_listeners(evt)
        if isinstance(evt, AgentEnd):
            await self._notify_listeners(Settled())

    # ---------- persistence helpers ----------
    async def _persist_message(self, message: Any) -> None:
        entry = MessageEntry(
            message=message.model_dump(mode="json"),
            id=f"msg-{int(time.time() * 1000)}",
        )
        await self._store_entry(entry)

    async def _persist_tool_result(self, evt: ToolExecutionEnd) -> None:
        """Persist tool results as tool_result messages in the session."""
        result_text = ""
        result = getattr(evt, "result", None)
        if result and hasattr(result, "content"):
            for item in result.content:
                if hasattr(item, "text"):
                    result_text = item.text
                    break
        elif result and hasattr(result, "text"):
            result_text = result.text

        entry = MessageEntry(
            message={
                "role": "tool_result",
                "tool_call_id": evt.tool_call_id,
                "tool_name": evt.tool_name,
                "content": [{"type": "text", "text": result_text}] if result_text else [],
                "is_error": getattr(evt, "is_error", False),
                "timestamp": time.time(),
            },
            id=f"tool-{int(time.time() * 1000)}",
        )
        await self._store_entry(entry)

    async def _store_entry(self, entry: MessageEntry) -> None:
        try:
            await self._store.append_entry(self._session_id, entry)
        except Exception as exc:
            logger.warning("Failed to persist entry for session %s: %s", self._session_id, exc)

    async def _maybe_compact(self) -> None:
        if self._compactor is None:
            return
        try:
            model = getattr(self._agent.state, "model", None)
            context_window = getattr(model, "context_window", 0) if model else 0
            messages = list(self._agent.state.messages)
            if not context_window or not self._compactor.should_compact(
                messages, context_window=context_window
            ):
                return

            async def _threshold_compact(msgs: list[Any]) -> bool:
                result = await self._compactor.compact(
                    msgs, reason="threshold", signal=None
                )
                entry = CompactionEntry(
                    summary=result.summary,
                    first_kept_entry_id=result.first_kept_entry_id,
                    tokens_before=result.tokens_before,
                    id=f"compaction-{int(time.time() * 1000)}",
                )
                await self._store.append_entry(self._session_id, entry)

                if result.summary and result.kept_count > 0:
                    from agent_core.core.messages import CustomMessage

                    summary_msg = CustomMessage(
                        custom_type="compaction_summary",
                        content=result.summary,
                        timestamp=time.time(),
                    )
                    kept = msgs[-result.kept_count:]
                    msgs.clear()
                    msgs.append(summary_msg)
                    msgs.extend(kept)
                    self._agent.state.messages = list(msgs)
                    return True
                return False

            old_cb = self._agent._compact_callback
            self._agent._compact_callback = _threshold_compact
            try:
                await self._agent.compact()
            finally:
                self._agent._compact_callback = old_cb
        except Exception as exc:
            logger.warning("Compaction failed for session %s: %s", self._session_id, exc)


# Backward compatibility alias
AgentSession = AgentHarness
