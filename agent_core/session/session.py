"""AgentSession — composition layer: Agent + Store + event persistence."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from agent_core.compaction.compactor import Compactor, CompactionResult
from agent_core.core.events import AgentEnd, AgentEvent, MessageEnd
from agent_core.extensions.base import ExtensionContext, ExtensionRunner
from agent_core.session.store import CompactionEntry, MessageEntry, SessionHeader, SessionStore

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
            await self._store.load_session(self._session_id)
        except KeyError:
            await self._store.create_session(self._session_id, header)

        self._agent_unsub = self._agent.subscribe(self._on_agent_event)
        if self._extensions:
            ext_ctx = ExtensionContext(
                session_id=self._session_id,
                agent=self._agent,
                store=self._store,
            )
            self._ext_runner = ExtensionRunner(self._extensions, ext_ctx)
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
        except Exception:
            pass

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
        except Exception:
            pass
