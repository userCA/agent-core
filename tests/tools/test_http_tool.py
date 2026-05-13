import httpx
import pytest
import respx

from agent_core.tools.base import ToolContext
from agent_core.tools.http_tool import BearerAuth, HttpTool


@respx.mock
async def test_http_tool_get():
    route = respx.get("https://api.example.com/users/1").mock(
        return_value=httpx.Response(200, json={"id": 1, "name": "Alice"})
    )

    tool = HttpTool(
        name="get_user",
        description="get user by id",
        method="GET",
        url="https://api.example.com/users/{id}",
        parameters={"type": "object", "properties": {"id": {"type": "integer"}}},
    )

    result = await tool.execute("c1", {"id": 1}, ToolContext(signal=None))

    assert route.called
    text = result.content[0].text
    assert "Alice" in text


@respx.mock
async def test_http_tool_post_with_template():
    route = respx.post("https://api.example.com/search").mock(
        return_value=httpx.Response(200, json={"results": ["a", "b"]})
    )

    tool = HttpTool(
        name="search",
        description="search",
        method="POST",
        url="https://api.example.com/search",
        parameters={"type": "object", "properties": {"q": {"type": "string"}}},
        request_template={"query": "{{q}}"},
        response_transform=lambda r: r["results"],
    )

    result = await tool.execute("c1", {"q": "hello"}, ToolContext(signal=None))

    assert route.called
    request = route.calls.last.request
    assert b'"query"' in request.content and b'"hello"' in request.content
    text = result.content[0].text
    assert "a" in text and "b" in text


@respx.mock
async def test_http_tool_bearer_auth():
    route = respx.get("https://api.example.com/data").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    tool = HttpTool(
        name="fetch",
        description="fetch",
        method="GET",
        url="https://api.example.com/data",
        parameters={},
        auth=BearerAuth(token="sk-test"),
    )

    result = await tool.execute("c1", {}, ToolContext(signal=None))

    assert route.called
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer sk-test"


@respx.mock
async def test_http_tool_error_raises():
    import httpx

    respx.get("https://api.example.com/fail").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    tool = HttpTool(
        name="fail",
        description="fail",
        method="GET",
        url="https://api.example.com/fail",
        parameters={},
    )

    with pytest.raises(httpx.HTTPStatusError):
        await tool.execute("c1", {}, ToolContext(signal=None))
