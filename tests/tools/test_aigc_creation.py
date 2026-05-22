"""Tests for AigcCreationTool."""

from __future__ import annotations

import asyncio
import os
from typing import Any
from unittest.mock import patch

import pytest
import respx
from httpx import Response

from agent_core.core.content import TextContent
from agent_core.core.human_input import RequiresHumanInput
from agent_core.core.tool_runner import _run_single_tool
from agent_core.tools.aigc_creation import (
    AigcAuth,
    AigcCreationTool,
    AigcToolConfig,
    create_nolo_video_tool,
)
from agent_core.tools.base import ToolContext, ToolDefinition, ToolRegistry, ToolResult


# ---------------------------------------------------------------------------
# Auth resolution
# ---------------------------------------------------------------------------

def test_resolve_auth_priority():
    """Metadata > constructor > env > default."""
    tool = AigcCreationTool(
        name="test",
        description="test",
        parameters={"type": "object", "properties": {}},
        scene="test",
        content_type="video",
        config=AigcToolConfig(auth=AigcAuth(channel="ctor_ch", pacmtoken="ctor_token")),
    )

    # metadata wins
    headers, cookies = tool._resolve_auth(
        {"aigc_auth": {"channel": "meta_ch", "pacmtoken": "meta_token"}}
    )
    assert headers["channel"] == "meta_ch"
    assert headers["content-type"] == "application/json"
    assert cookies["pacmtoken"] == "meta_token"

    # constructor wins when no metadata
    headers, cookies = tool._resolve_auth({})
    assert headers["channel"] == "ctor_ch"
    assert cookies["pacmtoken"] == "ctor_token"

    # env wins when no metadata/constructor
    with patch.dict(os.environ, {"MIGU_CHANNEL": "env_ch", "MIGU_PACM_TOKEN": "env_token"}):
        tool2 = AigcCreationTool(
            name="test",
            description="test",
            parameters={"type": "object", "properties": {}},
            scene="test",
            content_type="video",
        )
        headers, cookies = tool2._resolve_auth({})
        assert headers["channel"] == "env_ch"
        assert cookies["pacmtoken"] == "env_token"


# ---------------------------------------------------------------------------
# HITL
# ---------------------------------------------------------------------------

def test_hitl_when_params_missing():
    """Missing required params with a HITL builder raises RequiresHumanInput."""
    tool = create_nolo_video_tool()
    ctx = ToolContext(signal=asyncio.Event())

    with pytest.raises(RequiresHumanInput) as exc_info:
        asyncio.run(tool.execute("tc1", {}, ctx))

    assert "补充" in exc_info.value.prompt
    schema = exc_info.value.input_schema
    assert schema["type"] == "template_form"
    field_names = {f["name"] for f in schema["fields"]}
    assert "templateId" in field_names
    assert "input_images" in field_names


def test_no_hitl_when_builder_none():
    """Missing required params without HITL builder returns error result."""
    tool = AigcCreationTool(
        name="no_hitl",
        description="test",
        parameters={
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["x"],
        },
        scene="test",
        content_type="video",
    )
    ctx = ToolContext(signal=asyncio.Event())
    result = asyncio.run(tool.execute("tc1", {}, ctx))
    assert result.content[0].text == "缺少必需参数: x"


# ---------------------------------------------------------------------------
# Payload building
# ---------------------------------------------------------------------------

def test_build_payload():
    tool = create_nolo_video_tool()
    payload = tool._build_payload(
        {"templateId": "999", "aiTemplateName": "测试模板", "input_images": ["img1", "img2"]},
    )

    # Core fields
    assert payload["scene"] == "nolo"
    assert payload["aigcContentResultInput"]["contentType"] == "video"
    assert "ext" not in payload
    assert "taskSessionId" not in payload

    # inputContent — params directly mapped into inputMeta
    input_meta = payload["inputContent"]["inputMeta"]
    assert input_meta["templateId"] == "999"
    assert input_meta["aiTemplateName"] == "测试模板"

    content_list = payload["inputContent"]["aigcInputContentList"]
    assert len(content_list) == 2
    assert content_list[0]["picFileId"] == "img1"


# ---------------------------------------------------------------------------
# HTTP execution (mocked)
# ---------------------------------------------------------------------------

