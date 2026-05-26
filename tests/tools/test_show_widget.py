"""Tests for ShowWidgetTool."""

from __future__ import annotations

import asyncio

import pytest

from agent_core.core.content import TextContent
from agent_core.core.events import ToolExecutionEnd
from agent_core.tools.base import ToolContext, ToolResult
from agent_core.tools.widgets import ShowWidgetTool
from agent_core.tools.widgets.spec import WIDGET_SPEC
from scene.http_sse.events import agent_event_to_sse_json


@pytest.fixture
def tool():
    return ShowWidgetTool()


@pytest.fixture
def tool_ctx():
    return ToolContext(signal=asyncio.Event())


@pytest.mark.asyncio
async def test_normal_render(tool, tool_ctx):
    result = await tool.execute("tc1", {"html": "<div>hi</div>"}, tool_ctx)
    assert result.display["widget"]["html"] == "<div>hi</div>"
    assert result.display["widget"]["version"] == 1


@pytest.mark.asyncio
async def test_forbidden_tag_body(tool, tool_ctx):
    with pytest.raises(ValueError, match="forbidden tag"):
        await tool.execute("tc1", {"html": "<body>hi</body>"}, tool_ctx)


@pytest.mark.asyncio
async def test_forbidden_tag_html(tool, tool_ctx):
    with pytest.raises(ValueError, match="forbidden tag"):
        await tool.execute("tc1", {"html": "<html><div>hi</div></html>"}, tool_ctx)


@pytest.mark.asyncio
async def test_forbidden_doctype(tool, tool_ctx):
    with pytest.raises(ValueError, match="forbidden tag"):
        await tool.execute("tc1", {"html": "<!DOCTYPE html><div>hi</div>"}, tool_ctx)


@pytest.mark.asyncio
async def test_size_limit(tool, tool_ctx):
    huge = "x" * (50 * 1024 + 1)
    with pytest.raises(ValueError, match="size exceeds"):
        await tool.execute("tc1", {"html": huge}, tool_ctx)


@pytest.mark.asyncio
async def test_placeholder_text(tool, tool_ctx):
    result = await tool.execute("tc1", {"html": "<div>hi</div>"}, tool_ctx)
    assert result.content[0].text.startswith("[widget rendered:")


@pytest.mark.asyncio
async def test_placeholder_text_with_title(tool, tool_ctx):
    result = await tool.execute(
        "tc1", {"html": "<div>hi</div>", "title": "My Chart"}, tool_ctx
    )
    assert "My Chart" in result.content[0].text


@pytest.mark.asyncio
async def test_height_clamp_max(tool, tool_ctx):
    result = await tool.execute(
        "tc1", {"html": "<div>hi</div>", "height": 2000}, tool_ctx
    )
    assert result.display["widget"]["height"] == 1200


@pytest.mark.asyncio
async def test_height_default_on_none(tool, tool_ctx):
    result = await tool.execute(
        "tc1", {"html": "<div>hi</div>", "height": None}, tool_ctx
    )
    assert result.display["widget"]["height"] == 400


@pytest.mark.asyncio
async def test_height_default_on_zero(tool, tool_ctx):
    result = await tool.execute(
        "tc1", {"html": "<div>hi</div>", "height": 0}, tool_ctx
    )
    assert result.display["widget"]["height"] == 400


@pytest.mark.asyncio
async def test_height_default_on_string(tool, tool_ctx):
    result = await tool.execute(
        "tc1", {"html": "<div>hi</div>", "height": "400"}, tool_ctx
    )
    assert result.display["widget"]["height"] == 400


@pytest.mark.asyncio
async def test_height_default_when_missing(tool, tool_ctx):
    result = await tool.execute("tc1", {"html": "<div>hi</div>"}, tool_ctx)
    assert result.display["widget"]["height"] == 400


def test_tool_definition_has_widget_spec(tool):
    assert WIDGET_SPEC in tool.definition.description
    assert tool.definition.prompt_snippet is None
    assert tool.definition.name == "show_widget"
    assert "html" in tool.definition.parameters["properties"]
    assert tool.definition.parameters["required"] == ["html"]


def test_sse_wire_through_success_path():
    """Successful ToolExecutionEnd with display.widget → SSE JSON includes display."""
    result = ToolResult(
        content=[TextContent(text="[widget rendered: test]")],
        display={"widget": {"version": 1, "html": "<div>hi</div>", "title": "test", "height": 400}},
    )
    evt = ToolExecutionEnd(
        tool_call_id="tc1", tool_name="show_widget", result=result, is_error=False
    )
    output = agent_event_to_sse_json(evt)
    assert "display" in output
    assert output["display"]["widget"]["html"] == "<div>hi</div>"


def test_sse_wire_through_error_path():
    """Error ToolExecutionEnd with no display → SSE JSON does NOT include display key."""
    result = ToolResult(content=[TextContent(text="something went wrong")])
    evt = ToolExecutionEnd(
        tool_call_id="tc1", tool_name="show_widget", result=result, is_error=True
    )
    output = agent_event_to_sse_json(evt)
    assert "display" not in output


def test_sse_no_pollution():
    """Ordinary tool_end (read_file) without display → no display key in SSE JSON."""
    result = ToolResult(
        content=[TextContent(text="ok")],
        display=None,
    )
    evt = ToolExecutionEnd(
        tool_call_id="tc1", tool_name="read_file", result=result, is_error=False
    )
    output = agent_event_to_sse_json(evt)
    assert "display" not in output
