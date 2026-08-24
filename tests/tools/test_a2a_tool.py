"""A2AAgentTool + config parsing / registration tests."""

from __future__ import annotations

import asyncio
import json

import pytest
import respx
from httpx import Response

from agent_core.core.content import TextContent
from agent_core.tools.a2a_tool import (
    A2AAgentConfig,
    A2AAgentTool,
    build_a2a_tools,
    load_a2a_agent_configs,
    parse_a2a_agents,
    register_a2a_tools,
)
from agent_core.tools.base import ToolContext, ToolRegistry

BASE = "http://a2a.test"


def _task(state: str, text: str = "answer") -> dict:
    return {
        "id": "t1",
        "status": {"state": state},
        "artifacts": [],
        "messages": [{"role": "agent", "parts": [{"type": "text", "text": text}]}],
    }


def _rpc_result(result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": "1", "result": result}


class _Handler:
    def __init__(self, *, final_state: str = "completed", auto_finish: bool = True) -> None:
        self.calls: list[str] = []
        self.state = "working"
        self.final_state = final_state
        self.get_count = 0
        self.auto_finish = auto_finish

    def __call__(self, request):
        body = json.loads(request.content)
        method = body["method"]
        self.calls.append(method)
        if method == "message/send":
            return Response(200, json=_rpc_result(_task(self.state, "working...")))
        if method == "tasks/get":
            self.get_count += 1
            if self.auto_finish and self.get_count >= 2:
                self.state = self.final_state
            text = "final answer" if self.state == "completed" else self.state
            return Response(200, json=_rpc_result(_task(self.state, text)))
        if method == "tasks/cancel":
            self.state = "canceled"
            return Response(200, json=_rpc_result(_task("canceled")))
        raise AssertionError(f"unexpected A2A method: {method}")


def _ctx() -> tuple[ToolContext, list[dict]]:
    progress: list[dict] = []
    return ToolContext(signal=asyncio.Event(), on_update=lambda r: progress.append(r.details)), progress


def _tool(final_state: str = "completed") -> A2AAgentTool:
    return A2AAgentTool(
        name="researcher",
        description="research agent",
        base_url=BASE,
        timeout_seconds=5,
        poll_interval=0.01,
    )


@pytest.mark.asyncio
@respx.mock
async def test_execute_completed():
    server = _Handler()
    respx.post(BASE + "/").mock(side_effect=server)
    tool = _tool()
    ctx, progress = _ctx()
    result = await tool.execute("call-1", {"prompt": "research X"}, ctx)
    text = "".join(c.text for c in result.content if isinstance(c, TextContent))
    assert "final answer" in text
    delegation = result.details["delegation"]
    assert delegation["status"] == "completed"
    assert delegation["task_id"] == "t1"
    assert result.details["task"]["id"] == "t1"
    # progress events were emitted through ctx.on_update
    assert any(p.get("delegation", {}).get("phase") == "remote_task_update" for p in progress)


@pytest.mark.asyncio
@respx.mock
async def test_execute_failed():
    server = _Handler(final_state="failed")
    respx.post(BASE + "/").mock(side_effect=server)
    tool = _tool()
    ctx, _ = _ctx()
    result = await tool.execute("call-1", {"prompt": "do bad thing"}, ctx)
    delegation = result.details["delegation"]
    assert delegation["status"] == "failed"
    assert "失败" in "".join(c.text for c in result.content if isinstance(c, TextContent))


@pytest.mark.asyncio
@respx.mock
async def test_execute_aborts_on_signal():
    server = _Handler(auto_finish=False)
    respx.post(BASE + "/").mock(side_effect=server)
    tool = _tool()
    ctx, _ = _ctx()

    async def _set():
        await asyncio.sleep(0.02)
        ctx.signal.set()

    asyncio.get_running_loop().create_task(_set())
    result = await tool.execute("call-1", {"prompt": "long task"}, ctx)
    delegation = result.details["delegation"]
    assert delegation["status"] == "aborted"
    assert "tasks/cancel" in server.calls


@pytest.mark.asyncio
@respx.mock
async def test_execute_input_required():
    server = _Handler(final_state="input-required")
    respx.post(BASE + "/").mock(side_effect=server)
    tool = _tool()
    ctx, _ = _ctx()
    result = await tool.execute("call-1", {"prompt": "ambiguous"}, ctx)
    delegation = result.details["delegation"]
    assert delegation["status"] == "input_required"
    assert "需要更多输入" in "".join(c.text for c in result.content if isinstance(c, TextContent))


def test_parse_a2a_agents_json():
    raw = json.dumps([
        {"name": "r1", "url": "http://x", "description": "desc", "token_env": "TOK"},
        {"name": "r2", "url": "http://y", "timeout_seconds": 30},
    ])
    configs = parse_a2a_agents(raw)
    assert [c.name for c in configs] == ["r1", "r2"]
    assert configs[0].token_env == "TOK"
    assert configs[1].timeout_seconds == 30


def test_parse_a2a_agents_legacy():
    configs = parse_a2a_agents("r1:http://x:MY_TOKEN|r2:http://y")
    assert [(c.name, c.url) for c in configs] == [("r1", "http://x"), ("r2", "http://y")]
    assert configs[0].token_env == "MY_TOKEN"


def test_load_a2a_agent_configs_from_file(tmp_path):
    (tmp_path / ".a2a.json").write_text(
        json.dumps({"agents": [{"name": "r1", "url": "http://x"}]}), encoding="utf-8"
    )
    configs = load_a2a_agent_configs(cwd=str(tmp_path))
    assert len(configs) == 1
    assert configs[0].name == "r1"


def test_load_a2a_agent_configs_from_env(monkeypatch):
    monkeypatch.setenv("A2A_AGENTS", json.dumps([{"name": "r1", "url": "http://x"}]))
    configs = load_a2a_agent_configs(cwd="/nonexistent")
    assert len(configs) == 1
    assert configs[0].url == "http://x"


def test_build_and_register_a2a_tools():
    registry = ToolRegistry()
    configs = [
        A2AAgentConfig(name="r1", url="http://x"),
        A2AAgentConfig(name="r2", url="http://y", description="agent two"),
    ]
    tools = build_a2a_tools(configs)
    assert [t.definition.name for t in tools] == ["r1", "r2"]
    assert "agent two" in tools[1].definition.description
    for t in tools:
        registry.register(t)
    assert registry.get("r1") is not None
    assert "prompt" in registry.get("r2").definition.parameters["properties"]


def test_register_a2a_tools(tmp_path):
    (tmp_path / ".a2a.json").write_text(
        json.dumps({"agents": [{"name": "r1", "url": "http://x"}]}), encoding="utf-8"
    )
    registry = ToolRegistry()
    n = register_a2a_tools(registry, cwd=str(tmp_path))
    assert n == 1
    assert registry.get("r1") is not None
