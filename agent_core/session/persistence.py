"""Session persistence helpers for AgentHarness — no runtime phase ownership."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from agent_core.core.errors import AgentHarnessError
from agent_core.core.messages import deserialize_message
from agent_core.core.pending_writes import PendingSessionWrite
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


class HarnessPersistence:
    """Store read/write only. Runtime config replay mutates *apply_state* callbacks."""

    def __init__(self, store: SessionStore, session_id: str) -> None:
        self._store = store
        self._session_id = session_id

    @property
    def session_id(self) -> str:
        return self._session_id

    async def create_session(self, header: SessionHeader) -> None:
        await self._store.create_session(self._session_id, header)

    async def load_session(self) -> Any:
        return await self._store.load_session(self._session_id)

    async def close(self) -> None:
        await self._store.close()

    async def append_entry(self, entry: Any) -> None:
        try:
            await self._store.append_entry(self._session_id, entry)
        except Exception as exc:
            raise AgentHarnessError(
                "session",
                f"Failed to persist entry for session {self._session_id}",
                cause=exc,
            ) from exc

    def pending_write_to_entry(self, write: PendingSessionWrite) -> Any:
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

    async def persist_pending_write(self, write: PendingSessionWrite) -> None:
        await self.append_entry(self.pending_write_to_entry(write))

    async def persist_message(self, message: Any) -> None:
        entry = MessageEntry(
            message=message.model_dump(mode="json"),
            id=f"msg-{int(time.time() * 1000)}",
        )
        await self.append_entry(entry)

    async def persist_tool_result(self, evt: Any) -> None:
        result_text = ""
        result = getattr(evt, "result", None)
        if result and hasattr(result, "content"):
            for item in result.content:
                if hasattr(item, "text"):
                    result_text = item.text
                    break
        elif result and hasattr(result, "text"):
            result_text = result.text

        message: dict[str, Any] = {
            "role": "tool_result",
            "tool_call_id": evt.tool_call_id,
            "tool_name": evt.tool_name,
            "content": [{"type": "text", "text": result_text}] if result_text else [],
            "is_error": getattr(evt, "is_error", False),
            "timestamp": time.time(),
        }
        details = getattr(result, "details", None) if result is not None else None
        if details is not None:
            message["details"] = details
        entry = MessageEntry(
            message=message,
            id=f"tool-{int(time.time() * 1000)}",
        )
        await self.append_entry(entry)

    async def persist_compaction(self, result: Any) -> None:
        entry = CompactionEntry(
            summary=result.summary,
            first_kept_entry_id=result.first_kept_entry_id,
            tokens_before=result.tokens_before,
            id=f"compaction-{int(time.time() * 1000)}",
        )
        await self.append_entry(entry)

    def replay_entries(
        self,
        snapshot: Any,
        *,
        apply_message: Callable[[Any], None],
        apply_model_change: Callable[[ModelChangeEntry], None],
        apply_thinking_level: Callable[[ThinkingLevelChangeEntry], None],
        apply_active_tools: Callable[[ActiveToolsChangeEntry], None],
    ) -> None:
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
            elif isinstance(entry, ModelChangeEntry):
                apply_model_change(entry)
            elif isinstance(entry, ThinkingLevelChangeEntry):
                apply_thinking_level(entry)
            elif isinstance(entry, ActiveToolsChangeEntry):
                apply_active_tools(entry)
        if restored:
            apply_message(restored)
