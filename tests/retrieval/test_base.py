from agent_core.retrieval.base import Query, RetrievedChunk, Retriever


def test_query_defaults():
    q = Query(text="hello")
    assert q.text == "hello"
    assert q.top_k == 5
    assert q.filters == {}


def test_retrieved_chunk_fields():
    c = RetrievedChunk(text="doc body", score=0.83, source="doc-1", metadata={"page": 2})
    assert c.text == "doc body"
    assert c.score == 0.83
    assert c.source == "doc-1"
    assert c.metadata == {"page": 2}


def test_retriever_is_protocol():
    class Dummy:
        async def retrieve(self, query):
            return []
    r: Retriever = Dummy()
    assert hasattr(r, "retrieve")
