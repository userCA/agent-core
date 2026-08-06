"""Scene-level tests: ChatAssistant assembles a per-agent knowledge base.

Agents declare shared/private KB doc names; ChatAssistant must scope the
local KB roots per agent (shared + private), and expose the search_knowledge
tool only when an agent actually has KB docs. Uses the same stub/create
approach as test_agent_mcp_wiring.py — no real LLM or embeddings.
"""

from __future__ import annotations

import pytest

from agent_core.knowledge.composite import CompositeKnowledgeBase
from agent_core.knowledge.local_kb import ScopedKnowledgeBase
from agent_core.resources.agents import AgentDefinition, AgentKnowledge
from agent_core.retrieval.adapters.inmemory import InMemoryRetriever
from agent_core.retrieval.base import Query
from agent_core.session.inmemory_store import InMemoryStore
from scene.http_sse.chat_assistant import ChatAssistant, build_agent_knowledge_base


async def test_agent_composites_do_not_leak_private_docs():
    # Plan acceptance V5: Agent A's composite (shared-all + private "agents/a")
    # must never surface Agent B's private docs, and vice versa.
    shared = InMemoryRetriever()
    shared.add("alpha shared", source="alpha/0")
    private_a = InMemoryRetriever()
    private_a.add("secret_a", source="secret_a/0")
    private_b = InMemoryRetriever()
    private_b.add("secret_b", source="secret_b/0")

    agent_a = CompositeKnowledgeBase([
        ScopedKnowledgeBase(shared, scope="shared", doc_names=None),
        ScopedKnowledgeBase(private_a, scope="agents/a", doc_names={"secret_a"}),
    ])
    agent_b = CompositeKnowledgeBase([
        ScopedKnowledgeBase(shared, scope="shared", doc_names=None),
        ScopedKnowledgeBase(private_b, scope="agents/b", doc_names={"secret_b"}),
    ])

    chunks_a = await agent_a.retrieve(Query(text="alpha secret_a secret_b", top_k=10))
    sources_a = {c.source for c in chunks_a}
    assert "shared/alpha/0" in sources_a
    assert "agents/a/secret_a/0" in sources_a
    assert "agents/b/secret_b/0" not in sources_a

    chunks_b = await agent_b.retrieve(Query(text="alpha secret_a secret_b", top_k=10))
    sources_b = {c.source for c in chunks_b}
    assert "shared/alpha/0" in sources_b
    assert "agents/b/secret_b/0" in sources_b
    assert "agents/a/secret_a/0" not in sources_b


def _agent(aid: str, knowledge: AgentKnowledge | None) -> AgentDefinition:
    return AgentDefinition(
        id=aid,
        name=aid.upper(),
        description="",
        system_prompt=f"You are {aid}",
        knowledge=knowledge,
    )


def test_build_agent_knowledge_base_none_for_empty_knowledge():
    kb = build_agent_knowledge_base(_agent("a", AgentKnowledge()), cwd="/tmp")
    assert kb is None


def test_build_agent_knowledge_base_composite_for_missing_block(tmp_path):
    kb = build_agent_knowledge_base(_agent("a", None), cwd=str(tmp_path))
    assert isinstance(kb, CompositeKnowledgeBase)


def test_build_agent_knowledge_base_composite_for_shared_private(tmp_path):
    kb = build_agent_knowledge_base(
        _agent("a", AgentKnowledge(shared=["x"], private=["y"])),
        cwd=str(tmp_path),
    )
    assert isinstance(kb, CompositeKnowledgeBase)


@pytest.mark.asyncio
async def test_agent_with_kb_registers_search_knowledge_tool(tmp_path):
    cwd = str(tmp_path)
    agent = _agent("a", AgentKnowledge(shared=["x"]))
    assistant = await ChatAssistant.create(
        session_store=InMemoryStore(),
        session_id="sa",
        cwd=cwd,
        agent=agent,
        owner="u1",
        enable_multi_agent=False,
    )
    try:
        assert "search_knowledge" in assistant.tool_names
    finally:
        await assistant.dispose()


@pytest.mark.asyncio
async def test_agent_with_empty_kb_does_not_register_kb_tool(tmp_path):
    cwd = str(tmp_path)
    agent = _agent("a", AgentKnowledge())
    assistant = await ChatAssistant.create(
        session_store=InMemoryStore(),
        session_id="sa",
        cwd=cwd,
        agent=agent,
        owner="u1",
        enable_multi_agent=False,
    )
    try:
        assert "search_knowledge" not in assistant.tool_names
    finally:
        await assistant.dispose()


@pytest.mark.asyncio
async def test_agent_with_private_kb_registers_search_knowledge_tool(tmp_path):
    cwd = str(tmp_path)
    agent = _agent("a", AgentKnowledge(private=["p"]))
    assistant = await ChatAssistant.create(
        session_store=InMemoryStore(),
        session_id="sa",
        cwd=cwd,
        agent=agent,
        owner="u1",
        enable_multi_agent=False,
    )
    try:
        assert "search_knowledge" in assistant.tool_names
    finally:
        await assistant.dispose()
