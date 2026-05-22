from agent_core.retrieval.adapters.inmemory import InMemoryRetriever
from agent_core.retrieval.base import Query, RetrievedChunk


async def test_returns_top_k_by_keyword_overlap():
    r = InMemoryRetriever()
    r.add("Python is a programming language", source="d1")
    r.add("Cats are mammals", source="d2")
    r.add("Python snakes live in Asia", source="d3")

    chunks = await r.retrieve(Query(text="python language", top_k=2))

    assert len(chunks) == 2
    assert chunks[0].source == "d1"
    assert all(isinstance(c, RetrievedChunk) for c in chunks)
    assert chunks[0].score >= chunks[1].score


async def test_returns_empty_when_no_overlap():
    r = InMemoryRetriever()
    r.add("Cats are mammals", source="d1")
    chunks = await r.retrieve(Query(text="quantum physics", top_k=5))
    assert chunks == []


async def test_filter_by_metadata():
    r = InMemoryRetriever()
    r.add("Python guide", source="d1", metadata={"lang": "en"})
    r.add("Python 教程", source="d2", metadata={"lang": "zh"})
    chunks = await r.retrieve(Query(text="python", top_k=5, filters={"lang": "zh"}))
    assert len(chunks) == 1
    assert chunks[0].source == "d2"
