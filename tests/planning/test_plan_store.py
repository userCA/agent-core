"""Unit tests for PlanStore + ManagePlanTool."""

from __future__ import annotations

import pytest

from agent_core.planning.plan_tool import ManagePlanTool
from agent_core.planning.store import PLAN_SNAPSHOT_TYPE, PlanStore
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.store import SessionHeader
from agent_core.tools.base import ToolContext, ToolRegistry
from agent_core.planning.factory import install_planning
from agent_core.planning.context import format_plan_for_prompt


@pytest.fixture
def store():
    return InMemoryStore()


async def _create_session(store: InMemoryStore, sid: str = "s1", owner: str = "u1"):
    await store.create_session(
        sid,
        SessionHeader(id=sid, timestamp="2026-07-20T00:00:00Z", owner=owner),
    )


@pytest.mark.asyncio
async def test_replace_and_set_status(store):
    await _create_session(store)
    ps = PlanStore(session_store=store, session_id="s1", owner="u1")
    plan = ps.replace(
        title="Refund flow",
        steps=[{"id": "a", "title": "Ask order"}, {"id": "b", "title": "Query"}],
    )
    assert plan.version == 1
    assert len(plan.steps) == 2
    await ps.persist()

    ps.set_status(step_id="a", status="in_progress")
    ps.set_status(step_id="a", status="completed", detail="got ORD-1")
    assert ps.plan.steps[0].status == "completed"
    assert ps.plan.version >= 3
    await ps.persist()

    snap = await store.load_session("s1")
    customs = [
        e for e in snap.entries if getattr(e, "custom_type", None) == PLAN_SNAPSHOT_TYPE
    ]
    assert len(customs) >= 2
    assert customs[-1].data["owner"] == "u1"
    assert customs[-1].data["plan"]["steps"][0]["status"] == "completed"


@pytest.mark.asyncio
async def test_load_latest_restores_plan(store):
    await _create_session(store)
    ps = PlanStore(session_store=store, session_id="s1", owner="u1")
    ps.replace(title="T", steps=[{"id": "1", "title": "one"}])
    await ps.persist()

    ps2 = PlanStore(session_store=store, session_id="s1", owner="u1")
    loaded = await ps2.load_latest()
    assert loaded is not None
    assert loaded.title == "T"
    assert loaded.steps[0].id == "1"


@pytest.mark.asyncio
async def test_manage_plan_tool_replace(store):
    await _create_session(store)
    ps = PlanStore(session_store=store, session_id="s1", owner="u1")
    tool = ManagePlanTool(plan_store=ps)
    updates: list = []

    def on_update(r):
        updates.append(r)

    result = await tool.execute(
        "c1",
        {
            "action": "replace",
            "title": "Ship",
            "steps": [{"title": "Pack"}, {"title": "Send"}],
        },
        ToolContext(signal=__import__("asyncio").Event(), on_update=on_update),
    )
    assert "Ship" in result.content[0].text
    assert result.details["plan"]["phase"] == "replaced"
    assert result.details["plan"]["total"] == 2
    assert updates


@pytest.mark.asyncio
async def test_install_planning_registers_tool(store):
    await _create_session(store)
    reg = ToolRegistry()
    plan_store, tool, exts = await install_planning(
        reg, store=store, session_id="s1", owner="u1"
    )
    assert reg.get("manage_plan") is tool
    assert any(getattr(e, "name", None) == "planning_context" for e in exts)
    assert plan_store.plan is None


def test_format_plan_for_prompt():
    ps = PlanStore()
    ps.replace(title="X", steps=[{"id": "1", "title": "Do"}])
    text = format_plan_for_prompt(ps.plan)
    assert "X" in text
    assert "1: Do" in text
