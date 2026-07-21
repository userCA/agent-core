"""Unit tests for ArtifactStore (L1 ToolResultRefStore MVP)."""

from __future__ import annotations

import pytest

from agent_core.artifacts.store import InMemoryArtifactStore


@pytest.mark.asyncio
async def test_store_and_get_roundtrip():
    store = InMemoryArtifactStore()
    ref_id = await store.put(
        content="hello " * 1000,
        meta={"tool_name": "echo", "chars": 6000},
    )
    assert ref_id
    art = await store.get(ref_id)
    assert art is not None
    assert art.content.startswith("hello ")
    assert art.meta["tool_name"] == "echo"


@pytest.mark.asyncio
async def test_get_missing_returns_none():
    store = InMemoryArtifactStore()
    assert await store.get("missing-id") is None
