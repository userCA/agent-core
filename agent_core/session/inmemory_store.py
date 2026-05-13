"""In-memory SessionStore for testing and short-lived sessions."""

from __future__ import annotations

from agent_core.session.store import SessionEntry, SessionHeader, SessionMeta, SessionSnapshot


class InMemoryStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionSnapshot] = {}

    async def create_session(self, session_id: str, header: SessionHeader) -> None:
        self._sessions[session_id] = SessionSnapshot(header=header, entries=[])

    async def append_entry(self, session_id: str, entry: SessionEntry) -> None:
        snap = self._sessions.get(session_id)
        if snap is None:
            raise KeyError(f"Session {session_id} not found")
        snap.entries.append(entry)

    async def load_session(self, session_id: str) -> SessionSnapshot:
        snap = self._sessions.get(session_id)
        if snap is None:
            raise KeyError(f"Session {session_id} not found")
        return SessionSnapshot(header=snap.header, entries=list(snap.entries))

    async def list_sessions(self, *, owner: str | None = None, limit: int = 50) -> list[SessionMeta]:
        result: list[SessionMeta] = []
        for sid, snap in self._sessions.items():
            result.append(
                SessionMeta(
                    session_id=sid,
                    created_at=snap.header.timestamp,
                    entry_count=len(snap.entries),
                )
            )
        return result[:limit]

    async def close(self) -> None:
        pass
