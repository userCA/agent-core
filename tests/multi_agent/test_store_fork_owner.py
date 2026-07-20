"""SessionStore owner filtering and fork_session."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.jsonl_store import JsonlStore
from agent_core.session.sqlite_store import SqliteStore
from agent_core.session.store import MessageEntry, SessionHeader


def _header(sid: str, owner: str = "") -> SessionHeader:
    return SessionHeader(
        id=sid,
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
        cwd="/tmp",
        owner=owner,
    )


@pytest.mark.asyncio
async def test_inmemory_list_sessions_filters_owner():
    store = InMemoryStore()
    await store.create_session("a1", _header("a1", owner="alice"))
    await store.create_session("b1", _header("b1", owner="bob"))
    alice = await store.list_sessions(owner="alice")
    assert [s.session_id for s in alice] == ["a1"]
    all_sessions = await store.list_sessions()
    assert {s.session_id for s in all_sessions} == {"a1", "b1"}


@pytest.mark.asyncio
async def test_inmemory_fork_session_copies_entries():
    store = InMemoryStore()
    await store.create_session("parent", _header("parent", owner="alice"))
    await store.append_entry(
        "parent", MessageEntry(message={"role": "user", "content": "hi"}, id="e1")
    )
    await store.fork_session(
        "parent", "child", header=_header("child", owner="alice")
    )
    child = await store.load_session("child")
    assert child.header.id == "child"
    assert child.header.owner == "alice"
    assert len(child.entries) == 1
    assert isinstance(child.entries[0], MessageEntry)
    # Independent: append to parent does not affect child
    await store.append_entry(
        "parent", MessageEntry(message={"role": "assistant", "content": "yo"}, id="e2")
    )
    child2 = await store.load_session("child")
    assert len(child2.entries) == 1


@pytest.mark.asyncio
async def test_jsonl_fork_and_owner(tmp_path):
    store = JsonlStore(str(tmp_path))
    await store.create_session("p", _header("p", owner="u1"))
    await store.append_entry("p", MessageEntry(message={"role": "user", "text": "x"}, id="e1"))
    await store.create_session("other", _header("other", owner="u2"))
    listed = await store.list_sessions(owner="u1")
    assert [s.session_id for s in listed] == ["p"]
    await store.fork_session("p", "p__sub__billing__abcd1234", header=_header("p__sub__billing__abcd1234", owner="u1"))
    snap = await store.load_session("p__sub__billing__abcd1234")
    assert len(snap.entries) == 1


@pytest.mark.asyncio
async def test_sqlite_fork_and_owner(tmp_path):
    store = SqliteStore(str(tmp_path / "s.db"))
    await store.create_session("p", _header("p", owner="u1"))
    await store.append_entry("p", MessageEntry(message={"role": "user", "text": "x"}, id="e1"))
    await store.fork_session("p", "c", header=_header("c", owner="u1"))
    listed = await store.list_sessions(owner="u1")
    assert {s.session_id for s in listed} == {"p", "c"}
    snap = await store.load_session("c")
    assert len(snap.entries) == 1
