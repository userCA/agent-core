"""SessionStore Protocol and SessionEntry types."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel


class SessionHeader(BaseModel):
    type: str = "session"
    version: str = "1"
    id: str
    timestamp: str
    cwd: str = ""


class MessageEntry(BaseModel):
    type: str = "message"
    message: Any
    parent_id: str | None = None
    id: str


class CompactionEntry(BaseModel):
    type: str = "compaction"
    summary: str
    first_kept_entry_id: str
    tokens_before: int
    details: Any | None = None
    from_extension: bool = False


class ModelChangeEntry(BaseModel):
    type: str = "model_change"
    provider: str
    model_id: str
    id: str


class ThinkingLevelChangeEntry(BaseModel):
    type: str = "thinking_level_change"
    level: str
    id: str


class CustomEntry(BaseModel):
    type: str = "custom"
    custom_type: str
    data: Any
    id: str


SessionEntry = MessageEntry | CompactionEntry | ModelChangeEntry | ThinkingLevelChangeEntry | CustomEntry


class SessionSnapshot(BaseModel):
    header: SessionHeader
    entries: list[SessionEntry]


class SessionMeta(BaseModel):
    session_id: str
    created_at: str
    entry_count: int
    title: str = ""


class SessionStore(Protocol):
    async def create_session(self, session_id: str, header: SessionHeader) -> None: ...

    async def append_entry(self, session_id: str, entry: SessionEntry) -> None: ...

    async def load_session(self, session_id: str) -> SessionSnapshot: ...

    async def list_sessions(self, *, owner: str | None = None, limit: int = 50) -> list[SessionMeta]: ...

    async def close(self) -> None: ...
