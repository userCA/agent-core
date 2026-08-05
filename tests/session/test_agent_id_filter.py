"""SessionStore filtering by agent_id (Task 1.2)."""

from __future__ import annotations

import pytest

from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.jsonl_store import JsonlStore
from agent_core.session.sqlite_store import SqliteStore
from agent_core.session.store import SessionHeader, SessionStore


def _header(sid: str, owner: str = "", agent_id: str = "") -> SessionHeader:
    return SessionHeader(id=sid, timestamp="t", cwd="/tmp", owner=owner, agent_id=agent_id)


def _old_header(sid: str, owner: str = "") -> SessionHeader:
    # Constructed without agent_id to simulate a pre-agent_id session.
    return SessionHeader(id=sid, timestamp="t", cwd="/tmp", owner=owner)


@pytest.fixture(params=["inmemory", "jsonl", "sqlite"])
async def store(request: pytest.FixtureRequest, tmp_path) -> SessionStore:
    backend = request.param
    if backend == "inmemory":
        s: SessionStore = InMemoryStore()
    elif backend == "jsonl":
        s = JsonlStore(str(tmp_path))
    else:
        s = SqliteStore(str(tmp_path / "sessions.db"))
    yield s
    await s.close()


async def test_list_sessions_filters_by_agent_id(store):
    await store.create_session("s1", _header("s1", owner="u1", agent_id="support"))
    await store.create_session("s2", _header("s2", owner="u1", agent_id="analyst"))
    metas = await store.list_sessions(owner="u1", agent_id="support")
    assert [m.session_id for m in metas] == ["s1"]
    assert metas[0].agent_id == "support"


async def test_list_sessions_agent_id_none_returns_all_owner_sessions(store):
    await store.create_session("s1", _header("s1", owner="u1", agent_id="support"))
    await store.create_session("s2", _header("s2", owner="u1", agent_id="analyst"))
    metas = await store.list_sessions(owner="u1", agent_id=None)
    assert {m.session_id for m in metas} == {"s1", "s2"}
    # Omitting agent_id entirely behaves the same (backward compatible).
    metas2 = await store.list_sessions(owner="u1")
    assert {m.session_id for m in metas2} == {"s1", "s2"}


async def test_list_sessions_cross_filters_owner_and_agent(store):
    await store.create_session("u1s", _header("u1s", owner="u1", agent_id="support"))
    await store.create_session("u1a", _header("u1a", owner="u1", agent_id="analyst"))
    await store.create_session("u2s", _header("u2s", owner="u2", agent_id="support"))
    metas = await store.list_sessions(owner="u1", agent_id="support")
    assert [m.session_id for m in metas] == ["u1s"]


async def test_old_session_without_agent_id_defaults_to_empty(store):
    await store.create_session("old", _old_header("old", owner="u1"))
    await store.create_session("new", _header("new", owner="u1", agent_id="support"))
    # Explicit agent_id filter does NOT match the empty-defaulted old session.
    metas = await store.list_sessions(owner="u1", agent_id="support")
    assert [m.session_id for m in metas] == ["new"]
    # No filter returns both.
    all_metas = await store.list_sessions(owner="u1")
    assert {m.session_id for m in all_metas} == {"old", "new"}
    # Header round-trips with agent_id == "".
    snap = await store.load_session("old")
    assert snap.header.agent_id == ""


async def test_session_meta_agent_id_populated(store):
    await store.create_session("s1", _header("s1", owner="u1", agent_id="analyst"))
    metas = await store.list_sessions(owner="u1")
    assert metas[0].agent_id == "analyst"


async def test_jsonl_agent_id_survives_reopen(tmp_path):
    store = JsonlStore(str(tmp_path))
    await store.create_session("s1", _header("s1", owner="u1", agent_id="support"))
    await store.close()

    store2 = JsonlStore(str(tmp_path))
    metas = await store2.list_sessions(owner="u1", agent_id="support")
    assert [m.session_id for m in metas] == ["s1"]
    assert metas[0].agent_id == "support"
    snap = await store2.load_session("s1")
    assert snap.header.agent_id == "support"
    await store2.close()
