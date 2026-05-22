"""In-memory keyword-overlap retriever for tests and small demos."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agent_core.retrieval.base import Query, RetrievedChunk

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text)}


@dataclass
class _Doc:
    text: str
    source: str | None
    metadata: dict[str, Any]
    tokens: set[str]


class InMemoryRetriever:
    def __init__(self) -> None:
        self._docs: list[_Doc] = []

    def add(self, text: str, *, source: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        self._docs.append(_Doc(text=text, source=source, metadata=metadata or {}, tokens=_tokenize(text)))

    async def retrieve(self, query: Query) -> list[RetrievedChunk]:
        q_tokens = _tokenize(query.text)
        if not q_tokens:
            return []
        scored: list[tuple[float, _Doc]] = []
        for doc in self._docs:
            if query.filters and not all(doc.metadata.get(k) == v for k, v in query.filters.items()):
                continue
            overlap = len(q_tokens & doc.tokens)
            if overlap == 0:
                continue
            scored.append((overlap / len(q_tokens), doc))
        scored.sort(key=lambda p: p[0], reverse=True)
        return [
            RetrievedChunk(text=doc.text, score=score, source=doc.source, metadata=dict(doc.metadata))
            for score, doc in scored[: query.top_k]
        ]
