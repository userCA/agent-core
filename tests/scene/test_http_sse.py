"""Tests for HTTP SSE scene."""

from __future__ import annotations

import tempfile

import pytest

from agent_core.core.events import (
    MessageEnd,
    MessageUpdate,
    TextDelta,
    ThinkingDelta,
    ToolExecutionEnd,
    ToolExecutionStart,
)
from scene.http_sse.events import agent_event_to_sse_json
from scene.http_sse.manager import SessionManager


@pytest.fixture
def manager():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = SessionManager(cwd=tmpdir, session_store_dir=tmpdir)
        yield mgr


async def test_get_or_create_new_session(manager):
    session_id, assistant = await manager.get_or_create(None)
    assert session_id.startswith("scene-")
    assert assistant is not None


async def test_get_or_create_reuse(manager):
    sid1, assistant1 = await manager.get_or_create(None)
    sid2, assistant2 = await manager.get_or_create(sid1)
    assert sid1 == sid2
    assert assistant1 is assistant2


def test_text_delta():
    evt = MessageUpdate(message=None, delta=TextDelta(text="Hello"))
    result = agent_event_to_sse_json(evt)
    assert result == {"event": "text_delta", "text": "Hello"}


def test_thinking_delta():
    evt = MessageUpdate(message=None, delta=ThinkingDelta(text="Hmm"))
    result = agent_event_to_sse_json(evt)
    assert result == {"event": "thinking_delta", "text": "Hmm"}


def test_tool_start():
    evt = ToolExecutionStart(tool_call_id="tc1", tool_name="ls", args={"path": "/tmp"})
    result = agent_event_to_sse_json(evt)
    assert result == {"event": "tool_start", "tool_name": "ls", "args": {"path": "/tmp"}}


def test_tool_end():
    evt = ToolExecutionEnd(
        tool_call_id="tc1", tool_name="ls", result="file.txt", is_error=False
    )
    result = agent_event_to_sse_json(evt)
    assert result == {
        "event": "tool_end",
        "tool_name": "ls",
        "result": "file.txt",
        "is_error": False,
    }


def test_message_end_with_usage():
    class FakeUsage:
        input_tokens = 10
        output_tokens = 5
        cache_read_tokens = 0
        cache_write_tokens = 0
        total_tokens = 15

    msg = {"usage": FakeUsage()}
    evt = MessageEnd(message=msg)
    result = agent_event_to_sse_json(evt)
    assert result == {
        "event": "message_end",
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
        },
    }


def test_message_end_without_usage():
    evt = MessageEnd(message={})
    result = agent_event_to_sse_json(evt)
    assert result == {"event": "message_end", "usage": None}


def test_unsupported_events_return_none():
    from agent_core.core.events import AgentStart, TurnStart

    assert agent_event_to_sse_json(AgentStart()) is None
    assert agent_event_to_sse_json(TurnStart()) is None
