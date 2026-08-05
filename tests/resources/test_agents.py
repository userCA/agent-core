"""Tests for agent definition loading from .pi/agents/*.json."""

import json
import os
from pathlib import Path

from agent_core.resources.agents import (
    AgentDefinition,
    AgentKnowledge,
    AgentTools,
    delete_agent,
    get_agent,
    load_agents,
    save_agent,
)


def test_load_agent_with_private_and_shared(tmp_path: Path):
    agents_dir = tmp_path / ".pi" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "support.json").write_text(
        '{"id":"support","name":"客服","system_prompt":"hi",'
        '"tools":{"builtin":["read"],"shared_mcp":["amap"],"private_mcp":["crm"]},'
        '"knowledge":{"shared":["faq"],"private":["refund"]}}',
        encoding="utf-8",
    )
    agent = get_agent("support", cwd=str(tmp_path))
    assert agent is not None
    assert agent.tools.shared_mcp == ["amap"]
    assert agent.tools.private_mcp == ["crm"]
    assert agent.knowledge.private == ["refund"]


def test_missing_tools_and_knowledge_blocks_default_to_none(tmp_path: Path):
    agents_dir = tmp_path / ".pi" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "plain.json").write_text(
        '{"id":"plain","name":"朴素","system_prompt":"hi"}', encoding="utf-8"
    )
    agent = get_agent("plain", cwd=str(tmp_path))
    assert agent is not None
    assert agent.tools is None
    assert agent.knowledge is None


def test_save_agent_roundtrip(tmp_path: Path):
    agent = AgentDefinition(
        id="ops",
        name="运维",
        description="ops assistant",
        system_prompt="you are ops",
        tools=AgentTools(
            builtin=["bash"], shared_mcp=["tavily"], private_mcp=["crm"]
        ),
        knowledge=AgentKnowledge(
            shared=["runbook"],
            private=["secrets"],
            shared_mcp_knowledge=["wiki"],
            private_mcp_knowledge=["crm-kb"],
        ),
    )
    save_agent(agent, cwd=str(tmp_path))
    loaded = get_agent("ops", cwd=str(tmp_path))
    assert loaded is not None
    assert loaded.id == "ops"
    assert loaded.name == "运维"
    assert loaded.tools is not None
    assert loaded.tools.builtin == ["bash"]
    assert loaded.tools.shared_mcp == ["tavily"]
    assert loaded.tools.private_mcp == ["crm"]
    assert loaded.knowledge is not None
    assert loaded.knowledge.shared == ["runbook"]
    assert loaded.knowledge.private == ["secrets"]
    assert loaded.knowledge.shared_mcp_knowledge == ["wiki"]
    assert loaded.knowledge.private_mcp_knowledge == ["crm-kb"]


def test_save_agent_omits_default_keys(tmp_path: Path):
    agent = AgentDefinition(id="min", name="min", description="", system_prompt="hi")
    save_agent(agent, cwd=str(tmp_path))
    data = json.loads(
        (tmp_path / ".pi" / "agents" / "min.json").read_text(encoding="utf-8")
    )
    assert "tools" not in data
    assert "knowledge" not in data


def test_save_agent_preserves_empty_blocks(tmp_path: Path):
    # AgentTools()/AgentKnowledge() is explicit-empty, not "unrestricted".
    agent = AgentDefinition(
        id="empty",
        name="empty",
        description="",
        system_prompt="hi",
        tools=AgentTools(),
        knowledge=AgentKnowledge(),
    )
    save_agent(agent, cwd=str(tmp_path))
    data = json.loads(
        (tmp_path / ".pi" / "agents" / "empty.json").read_text(encoding="utf-8")
    )
    assert data["tools"] == {}
    assert data["knowledge"] == {}
    loaded = get_agent("empty", cwd=str(tmp_path))
    assert loaded is not None
    assert loaded.tools is not None
    assert loaded.tools.builtin is None
    assert loaded.tools.shared_mcp == []
    assert loaded.tools.private_mcp == []
    assert loaded.knowledge is not None
    assert loaded.knowledge.shared == []
    assert loaded.knowledge.private == []


def test_delete_agent(tmp_path: Path):
    agent = AgentDefinition(id="gone", name="gone", description="", system_prompt="hi")
    save_agent(agent, cwd=str(tmp_path))
    assert delete_agent("gone", cwd=str(tmp_path)) is True
    assert get_agent("gone", cwd=str(tmp_path)) is None
    assert delete_agent("gone", cwd=str(tmp_path)) is False


def test_load_agents_lists_multiple_and_skips_bad_files(tmp_path: Path):
    agents_dir = tmp_path / ".pi" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "a.json").write_text(
        '{"id":"a","name":"A","system_prompt":"hi"}', encoding="utf-8"
    )
    (agents_dir / "b.json").write_text(
        '{"id":"b","name":"B","system_prompt":"hi"}', encoding="utf-8"
    )
    (agents_dir / "bad.json").write_text("{not json", encoding="utf-8")
    agents = load_agents(cwd=str(tmp_path))
    assert [a.id for a in agents] == ["a", "b"]


def test_local_agent_wins_over_home(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    (home / ".pi" / "agent" / "agents").mkdir(parents=True)
    (home / ".pi" / "agent" / "agents" / "dup.json").write_text(
        '{"id":"dup","name":"home","system_prompt":"home"}', encoding="utf-8"
    )
    local = tmp_path / "local"
    (local / ".pi" / "agents").mkdir(parents=True)
    (local / ".pi" / "agents" / "dup.json").write_text(
        '{"id":"dup","name":"local","system_prompt":"local"}', encoding="utf-8"
    )
    monkeypatch.setattr(
        os.path, "expanduser", lambda p: str(home) + p[1:] if p.startswith("~") else p
    )
    agents = load_agents(cwd=str(local))
    assert [a.id for a in agents] == ["dup"]
    assert agents[0].name == "local"
