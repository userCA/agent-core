import time
from types import SimpleNamespace

from agent_core.core.content import TextContent
from agent_core.core.events import MessageEnd, TurnEnd
from agent_core.core.messages import UserMessage
from agent_core.memory.adapters.inmemory import InMemoryMemoryStore
from agent_core.memory.extension import MemoryExtension


def _ctx(session_id: str = "sess-1"):
    return SimpleNamespace(session_id=session_id, agent=None, store=None)


async def test_persists_user_message_after_turn_end():
    store = InMemoryMemoryStore()
    ext = MemoryExtension(store=store, session_id="sess-1")
    user = UserMessage(content=[TextContent(text="I prefer Go")], timestamp=time.time())

    await ext.on_event(_ctx(), MessageEnd(message=user))
    assert await store.recall(session_id="sess-1", query="x", limit=10) == []

    await ext.on_event(_ctx(), TurnEnd(message=SimpleNamespace(), tool_results=[]))
    recs = await store.recall(session_id="sess-1", query="x", limit=10)
    assert len(recs) == 1
    assert recs[0].text == "I prefer Go"


async def test_does_not_persist_non_user_messages():
    store = InMemoryMemoryStore()
    ext = MemoryExtension(store=store, session_id="sess-1")
    await ext.on_event(_ctx(), MessageEnd(message=SimpleNamespace(role="assistant", content=[])))
    await ext.on_event(_ctx(), TurnEnd(message=SimpleNamespace(), tool_results=[]))
    assert await store.recall(session_id="sess-1", query="x", limit=10) == []


async def test_transform_context_injects_recall():
    store = InMemoryMemoryStore()
    await store.remember(session_id="sess-1", text="User prefers Go")
    ext = MemoryExtension(store=store, session_id="sess-1", top_k=5)

    out = await ext.transform_context([{"role": "user", "content": "what language do I like"}], signal=None)

    assert len(out) == 2
    assert out[0]["role"] == "system"
    assert "User prefers Go" in out[0]["content"]


async def test_transform_context_noop_when_no_records():
    store = InMemoryMemoryStore()
    ext = MemoryExtension(store=store, session_id="sess-1")
    msgs = [{"role": "user", "content": "hi"}]
    out = await ext.transform_context(msgs, signal=None)
    assert out == msgs
