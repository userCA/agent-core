from agent_core.memory.adapters.inmemory import InMemoryMemoryStore
from agent_core.memory.base import MemoryRecord


async def test_remember_then_recall_same_session():
    store = InMemoryMemoryStore()
    await store.remember(session_id="s1", text="User loves Go")
    await store.remember(session_id="s1", text="Prefers terse answers")
    recs = await store.recall(session_id="s1", query="language preference", limit=10)
    assert len(recs) == 2
    assert {r.text for r in recs} == {"User loves Go", "Prefers terse answers"}


async def test_recall_is_session_scoped():
    store = InMemoryMemoryStore()
    await store.remember(session_id="s1", text="secret-1")
    await store.remember(session_id="s2", text="secret-2")
    recs = await store.recall(session_id="s1", query="any", limit=10)
    assert [r.text for r in recs] == ["secret-1"]


async def test_recall_respects_limit():
    store = InMemoryMemoryStore()
    for i in range(5):
        await store.remember(session_id="s1", text=f"fact {i}")
    recs = await store.recall(session_id="s1", query="any", limit=2)
    assert len(recs) == 2


async def test_forget_session_removes_records():
    store = InMemoryMemoryStore()
    await store.remember(session_id="s1", text="t")
    await store.forget(session_id="s1")
    assert await store.recall(session_id="s1", query="any", limit=10) == []


async def test_recall_ranks_by_query_overlap():
    store = InMemoryMemoryStore()
    await store.remember(session_id="s1", text="Cats are mammals")
    await store.remember(session_id="s1", text="Python is a programming language")
    recs = await store.recall(session_id="s1", query="python language", limit=1)
    assert recs[0].text == "Python is a programming language"
