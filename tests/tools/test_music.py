"""Tests for TextToMusicTool."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_core.core.content import TextContent
from agent_core.tools.base import ToolContext, ToolResult
from agent_core.tools.music import TextToMusicTool, POLL_MAX_ATTEMPTS


@pytest.fixture
def tool():
    return TextToMusicTool(api_url="http://test/create", query_url="http://test/query")


@pytest.fixture
def tool_ctx():
    return ToolContext(signal=asyncio.Event())


@pytest.mark.asyncio
async def test_definition_has_required_params(tool):
    d = tool.definition
    assert d.name == "text_to_music"
    assert "prompt" in d.parameters["properties"]
    assert d.parameters["required"] == ["prompt"]


@pytest.mark.asyncio
async def test_returns_display_audio_on_success(tool, tool_ctx):
    """Successful music generation should include display.audio."""
    create_data = {"taskId": "task-123"}
    query_data = {"taskId": "task-123", "status": "SUCCESS", "output": [{"url": "http://example.com/1.mp3"}]}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        create_resp = MagicMock()
        create_resp.json.return_value = create_data
        create_resp.raise_for_status = MagicMock()

        query_resp = MagicMock()
        query_resp.json.return_value = query_data
        query_resp.raise_for_status = MagicMock()

        mock_client.post = AsyncMock(return_value=create_resp)
        mock_client.get = AsyncMock(return_value=query_resp)

        result = await tool.execute("tc1", {"prompt": "test music"}, tool_ctx)

        assert result.display is not None
        assert result.display["audio"]["urls"] == ["http://example.com/1.mp3"]
        assert result.display["audio"]["task_id"] == "task-123"
        assert result.display["audio"]["prompt"] == "test music"
        assert "音乐生成完成" in result.content[0].text


@pytest.mark.asyncio
async def test_no_display_on_create_failure(tool, tool_ctx):
    """Failed task creation should not include display."""
    create_data = {"error": "invalid"}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        create_resp = MagicMock()
        create_resp.json.return_value = create_data
        create_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=create_resp)

        result = await tool.execute("tc1", {"prompt": "test"}, tool_ctx)

        assert result.display is None
        assert "创建任务失败" in result.content[0].text


@pytest.mark.asyncio
async def test_no_display_on_poll_timeout(tool, tool_ctx):
    """Polling timeout should not include display."""
    create_data = {"taskId": "task-123"}
    processing_data = {"taskId": "task-123", "status": "PROCESSING"}

    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return processing_data

    with patch("httpx.AsyncClient") as mock_client_cls, patch("asyncio.sleep") as mock_sleep:
        mock_client = MagicMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        create_resp = MagicMock()
        create_resp.json.return_value = create_data
        create_resp.raise_for_status = MagicMock()

        mock_client.post = AsyncMock(return_value=create_resp)
        mock_client.get = AsyncMock(return_value=FakeResp())
        mock_sleep.return_value = None  # skip actual sleeps

        result = await tool.execute("tc1", {"prompt": "test"}, tool_ctx)

        assert result.display is None
        assert "轮询超时" in result.content[0].text


@pytest.mark.asyncio
async def test_style_combined_into_prompt(tool, tool_ctx):
    """Style parameter should be prepended to prompt."""
    with patch("httpx.AsyncClient") as mock_client_cls, patch("asyncio.sleep") as mock_sleep:
        mock_client = MagicMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        create_resp = MagicMock()
        create_resp.json.return_value = {"taskId": "task-1"}
        create_resp.raise_for_status = MagicMock()

        captured_payload = {}

        async def capture_post(url, headers, json):
            captured_payload["prompt"] = json["inputModel"]["contents"][0]["content"]
            return create_resp

        mock_client.post = capture_post

        # Poll returns failure to stop quickly
        fail_resp = MagicMock()
        fail_resp.json.return_value = {"status": "FAILED"}
        fail_resp.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=fail_resp)
        mock_sleep.return_value = None

        await tool.execute("tc1", {"prompt": "happy song", "style": "pop"}, tool_ctx)
        assert "[pop] happy song" in captured_payload["prompt"]


@pytest.mark.asyncio
async def test_abort_during_polling(tool, tool_ctx):
    """Setting the signal should abort polling gracefully."""
    create_data = {"taskId": "task-123"}
    tool_ctx.signal.set()

    with patch("httpx.AsyncClient") as mock_client_cls, patch("asyncio.sleep") as mock_sleep:
        mock_client = MagicMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        create_resp = MagicMock()
        create_resp.json.return_value = create_data
        create_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=create_resp)
        mock_sleep.return_value = None

        result = await tool.execute("tc1", {"prompt": "test"}, tool_ctx)

        assert "已取消" in result.content[0].text
        assert result.display is None


@pytest.mark.asyncio
async def test_backoff_intervals():
    """Verify exponential backoff progression."""
    from agent_core.tools.music import POLL_INTERVAL_INITIAL, POLL_INTERVAL_MAX, POLL_BACKOFF

    interval = POLL_INTERVAL_INITIAL
    intervals = []
    for _ in range(POLL_MAX_ATTEMPTS - 1):
        intervals.append(interval)
        interval = min(interval * POLL_BACKOFF, POLL_INTERVAL_MAX)

    # First interval should be initial value
    assert intervals[0] == POLL_INTERVAL_INITIAL
    # Should reach max eventually
    assert intervals[-1] == POLL_INTERVAL_MAX
    # Should be non-decreasing
    for i in range(1, len(intervals)):
        assert intervals[i] >= intervals[i - 1]


def test_sse_wire_through_audio_display():
    """ToolExecutionEnd with display.audio → SSE JSON includes display."""
    from scene.http_sse.events import agent_event_to_sse_json
    from agent_core.core.events import ToolExecutionEnd

    result = ToolResult(
        content=[TextContent(text="done")],
        display={"audio": {"urls": ["http://ex.com/1.mp3"], "task_id": "t1", "prompt": "test"}},
    )
    evt = ToolExecutionEnd(
        tool_call_id="tc1", tool_name="text_to_music", result=result, is_error=False
    )
    output = agent_event_to_sse_json(evt)
    assert "display" in output
    assert output["display"]["audio"]["urls"] == ["http://ex.com/1.mp3"]
