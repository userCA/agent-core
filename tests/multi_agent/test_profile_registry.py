"""Tests for AgentProfileRegistry."""

from __future__ import annotations

from agent_core.multi_agent.profile_registry import AgentProfileRegistry
from agent_core.multi_agent.types import AgentProfile


def test_register_resolve_list():
    reg = AgentProfileRegistry()
    p = AgentProfile(name="billing", description="退款与订单", system_prompt="You are billing.")
    reg.register(p)
    assert reg.resolve("billing") is p
    assert reg.resolve("missing") is None
    assert [x.name for x in reg.list()] == ["billing"]


def test_unregister():
    reg = AgentProfileRegistry()
    reg.register(AgentProfile(name="a", description="A", system_prompt="a"))
    reg.unregister("a")
    assert reg.resolve("a") is None


def test_format_for_system_prompt_xml():
    reg = AgentProfileRegistry()
    reg.register(AgentProfile(name="billing", description="退款", system_prompt="b"))
    reg.register(AgentProfile(name="logistics", description="物流", system_prompt="l"))
    text = reg.format_for_system_prompt()
    assert "<available_agents>" in text
    assert "<name>billing</name>" in text
    assert "<description>退款</description>" in text
    assert "<name>logistics</name>" in text
