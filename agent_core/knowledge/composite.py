"""Composite knowledge base — merge retrieval from multiple roots.

Sequentially queries every configured retriever (e.g. shared + private
knowledge bases) and merges the results by relevance score, deduping by
source so a chunk surfaced by more than one root appears once.
"""

from __future__ import annotations

from agent_core.retrieval.base import Query, RetrievedChunk, Retriever


class CompositeKnowledgeBase:
    """Sequentially retrieve from multiple retrievers and merge by relevance score."""

    def __init__(self, retrievers: list[Retriever]) -> None:
        self._retrievers = list(retrievers)

    async def retrieve(self, query: Query) -> list[RetrievedChunk]:
        collected: list[tuple[int, int, RetrievedChunk]] = []
        for r_idx, retriever in enumerate(self._retrievers):
            for c_idx, chunk in enumerate(await retriever.retrieve(query)):
                collected.append((r_idx, c_idx, chunk))

        # Dedupe by source — keep the highest-scoring chunk for a given
        # source, anchored at its first occurrence. Chunks without a source
        # are never deduped away.
        best: dict[str, int] = {}
        deduped: list[tuple[int, int, RetrievedChunk]] = []
        for r_idx, c_idx, chunk in collected:
            if chunk.source is not None and chunk.source in best:
                pos = best[chunk.source]
                if chunk.score > deduped[pos][2].score:
                    deduped[pos] = (r_idx, c_idx, chunk)
                continue
            if chunk.source is not None:
                best[chunk.source] = len(deduped)
            deduped.append((r_idx, c_idx, chunk))

        # Score descending; equal scores keep original retrieval order.
        deduped.sort(key=lambda item: (-item[2].score, item[0], item[1]))
        return [chunk for _, _, chunk in deduped[: query.top_k]]
