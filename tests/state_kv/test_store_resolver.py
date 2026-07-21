"""Unit tests for SessionStateStore + placeholder resolver."""

from __future__ import annotations

import pytest

from agent_core.state_kv.resolver import (
    STATE_KEY_MISSING,
    StateKeyMissingError,
    has_state_placeholder,
    resolve_placeholders,
)
from agent_core.state_kv.store import InMemorySessionStateStore


@pytest.mark.asyncio
async def test_store_set_get_has_clear():
    store = InMemorySessionStateStore()
    assert await store.has("s1", "ids") is False
    await store.set("s1", "ids", [1, 2, 3])
    assert await store.has("s1", "ids") is True
    assert await store.get("s1", "ids") == [1, 2, 3]
    await store.set("s1", "nullable", None)
    assert await store.has("s1", "nullable") is True
    assert await store.get("s1", "nullable") is None
    await store.delete("s1", "ids")
    assert await store.has("s1", "ids") is False
    await store.clear("s1")
    assert await store.has("s1", "nullable") is False


@pytest.mark.asyncio
async def test_store_session_isolation():
    store = InMemorySessionStateStore()
    await store.set("a", "k", 1)
    await store.set("b", "k", 2)
    assert await store.get("a", "k") == 1
    assert await store.get("b", "k") == 2


@pytest.mark.asyncio
async def test_resolve_whole_placeholder_preserves_type():
    store = InMemorySessionStateStore()
    await store.set("s1", "ids", [10, 20])
    out = await resolve_placeholders(
        {"items": "{{state.ids}}"},
        store=store,
        session_id="s1",
    )
    assert out == {"items": [10, 20]}


@pytest.mark.asyncio
async def test_resolve_partial_string_interpolates():
    store = InMemorySessionStateStore()
    await store.set("s1", "id", "abc")
    out = await resolve_placeholders(
        {"path": "/tmp/{{state.id}}.json"},
        store=store,
        session_id="s1",
    )
    assert out == {"path": "/tmp/abc.json"}


@pytest.mark.asyncio
async def test_resolve_missing_key_raises():
    store = InMemorySessionStateStore()
    with pytest.raises(StateKeyMissingError) as ei:
        await resolve_placeholders(
            {"items": "{{state.missing}}"},
            store=store,
            session_id="s1",
        )
    assert STATE_KEY_MISSING in str(ei.value)
    assert ei.value.key == "missing"


def test_has_state_placeholder():
    assert has_state_placeholder({"a": "{{state.x}}"}) is True
    assert has_state_placeholder({"a": "plain"}) is False
    assert has_state_placeholder({"n": {"b": ["{{state.y}}"]}}) is True
