"""A2AClient transport tests (JSON-RPC over httpx, mocked with respx)."""

from __future__ import annotations

import asyncio
import json

import pytest
import respx
from httpx import Response

from agent_core.tools.a2a_client import A2AClient, A2AError

BASE = "http://a2a.test"


def _task(task_id: str = "t1", state: str = "completed", text: str = "hello from agent") -> dict:
    return {
        "id": task_id,
        "status": {"state": state},
        "artifacts": [],
        "messages": [{"role": "agent", "parts": [{"type": "text", "text": text}]}],
        "historyLength": 1,
    }


def _rpc_result(result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": "1", "result": result}


class _Handler:
    """Distinguishes A2A RPC methods hitting the same POST endpoint."""

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
            return Response(200, json=_rpc_result(_task("t1", self.state, "working...")))
        if method == "tasks/get":
            self.get_count += 1
            if self.auto_finish and self.get_count >= 2:
                self.state = self.final_state
            text = "final answer" if self.state == "completed" else self.state
            return Response(200, json=_rpc_result(_task("t1", self.state, text)))
        if method == "tasks/cancel":
            self.state = "canceled"
            return Response(200, json=_rpc_result(_task("t1", "canceled")))
        raise AssertionError(f"unexpected A2A method: {method}")


@pytest.mark.asyncio
@respx.mock
async def test_send_message_completed():
    respx.post(BASE + "/").mock(return_value=Response(200, json=_rpc_result(_task())))
    client = A2AClient(BASE)
    task = await client.send_message("hello")
    assert task.id == "t1"
    assert task.is_terminal()
    assert task.output_text() == "hello from agent"


@pytest.mark.asyncio
@respx.mock
async def test_run_task_polls_until_completed():
    server = _Handler()
    respx.post(BASE + "/").mock(side_effect=server)
    client = A2AClient(BASE, poll_interval=0.01)
    task = await client.run_task("do it")
    assert task.state == "completed"
    assert task.output_text() == "final answer"
    assert server.calls.count("tasks/get") >= 1


@pytest.mark.asyncio
@respx.mock
async def test_run_task_input_required_stops_polling():
    server = _Handler(final_state="input-required")
    respx.post(BASE + "/").mock(side_effect=server)
    client = A2AClient(BASE, poll_interval=0.01)
    task = await client.run_task("do it")
    assert task.needs_input()
    # Stops as soon as the agent reports input-required (2 gets: working→required).
    assert server.get_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_run_task_cancel_on_signal():
    server = _Handler(auto_finish=False)
    respx.post(BASE + "/").mock(side_effect=server)
    client = A2AClient(BASE, poll_interval=0.01)
    signal = asyncio.Event()
    ctx = type("Ctx", (), {"signal": signal})()

    async def _set():
        await asyncio.sleep(0.03)
        signal.set()

    asyncio.get_running_loop().create_task(_set())
    task = await client.run_task("do it", ctx=ctx)
    assert task.state == "canceled"
    assert "tasks/cancel" in server.calls


@pytest.mark.asyncio
@respx.mock
async def test_run_task_timeout():
    respx.post(BASE + "/").mock(return_value=Response(200, json=_rpc_result(_task("t1", "working"))))
    client = A2AClient(BASE, poll_interval=0.01, timeout=120.0)
    with pytest.raises(A2AError, match="timed out"):
        await client.run_task("do it", max_wait_seconds=0.05)


@pytest.mark.asyncio
@respx.mock
async def test_rpc_error_raises_a2a_error():
    respx.post(BASE + "/").mock(return_value=Response(200, json={
        "jsonrpc": "2.0", "id": "1",
        "error": {"code": -32001, "message": "invalid message"},
    }))
    client = A2AClient(BASE)
    with pytest.raises(A2AError, match="invalid message"):
        await client.send_message("hi")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_agent_card():
    card = {
        "name": "researcher",
        "description": "research agent",
        "skills": [{"id": "s1", "name": "web search"}],
        "capabilities": {"streaming": True},
    }
    respx.get(BASE + "/.well-known/agent-card.json").mock(return_value=Response(200, json=card))
    client = A2AClient(BASE)
    c = await client.fetch_agent_card()
    assert c.name == "researcher"
    assert c.skills[0]["id"] == "s1"
    assert c.capabilities["streaming"] is True


@pytest.mark.asyncio
@respx.mock
async def test_subscribe_sse_streams_until_terminal():
    frame1 = json.dumps(_rpc_result(_task("t1", "working", "thinking..."))).replace("\n", "")
    frame2 = json.dumps(_rpc_result(_task("t1", "completed", "final"))).replace("\n", "")
    body = f"event: message\ndata: {frame1}\n\n" f"event: message\ndata: {frame2}\n\n"
    respx.post(BASE + "/").mock(return_value=Response(
        200, headers={"content-type": "text/event-stream"}, content=body.encode()
    ))
    client = A2AClient(BASE)
    states: list[str] = []
    task = await client.subscribe("t1", on_update=lambda t: states.append(t.state))
    assert task is not None
    assert task.state == "completed"
    assert states == ["working", "completed"]
