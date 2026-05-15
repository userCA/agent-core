"""Session manager for the HTTP SSE chat scene.

Note: Concurrent access to the same session_id is not fully serialized.
This is acceptable for a demo scene; production would need a more robust
session lifecycle (e.g., tracking creation-in-progress futures).
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any

from agent_core.session.jsonl_store import JsonlStore
from agent_core.session.store import SessionStore

from scene.http_sse.chat_assistant import ChatAssistant


_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _generate_session_id() -> str:
    return f"scene-{int(time.time() * 1000)}"


def _validate_session_id(sid: str) -> None:
    if not _SESSION_ID_RE.match(sid):
        raise ValueError(f"Invalid session_id: {sid}")


class SessionManager:
    """Manages ChatAssistant instances and their persistent storage."""

    def __init__(
        self,
        *,
        cwd: str = "",
        session_store_dir: str = "./sessions",
    ) -> None:
        self._cwd = cwd or os.getcwd()
        self._store_dir = session_store_dir
        self._sessions: dict[str, ChatAssistant] = {}
        self._lock = asyncio.Lock()
        self._create_locks: dict[str, asyncio.Lock] = {}

    async def get_or_create(self, session_id: str | None) -> tuple[str, ChatAssistant]:
        """Get an existing assistant or create a new one."""
        if session_id:
            _validate_session_id(session_id)
            if session_id in self._sessions:
                return session_id, self._sessions[session_id]

        sid = session_id or _generate_session_id()
        _validate_session_id(sid)
        lock = self._create_locks.setdefault(sid, asyncio.Lock())
        async with lock:
            # Re-check inside lock
            if sid in self._sessions:
                return sid, self._sessions[sid]
            store = JsonlStore(self._store_dir)
            
            provider_name = os.environ.get("AGENT_PROVIDER", "openai")
            model_id = os.environ.get("AGENT_MODEL", "gpt-4o")
            api_key_env = os.environ.get("AGENT_API_KEY_ENV")
            
            assistant = await ChatAssistant.create(
                session_store=store,
                session_id=sid,
                cwd=self._cwd,
                provider_name=provider_name,
                model_id=model_id,
                api_key_env=api_key_env,
            )
            async with self._lock:
                self._sessions[sid] = assistant
        self._create_locks.pop(sid, None)
        return sid, assistant

    async def dispose(self, session_id: str) -> None:
        """Dispose a session and remove it from memory."""
        _validate_session_id(session_id)
        lock = self._create_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            assistant = self._sessions.pop(session_id, None)
            self._create_locks.pop(session_id, None)
        if assistant:
            await assistant.dispose()

    async def dispose_all(self) -> None:
        """Dispose all active sessions."""
        async with self._lock:
            items = list(self._sessions.items())
            self._sessions.clear()
            self._create_locks.clear()
        for _, assistant in items:
            await assistant.dispose()
