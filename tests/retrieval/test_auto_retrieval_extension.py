from agent_core.retrieval.adapters.inmemory import InMemoryRetriever
from agent_core.retrieval.extension import AutoRetrievalExtension


async def test_injects_chunks_before_user_message():
    r = InMemoryRetriever()
    r.add("Python uses GIL for threading", source="d1")
    ext = AutoRetrievalExtension(retriever=r, top_k=2)

    out = await ext.transform_context([{"role": "user", "content": "Tell me about Python threading"}], signal=None)

    assert len(out) == 2
    assert out[0]["role"] == "system"
    assert "Python uses GIL" in out[0]["content"]


async def test_noop_when_no_user_message():
    r = InMemoryRetriever()
    r.add("doc", source="d1")
    ext = AutoRetrievalExtension(retriever=r)
    out = await ext.transform_context([{"role": "assistant", "content": "hi"}], signal=None)
    assert out == [{"role": "assistant", "content": "hi"}]


async def test_noop_when_no_chunks_match():
    ext = AutoRetrievalExtension(retriever=InMemoryRetriever())
    msgs = [{"role": "user", "content": "anything"}]
    out = await ext.transform_context(msgs, signal=None)
    assert out == msgs
