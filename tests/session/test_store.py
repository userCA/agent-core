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
