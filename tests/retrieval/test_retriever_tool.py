import asyncio

from agent_core.core.content import TextContent
from agent_core.retrieval.adapters.inmemory import InMemoryRetriever
from agent_core.retrieval.tool import RetrieverTool
from agent_core.tools.base import ToolContext


def _ctx() -> ToolContext:
    return ToolContext(signal=asyncio.Event(), on_update=None, metadata={}, mutation_queue=None)


async def test_tool_definition_shape():
    r = InMemoryRetriever()
    tool = RetrieverTool(retriever=r, name="search_kb", description="Search KB")
    assert tool.definition.name == "search_kb"
    assert "query" in tool.definition.parameters["properties"]
    assert tool.definition.parameters["required"] == ["query"]


async def test_tool_returns_chunks_as_text():
    r = InMemoryRetriever()
    r.add("Python is great", source="d1")
    tool = RetrieverTool(retriever=r)

    result = await tool.execute(tool_call_id="t1", params={"query": "python", "top_k": 1}, ctx=_ctx())

    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    assert "Python is great" in result.content[0].text
    assert "d1" in result.content[0].text


async def test_tool_empty_result_message():
    r = InMemoryRetriever()
    tool = RetrieverTool(retriever=r)
    result = await tool.execute(tool_call_id="t1", params={"query": "nothing"}, ctx=_ctx())
    assert "No matching" in result.content[0].text
