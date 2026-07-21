"""Persist/reload round-trip for tool_result details (__refId)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_core.core.content import TextContent
from agent_core.core.messages import deserialize_message
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.persistence import HarnessPersistence
from agent_core.session.store import SessionHeader
from agent_core.tools.base import ToolResult


@pytest.mark.asyncio
async def test_persist_tool_result_keeps_artifact_details():
    store = InMemoryStore()
    await store.create_session(
        "sess-art",
        SessionHeader(id="sess-art", timestamp="2026-07-21T00:00:00Z"),
    )
    persistence = HarnessPersistence(store, "sess-art")
    result = ToolResult(
        content=[TextContent(text="[artifact_ref]\nrefId: abc\n")],
        details={"__stored": True, "__refId": "abc", "exit_code": 0},
    )
    evt = SimpleNamespace(
        tool_call_id="c1",
        tool_name="bash",
        result=result,
        is_error=False,
    )
    await persistence.persist_tool_result(evt)

    snapshot = await store.load_session("sess-art")
    assert snapshot is not None
    entry = next(e for e in snapshot.entries if getattr(e, "type", None) == "message")
    msg = deserialize_message(entry.message)
    assert msg.role == "tool_result"
    assert msg.details["__refId"] == "abc"
    assert msg.details["exit_code"] == 0