@respx.mock
async def _test_execute_success():
    tool = create_nolo_video_tool()
    ctx = ToolContext(signal=asyncio.Event())

    create_url = "http://app.c.vip.migu.cn/user/h5/ai-gc/create/v1.0"
    query_url = "http://app.c.vip.migu.cn/user/h5/ai-gc/query/v1.0"
    tool._api_url = create_url
    tool._query_url = query_url
    tool._poll_interval = 0.01
    tool._poll_max_attempts = 5

    # Mock create endpoint
    respx.post(create_url).mock(return_value=Response(200, json={"taskId": "task_123"}))

    # Mock query endpoint – first processing, then success
    query_route = respx.get(query_url)
    query_route.side_effect = [
        Response(200, json={"status": "PROCESSING"}),
        Response(200, json={"status": "SUCCESS", "data": {"url": "http://result.mp4"}}),
    ]

    result = await tool.execute(
        "tc1",
        {"templateId": "426", "aiTemplateName": "时光温柔", "input_images": ["img1"]},
        ctx,
    )
    text = result.content[0].text
    assert "完成" in text
    assert "task_123" in text
    assert "http://result.mp4" in text


def test_execute_success():
    asyncio.run(_test_execute_success())


@respx.mock
async def _test_execute_poll_timeout():
    tool = create_nolo_video_tool()
    ctx = ToolContext(signal=asyncio.Event())

    create_url = "http://app.c.vip.migu.cn/user/h5/ai-gc/create/v1.0"
    query_url = "http://app.c.vip.migu.cn/user/h5/ai-gc/query/v1.0"
    tool._api_url = create_url
    tool._query_url = query_url
    tool._poll_interval = 0.01
    tool._poll_max_attempts = 2

    respx.post(create_url).mock(return_value=Response(200, json={"taskId": "task_456"}))
    respx.get(query_url).mock(return_value=Response(200, json={"status": "PENDING"}))

    result = await tool.execute(
        "tc1",
        {"templateId": "426", "input_images": ["img1"]},
        ctx,
    )
    assert "超时" in result.content[0].text
    assert "task_456" in result.content[0].text


def test_execute_poll_timeout():
    asyncio.run(_test_execute_poll_timeout())


@respx.mock
async def _test_execute_api_error():
    tool = create_nolo_video_tool()
    ctx = ToolContext(signal=asyncio.Event())

    create_url = "http://app.c.vip.migu.cn/user/h5/ai-gc/create/v1.0"
    tool._api_url = create_url

    respx.post(create_url).mock(return_value=Response(500, text="Internal Server Error"))

    result = await tool.execute(
        "tc1",
        {"templateId": "426", "input_images": ["img1"]},
        ctx,
    )
    assert "500" in result.content[0].text
    # ToolResult carries error info in details; is_error is a runner-side flag


def test_execute_api_error():
    asyncio.run(_test_execute_api_error())


# ---------------------------------------------------------------------------
# Tool runner inject_metadata integration
# ---------------------------------------------------------------------------

class _MetadataEchoTool:
    definition = ToolDefinition(
        name="echo_meta",
        description="echo",
        parameters={"type": "object", "properties": {}},
    )

    async def execute(self, tool_call_id, params, ctx: ToolContext) -> ToolResult:
        return ToolResult(content=[TextContent(text=str(ctx.metadata))])


async def _test_inject_metadata():
    registry = ToolRegistry()
    registry.register(_MetadataEchoTool())

    async def before_hook(info):
        return {"inject_metadata": {"aigc_auth": {"uid": "42"}}}

    class FakeToolCall:
        id = "tc1"
        name = "echo_meta"
        arguments = {}

    _, result, is_error = await _run_single_tool(
        FakeToolCall(), registry, before_hook, None, None, None
    )
    assert is_error is False
    assert "aigc_auth" in result.content[0].text
    assert "42" in result.content[0].text


def test_inject_metadata():
    asyncio.run(_test_inject_metadata())


# ---------------------------------------------------------------------------
# Session chained hooks (high-level smoke)
# ---------------------------------------------------------------------------

def test_session_chains_extension_hooks():
    """AgentSession.start() wires Extension before_tool_call after scene hook."""
    from agent_core.extensions.base import Extension, ExtensionContext, ExtensionRunner
    from agent_core.session.session import AgentSession
    from agent_core.core.agent import Agent
    from agent_core.core.state import AgentState
    from tests.conftest import FakeProvider, fake_model
    from agent_core.providers.auth import AuthSource

    calls = []

    class _SpyExt(Extension):
        name = "spy"

        async def on_before_tool_call(self, ctx: ExtensionContext, tool_call: Any) -> dict[str, Any] | None:
            calls.append("ext")
            return None

    provider = FakeProvider()
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(model=fake_model()),
    )

    async def scene_hook(info):
        calls.append("scene")
        return None

    agent._before_tool_call = scene_hook

    store = __import__("agent_core.session.inmemory_store", fromlist=["InMemoryStore"]).InMemoryStore()
    session = AgentSession(agent=agent, store=store, session_id="test-chain", extensions=[_SpyExt()])

    asyncio.run(session.start())

    # The chained hook should exist and call both
    assert agent._before_tool_call is not scene_hook  # replaced by chain
    asyncio.run(agent._before_tool_call({"tool_call": None, "args": {}}))
    assert calls == ["scene", "ext"]
