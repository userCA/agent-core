"""AgentSession — composition layer: Agent + Store + event persistence."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from agent_core.compaction.compactor import Compactor, CompactionResult
from agent_core.core.events import AgentEnd, AgentEvent, MessageEnd
from agent_core.core.messages import deserialize_message
from agent_core.extensions.base import ExtensionContext, ExtensionRunner
from agent_core.session.store import CompactionEntry, MessageEntry, SessionHeader, SessionStore

logger = logging.getLogger(__name__)

Listener = Callable[[AgentEvent], Awaitable[None] | None]
Unsubscribe = Callable[[], None]


class AgentSession:
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
        self._agent_unsub: Unsubscribe | None = None
        self._started = False
        self._closed = False
        self._ext_runner: ExtensionRunner | None = None

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

        self._agent_unsub = self._agent.subscribe(self._on_agent_event)
        if self._extensions:
            ext_ctx = ExtensionContext(
                session_id=self._session_id,
                agent=self._agent,
                store=self._store,
            )
            self._ext_runner = ExtensionRunner(self._extensions, ext_ctx)

        # Chain Extension before_tool_call hooks after any scene-layer hook
        if self._ext_runner is not None:
            existing = getattr(self._agent, "_before_tool_call", None)

            async def _chained_before(call_ctx: dict[str, Any]) -> dict[str, Any] | None:
                result = None
                if existing is not None:
                    result = await existing(call_ctx)
                    if result and result.get("block"):
                        return result

                ext_result = await self._ext_runner.before_tool_call(call_ctx)
                if ext_result and ext_result.get("block"):
                    return ext_result

                merged: dict[str, Any] = {}
                for r in (result, ext_result):
                    if r and r.get("inject_metadata"):
                        merged.update(r["inject_metadata"])
                return {"inject_metadata": merged} if merged else None

            self._agent._before_tool_call = _chained_before

        # Chain Extension.transform_context
        if self._extensions:
            ext_transforms = [getattr(e, "transform_context", None) for e in self._extensions]
            ext_transforms = [t for t in ext_transforms if callable(t)]
            if ext_transforms:
                existing_transform = getattr(self._agent, "_transform_context", None)

                async def _chained_transform(llm_messages, signal):
                    current = llm_messages
                    if existing_transform is not None:
                        current = await existing_transform(current, signal)
                    for t in ext_transforms:
                        current = await t(current, signal)
                    return current

                self._agent._transform_context = _chained_transform
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
        await self._agent.prompt(text, **opts)

    async def continue_(self) -> None:
        self._check_ready()
        await self._agent.continue_()

    async def compact(self, *, instructions: str | None = None) -> None:
        """Manually trigger compaction."""
        self._check_ready()
        if self._compactor is None:
            return
        messages = list(self._agent.state.messages)
        result = await self._compactor.compact(
            messages, reason="manual", instructions=instructions, signal=None
        )
        entry = CompactionEntry(
            summary=result.summary,
            first_kept_entry_id=result.first_kept_entry_id,
            tokens_before=result.tokens_before,
            id=f"compaction-{int(time.time() * 1000)}",
        )
        await self._store.append_entry(self._session_id, entry)

    def abort(self) -> None:
        self._agent.abort()

    async def dispose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._agent_unsub is not None:
            self._agent_unsub()
            self._agent_unsub = None
        await self._store.close()

    def _check_ready(self) -> None:
        if self._closed:
            raise RuntimeError("AgentSession is disposed")
        if not self._started:
            raise RuntimeError("AgentSession not started; call start() first")

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

    # ---------- event handling ----------
    async def _on_agent_event(self, evt: AgentEvent) -> None:
        if isinstance(evt, MessageEnd):
            await self._persist_message(evt.message)
        elif isinstance(evt, AgentEnd):
            if self._compactor is not None:
                await self._maybe_compact()

        if self._ext_runner is not None:
            await self._ext_runner.on_event(evt)

        for listener in list(self._listeners):
            result = listener(evt)
            if result is not None and hasattr(result, "__await__"):
                await result

    async def _persist_message(self, message: Any) -> None:
        entry = MessageEntry(
            message=message.model_dump(mode="json"),
            id=f"msg-{int(time.time() * 1000)}",
        )
        try:
            await self._store.append_entry(self._session_id, entry)
        except Exception as exc:
            logger.warning("Failed to persist message for session %s: %s", self._session_id, exc)

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

            result = await self._compactor.compact(
                messages, reason="threshold", signal=None
            )
            entry = CompactionEntry(
                summary=result.summary,
                first_kept_entry_id=result.first_kept_entry_id,
                tokens_before=result.tokens_before,
                id=f"compaction-{int(time.time() * 1000)}",
            )
            await self._store.append_entry(self._session_id, entry)
        except Exception as exc:
            logger.warning("Compaction failed for session %s: %s", self._session_id, exc)
