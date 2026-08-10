"""Tests for WorkflowStore checkpoint persistence."""

from __future__ import annotations

import pytest

from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.store import SessionHeader
from agent_core.workflows.store import WORKFLOW_CHECKPOINT_TYPE, WorkflowStore
from agent_core.workflows.types import WorkflowCheckpoint


@pytest.fixture
def inmemory_store():
    return InMemoryStore()


async def _create_session(store: InMemoryStore, sid: str = "s1", owner: str = "u1") -> None:
    await store.create_session(
        sid,
        SessionHeader(id=sid, timestamp="2026-08-10T00:00:00Z", owner=owner),
    )


@pytest.mark.asyncio
async def test_save_and_load_checkpoint(inmemory_store):
    await _create_session(inmemory_store)
    ws = WorkflowStore(session_store=inmemory_store, session_id="s1", owner="u1")
    cp = WorkflowCheckpoint(
        run_id="r1",
        workflow_name="demo",
        status="running",
        updated_at=1.0,
        owner="u1",
        session_id="s1",
    )
    await ws.save_checkpoint(cp)
    loaded = await ws.load_checkpoint("r1")
    assert loaded is not None
    assert loaded.workflow_name == "demo"
    assert loaded.run_id == "r1"
    assert loaded.owner == "u1"
    assert loaded.session_id == "s1"

    snap = await inmemory_store.load_session("s1")
    customs = [
        e for e in snap.entries if getattr(e, "custom_type", None) == WORKFLOW_CHECKPOINT_TYPE
    ]
    assert len(customs) == 1
    assert customs[0].data["run_id"] == "r1"


@pytest.mark.asyncio
async def test_load_missing_returns_none(inmemory_store):
    await _create_session(inmemory_store)
    ws = WorkflowStore(session_store=inmemory_store, session_id="s1", owner="u1")
    assert await ws.load_checkpoint("missing") is None


@pytest.mark.asyncio
async def test_list_checkpoints_returns_saved(inmemory_store):
    await _create_session(inmemory_store)
    ws = WorkflowStore(session_store=inmemory_store, session_id="s1", owner="u1")
    cp1 = WorkflowCheckpoint(
        run_id="r1",
        workflow_name="demo",
        status="running",
        updated_at=1.0,
        owner="u1",
        session_id="s1",
    )
    cp2 = WorkflowCheckpoint(
        run_id="r2",
        workflow_name="other",
        status="completed",
        updated_at=2.0,
        owner="u1",
        session_id="s1",
    )
    await ws.save_checkpoint(cp1)
    await ws.save_checkpoint(cp2)
    listed = await ws.list_checkpoints()
    assert len(listed) >= 1
    run_ids = {c.run_id for c in listed}
    assert "r1" in run_ids
    assert "r2" in run_ids


@pytest.mark.asyncio
async def test_load_returns_latest_for_run_id(inmemory_store):
    await _create_session(inmemory_store)
    ws = WorkflowStore(session_store=inmemory_store, session_id="s1", owner="u1")
    await ws.save_checkpoint(
        WorkflowCheckpoint(
            run_id="r1",
            workflow_name="v1",
            status="running",
            updated_at=1.0,
            owner="u1",
            session_id="s1",
        )
    )
    await ws.save_checkpoint(
        WorkflowCheckpoint(
            run_id="r1",
            workflow_name="v2",
            status="paused",
            updated_at=2.0,
            owner="u1",
            session_id="s1",
        )
    )
    loaded = await ws.load_checkpoint("r1")
    assert loaded is not None
    assert loaded.workflow_name == "v2"
    assert loaded.status == "paused"
