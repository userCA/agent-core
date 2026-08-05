"""SQLite-backed SessionStore — lightweight local database adapter.

Uses the stdlib ``sqlite3`` module (no extra dependency). Safe for single-process
Scene hosts; for multi-process writers prefer a networked DB adapter.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

from agent_core.session.jsonl_store import _deserialize_entry
from agent_core.session.store import (
    SessionEntry,
    SessionHeader,
    SessionMeta,
    SessionSnapshot,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    header_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entries (
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    entry_json TEXT NOT NULL,
    PRIMARY KEY (session_id, seq),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);
CREATE INDEX IF NOT EXISTS idx_entries_session ON entries(session_id);
"""


def _title_from_entry_payload(data: dict[str, Any]) -> str:
    if data.get("type") != "message":
        return ""
    msg = data.get("message", {})
    if msg.get("role") != "user":
        return ""
    content = msg.get("content", "")
    if isinstance(content, list) and content:
        text_parts = [
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        content_text = "".join(text_parts)
    elif isinstance(content, str):
        content_text = content
    else:
        content_text = str(content) if content else ""
    if not content_text:
        return ""
    return content_text[:30] + ("..." if len(content_text) > 30 else "")


class SqliteStore:
    """SessionStore implementation backed by a single SQLite file."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        if self._path.parent and str(self._path.parent) not in ("", "."):
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._lock = asyncio.Lock()

    async def create_session(self, session_id: str, header: SessionHeader) -> None:
        async with self._lock:
            await asyncio.to_thread(self._create_session_sync, session_id, header)

    def _create_session_sync(self, session_id: str, header: SessionHeader) -> None:
        self._conn.execute(
            "INSERT INTO sessions (session_id, header_json, created_at) VALUES (?, ?, ?)",
            (session_id, json.dumps(header.model_dump(), ensure_ascii=False), header.timestamp),
        )
        self._conn.commit()

    async def append_entry(self, session_id: str, entry: SessionEntry) -> None:
        async with self._lock:
            await asyncio.to_thread(self._append_entry_sync, session_id, entry)

    def _append_entry_sync(self, session_id: str, entry: SessionEntry) -> None:
        row = self._conn.execute(
            "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Session {session_id} not found")
        seq_row = self._conn.execute(
            "SELECT COALESCE(MAX(seq), 0) AS m FROM entries WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        next_seq = int(seq_row["m"]) + 1
        self._conn.execute(
            "INSERT INTO entries (session_id, seq, entry_json) VALUES (?, ?, ?)",
            (session_id, next_seq, json.dumps(entry.model_dump(mode="json"), ensure_ascii=False)),
        )
        self._conn.commit()

    async def load_session(self, session_id: str) -> SessionSnapshot:
        async with self._lock:
            return await asyncio.to_thread(self._load_session_sync, session_id)

    def _load_session_sync(self, session_id: str) -> SessionSnapshot:
        row = self._conn.execute(
            "SELECT header_json FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Session {session_id} not found")
        header = SessionHeader.model_validate(json.loads(row["header_json"]))
        entry_rows = self._conn.execute(
            "SELECT entry_json FROM entries WHERE session_id = ? ORDER BY seq ASC",
            (session_id,),
        ).fetchall()
        entries: list[SessionEntry] = [
            _deserialize_entry(json.loads(r["entry_json"])) for r in entry_rows
        ]
        return SessionSnapshot(header=header, entries=entries)

    async def list_sessions(
        self, *, owner: str | None = None, agent_id: str | None = None, limit: int = 50
    ) -> list[SessionMeta]:
        async with self._lock:
            return await asyncio.to_thread(self._list_sessions_sync, owner, agent_id, limit)

    def _list_sessions_sync(self, owner: str | None, agent_id: str | None, limit: int) -> list[SessionMeta]:
        # Fetch more rows when filtering by owner/agent_id so LIMIT applies after filter.
        fetch_limit = limit if (owner is None and agent_id is None) else max(limit * 10, 100)
        rows = self._conn.execute(
            "SELECT session_id, header_json, created_at FROM sessions "
            "ORDER BY created_at DESC LIMIT ?",
            (fetch_limit,),
        ).fetchall()
        result: list[SessionMeta] = []
        for row in rows:
            sid = row["session_id"]
            header = SessionHeader.model_validate(json.loads(row["header_json"]))
            if owner is not None and header.owner != owner:
                continue
            if agent_id is not None and header.agent_id != agent_id:
                continue
            count_row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM entries WHERE session_id = ?", (sid,)
            ).fetchone()
            entry_count = int(count_row["c"])
            title = ""
            entry_rows = self._conn.execute(
                "SELECT entry_json FROM entries WHERE session_id = ? ORDER BY seq ASC",
                (sid,),
            ).fetchall()
            for er in entry_rows:
                try:
                    title = _title_from_entry_payload(json.loads(er["entry_json"]))
                except (json.JSONDecodeError, TypeError, AttributeError):
                    continue
                if title:
                    break
            result.append(
                SessionMeta(
                    session_id=sid,
                    created_at=header.timestamp,
                    entry_count=entry_count,
                    title=title,
                    agent_id=header.agent_id,
                )
            )
            if len(result) >= limit:
                break
        return result

    async def delete_session(self, session_id: str) -> bool:
        async with self._lock:
            return await asyncio.to_thread(self._delete_session_sync, session_id)

    def _delete_session_sync(self, session_id: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
        )
        if cur.fetchone() is None:
            return False
        self._conn.execute("DELETE FROM entries WHERE session_id = ?", (session_id,))
        self._conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        self._conn.commit()
        return True

    async def fork_session(
        self, source_session_id: str, new_session_id: str, *, header: SessionHeader
    ) -> None:
        source = await self.load_session(source_session_id)
        async with self._lock:
            exists = await asyncio.to_thread(
                lambda: self._conn.execute(
                    "SELECT 1 FROM sessions WHERE session_id = ?", (new_session_id,)
                ).fetchone()
            )
            if exists is not None:
                raise ValueError(f"Session {new_session_id} already exists")
        await self.create_session(new_session_id, header)
        for entry in source.entries:
            await self.append_entry(new_session_id, entry.model_copy(deep=True))

    async def close(self) -> None:
        async with self._lock:
            if getattr(self, "_closed", False):
                return
            await asyncio.to_thread(self._conn.close)
            self._closed = True
