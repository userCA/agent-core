"""Tests for ScopedKnowledgeBase and knowledge root resolution helpers."""

from __future__ import annotations

import os

from agent_core.knowledge.composite import CompositeKnowledgeBase
from agent_core.knowledge.local_kb import (
    ScopedKnowledgeBase,
    knowledge_agent_dir,
    knowledge_shared_dir,
)
from agent_core.retrieval.adapters.inmemory import InMemoryRetriever
from agent_core.retrieval.base import Query, RetrievedChunk


def _make_retriever() -> InMemoryRetriever:
    r = InMemoryRetriever()
    r.add("faq answer", source="faq/0")
    r.add("guide text", source="guide/0")
    return r


async def test_filters_chunks_to_allowed_doc_names():
    scoped = ScopedKnowledgeBase(_make_retriever(), scope="shared", doc_names={"faq"})

    chunks = await scoped.retrieve(Query(text="faq answer guide", top_k=10))

    assert [c.source for c in chunks] == ["shared/faq/0"]
    assert all("guide" not in (c.source or "") for c in chunks)


async def test_none_doc_names_allows_all():
    scoped = ScopedKnowledgeBase(_make_retriever(), scope="shared", doc_names=None)

    chunks = await scoped.retrieve(Query(text="faq answer guide", top_k=10))

    assert {c.source for c in chunks} == {"shared/faq/0", "shared/guide/0"}


async def test_sources_prefixed_with_scope():
    scoped = ScopedKnowledgeBase(_make_retriever(), scope="agents/a", doc_names={"faq"})

    chunks = await scoped.retrieve(Query(text="faq answer", top_k=10))

    assert [c.source for c in chunks] == ["agents/a/faq/0"]


async def test_none_source_passes_through_unchanged():
    r = InMemoryRetriever()
    r.add("no source text", source=None)
    scoped = ScopedKnowledgeBase(r, scope="agents/a", doc_names=None)

    chunks = await scoped.retrieve(Query(text="no source text", top_k=10))

    assert len(chunks) == 1
    assert chunks[0].source is None
    assert chunks[0].text == "no source text"


async def test_composite_with_scoped_retrievers_only_returns_declared_chunks():
    shared = InMemoryRetriever()
    shared.add("alpha secret", source="alpha/0")  # declared by agent a
    shared.add("beta secret", source="beta/0")    # NOT declared by agent a
    private_a = InMemoryRetriever()
    private_a.add("gamma private", source="gamma/0")

    kb = CompositeKnowledgeBase([
        ScopedKnowledgeBase(shared, scope="shared", doc_names={"alpha"}),
        ScopedKnowledgeBase(private_a, scope="agents/a", doc_names={"gamma"}),
    ])

    chunks = await kb.retrieve(Query(text="alpha beta gamma secret private", top_k=10))

    sources = {c.source for c in chunks}
    assert "shared/alpha/0" in sources
    assert "agents/a/gamma/0" in sources
    assert "shared/beta/0" not in sources


def test_knowledge_shared_dir_prefers_shared_subdir(tmp_path):
    base = os.path.join(str(tmp_path), ".pi", "knowledge")
    os.makedirs(os.path.join(base, "shared"), exist_ok=True)

    assert knowledge_shared_dir(str(tmp_path)) == os.path.join(base, "shared")


def test_knowledge_shared_dir_prefers_shared_even_with_flat_docs(tmp_path):
    base = os.path.join(str(tmp_path), ".pi", "knowledge")
    os.makedirs(os.path.join(base, "shared"), exist_ok=True)
    doc = os.path.join(base, "faq")
    os.makedirs(doc, exist_ok=True)
    with open(os.path.join(doc, "meta.json"), "w", encoding="utf-8") as f:
        f.write("{}")

    assert knowledge_shared_dir(str(tmp_path)) == os.path.join(base, "shared")


def test_knowledge_shared_dir_falls_back_to_flat_layout(tmp_path):
    base = os.path.join(str(tmp_path), ".pi", "knowledge")
    doc = os.path.join(base, "faq")
    os.makedirs(doc, exist_ok=True)
    with open(os.path.join(doc, "meta.json"), "w", encoding="utf-8") as f:
        f.write("{}")

    assert knowledge_shared_dir(str(tmp_path)) == base


def test_knowledge_shared_dir_with_neither_returns_shared(tmp_path):
    base = os.path.join(str(tmp_path), ".pi", "knowledge")
    # No shared/ subdir and no flat doc dirs → still resolves to shared path.
    assert knowledge_shared_dir(str(tmp_path)) == os.path.join(base, "shared")


def test_knowledge_agent_dir(tmp_path):
    expected = os.path.join(str(tmp_path), ".pi", "knowledge", "agents", "a1")
    assert knowledge_agent_dir("a1", str(tmp_path)) == expected
