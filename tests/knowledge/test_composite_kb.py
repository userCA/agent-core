from agent_core.knowledge.composite import CompositeKnowledgeBase
from agent_core.retrieval.base import Query, RetrievedChunk, Retriever


class FakeRetriever:
    def __init__(self, chunks: list[RetrievedChunk]):
        self._chunks = chunks

    async def retrieve(self, query: Query) -> list[RetrievedChunk]:
        return list(self._chunks)


def _chunk(text: str, score: float, source: str | None = None) -> RetrievedChunk:
    return RetrievedChunk(text=text, score=score, source=source)


async def test_merges_across_retrievers_sorted_and_capped():
    r1 = FakeRetriever([
        _chunk("shared alpha", 0.4, source="shared/a"),
        _chunk("private beta", 0.9, source="private/b"),
    ])
    r2 = FakeRetriever([_chunk("shared gamma", 0.7, source="shared/g")])
    kb = CompositeKnowledgeBase([r1, r2])

    chunks = await kb.retrieve(Query(text="q", top_k=2))

    assert [c.source for c in chunks] == ["private/b", "shared/g"]
    assert all(isinstance(c, RetrievedChunk) for c in chunks)


async def test_dedupes_by_source_keeping_highest_score():
    r1 = FakeRetriever([_chunk("dup low", 0.3, source="doc/a")])
    r2 = FakeRetriever([
        _chunk("dup high", 0.9, source="doc/a"),
        _chunk("unique", 0.5, source="doc/b"),
    ])
    kb = CompositeKnowledgeBase([r1, r2])

    chunks = await kb.retrieve(Query(text="q", top_k=5))

    assert [c.source for c in chunks] == ["doc/a", "doc/b"]
    assert chunks[0].text == "dup high"


async def test_empty_retriever_contributes_nothing_and_empty_list_returns_empty():
    empty = CompositeKnowledgeBase([])
    assert await empty.retrieve(Query(text="q", top_k=5)) == []

    kb = CompositeKnowledgeBase([FakeRetriever([]), FakeRetriever([_chunk("x", 0.5, "s")])])
    chunks = await kb.retrieve(Query(text="q", top_k=5))
    assert [c.source for c in chunks] == ["s"]


async def test_equal_scores_keep_first_retriever_order():
    r1 = FakeRetriever([_chunk("first", 0.5, source="r1")])
    r2 = FakeRetriever([_chunk("second", 0.5, source="r2")])
    kb = CompositeKnowledgeBase([r1, r2])

    chunks = await kb.retrieve(Query(text="q", top_k=5))

    assert [c.source for c in chunks] == ["r1", "r2"]


async def test_honors_top_k_after_merge():
    r1 = FakeRetriever([_chunk("a", 0.3, "a"), _chunk("b", 0.2, "b")])
    r2 = FakeRetriever([_chunk("c", 0.4, "c"), _chunk("d", 0.1, "d")])
    kb = CompositeKnowledgeBase([r1, r2])

    chunks = await kb.retrieve(Query(text="q", top_k=2))

    assert [c.source for c in chunks] == ["c", "a"]


async def test_chunks_without_source_are_never_deduped_away():
    r1 = FakeRetriever([_chunk("no source", 0.5)])
    r2 = FakeRetriever([_chunk("no source again", 0.4)])
    kb = CompositeKnowledgeBase([r1, r2])

    chunks = await kb.retrieve(Query(text="q", top_k=5))

    assert len(chunks) == 2


def test_satisfies_retriever_protocol():
    kb = CompositeKnowledgeBase([FakeRetriever([])])
    assert isinstance(kb, Retriever)
