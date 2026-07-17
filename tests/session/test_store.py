import asyncio
from datetime import datetime, timezone

import pytest

from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.jsonl_store import JsonlStore
from agent_core.session.store import (
    CompactionEntry,
    MessageEntry,
    ModelChangeEntry,
    SessionHeader,
)


def _header(sid: str) -> SessionHeader:
    return SessionHeader(id=sid, timestamp=datetime.now(tz=timezone.utc).isoformat(), cwd="/tmp")


@pytest.mark.asyncio
async def test_inmemory_store_roundtrip():
    store = InMemoryStore()
    await store.create_session("s1", _header("s1"))
    await store.append_entry("s1", MessageEntry(message={"role": "user", "text": "hi"}, id="e1"))
    await store.append_entry("s1", CompactionEntry(summary="s", first_kept_entry_id="e1", tokens_before=100, id="e2"))

    snap = await store.load_session("s1")
    assert snap.header.id == "s1"
    assert len(snap.entries) == 2
    assert isinstance(snap.entries[0], MessageEntry)
    assert isinstance(snap.entries[1], CompactionEntry)

    sessions = await store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].entry_count == 2


@pytest.mark.asyncio
async def test_jsonl_store_roundtrip(tmp_path):
    store = JsonlStore(str(tmp_path))
    await store.create_session("s1", _header("s1"))
    await store.append_entry("s1", MessageEntry(message={"role": "user", "text": "hi"}, id="e1"))
    await store.append_entry("s1", ModelChangeEntry(provider="openai", model_id="gpt-4o", id="e2"))

    snap = await store.load_session("s1")
    assert len(snap.entries) == 2
    assert isinstance(snap.entries[0], MessageEntry)
    assert isinstance(snap.entries[1], ModelChangeEntry)

    sessions = await store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].entry_count == 2


@pytest.mark.asyncio
async def test_jsonl_store_load_missing():
    store = JsonlStore("/tmp/nonexistent_jsonl_store_12345")
    with pytest.raises(KeyError):
        await store.load_session("missing")


@pytest.mark.asyncio
async def test_sqlite_store_roundtrip(tmp_path):
    from agent_core.session.sqlite_store import SqliteStore

    store = SqliteStore(str(tmp_path / "sessions.db"))
    await store.create_session("s1", _header("s1"))
    await store.append_entry(
        "s1",
        MessageEntry(
            message={"role": "user", "content": [{"type": "text", "text": "hello sqlite"}]},
            id="e1",
        ),
    )
    await store.append_entry("s1", ModelChangeEntry(provider="openai", model_id="gpt-4o", id="e2"))
    await store.append_entry(
        "s1",
        CompactionEntry(summary="sum", first_kept_entry_id="e1", tokens_before=10, id="e3"),
    )

    snap = await store.load_session("s1")
    assert snap.header.id == "s1"
    assert len(snap.entries) == 3
    assert isinstance(snap.entries[0], MessageEntry)
    assert isinstance(snap.entries[1], ModelChangeEntry)
    assert isinstance(snap.entries[2], CompactionEntry)

    sessions = await store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].session_id == "s1"
    assert sessions[0].entry_count == 3
    assert "hello sqlite" in sessions[0].title

    await store.close()


@pytest.mark.asyncio
async def test_sqlite_store_load_missing(tmp_path):
    from agent_core.session.sqlite_store import SqliteStore

    store = SqliteStore(str(tmp_path / "empty.db"))
    with pytest.raises(KeyError):
        await store.load_session("missing")
    await store.close()


@pytest.mark.asyncio
async def test_sqlite_store_persists_across_instances(tmp_path):
    from agent_core.session.sqlite_store import SqliteStore

    db = str(tmp_path / "persist.db")
    store1 = SqliteStore(db)
    await store1.create_session("s1", _header("s1"))
    await store1.append_entry("s1", MessageEntry(message={"role": "user", "text": "hi"}, id="e1"))
    await store1.close()

    store2 = SqliteStore(db)
    snap = await store2.load_session("s1")
    assert len(snap.entries) == 1
    await store2.close()


@pytest.mark.asyncio
async def test_sqlite_store_delete_session(tmp_path):
    from agent_core.session.sqlite_store import SqliteStore

    store = SqliteStore(str(tmp_path / "del.db"))
    await store.create_session("s1", _header("s1"))
    await store.append_entry("s1", MessageEntry(message={"role": "user", "text": "x"}, id="e1"))
    assert await store.delete_session("s1") is True
    with pytest.raises(KeyError):
        await store.load_session("s1")
    assert await store.delete_session("s1") is False
    await store.close()


@pytest.mark.asyncio
async def test_create_session_store_sqlite(tmp_path, monkeypatch):
    from agent_core.session.factory import create_session_store
    from agent_core.session.sqlite_store import SqliteStore

    monkeypatch.setenv("SESSION_STORE", "sqlite")
    monkeypatch.setenv("SESSION_SQLITE_PATH", str(tmp_path / "env.db"))
    store = create_session_store(directory=str(tmp_path))
    assert isinstance(store, SqliteStore)
    await store.create_session("s1", _header("s1"))
    await store.close()
