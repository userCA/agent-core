"""Retriever Protocol and data types for RAG."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class Query(BaseModel):
    text: str
    top_k: int = 5
    filters: dict[str, Any] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    text: str
    score: float
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class Retriever(Protocol):
    async def retrieve(self, query: Query) -> list[RetrievedChunk]: ...
