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

    async def list_sessions(
        self, *, owner: str | None = None, agent_id: str | None = None, limit: int = 50
    ) -> list[SessionMeta]:
        result: list[SessionMeta] = []
        for sid, snap in self._sessions.items():
            if owner is not None and snap.header.owner != owner:
                continue
            if agent_id is not None and snap.header.agent_id != agent_id:
                continue
            result.append(
                SessionMeta(
                    session_id=sid,
                    created_at=snap.header.timestamp,
                    entry_count=len(snap.entries),
                    agent_id=snap.header.agent_id,
                )
            )
        return result[:limit]

    async def delete_session(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        del self._sessions[session_id]
        return True

    async def fork_session(
        self, source_session_id: str, new_session_id: str, *, header: SessionHeader
    ) -> None:
        source = await self.load_session(source_session_id)
        if new_session_id in self._sessions:
            raise ValueError(f"Session {new_session_id} already exists")
        # Deep-copy entries so later parent writes do not mutate the fork.
        copied = [e.model_copy(deep=True) for e in source.entries]
        self._sessions[new_session_id] = SessionSnapshot(header=header, entries=copied)

    async def close(self) -> None:
        pass
