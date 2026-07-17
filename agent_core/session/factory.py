"""Factory for SessionStore backends."""

from __future__ import annotations

import os

from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.jsonl_store import JsonlStore
from agent_core.session.sqlite_store import SqliteStore
from agent_core.session.store import SessionStore


def create_session_store(
    backend: str | None = None,
    *,
    directory: str = "./sessions",
    sqlite_path: str | None = None,
) -> SessionStore:
    """Create a SessionStore from *backend* or ``SESSION_STORE`` env.

    Backends:
    - ``jsonl`` (default): one ``.jsonl`` file per session under *directory*
    - ``sqlite``: single SQLite DB (stdlib; path from *sqlite_path* /
      ``SESSION_SQLITE_PATH`` / ``{directory}/sessions.db``)
    - ``inmemory``: process memory only
    """
    name = (backend or os.environ.get("SESSION_STORE", "jsonl")).strip().lower()
    if name in ("sqlite", "sqlite3"):
        path = (
            sqlite_path
            or os.environ.get("SESSION_SQLITE_PATH")
            or os.path.join(directory, "sessions.db")
        )
        return SqliteStore(path)
    if name in ("inmemory", "memory"):
        return InMemoryStore()
    if name in ("jsonl", "file", ""):
        return JsonlStore(directory)
    raise ValueError(f"Unknown SESSION_STORE backend: {backend!r}")
