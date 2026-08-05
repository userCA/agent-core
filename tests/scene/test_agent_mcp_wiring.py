"""Scene-level tests: ChatAssistant assembles MCP tools per AgentDefinition.

Two agents with different private MCP servers must not see each other's
private tools, while shared tools are visible to both. Uses stub MCP
managers — no real MCP connections are made.
"""

from __future__ import annotations

import json
import os

import pytest

from agent_core.resources.agents import AgentDefinition, AgentTools
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.tools.base import ToolDefinition
from agent_core.tools.mcp_pool import MCPPool
from agent_core.tools.mcp_tool import MCPManager
from scene.http_sse.chat_assistant import ChatAssistant
from scene.http_sse.manager import SessionManager


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class StubAdapter:
    def __init__(self, name, server_name=""):
        self.server_name = server_name
        self.definition = ToolDefinition(name=name, description="", parameters={})

    async def execute(self, tool_call_id, params, ctx):
        return None


class StubMCPManager:
    def __init__(self, adapters=None):
        self._adapters = list(adapters or [])

    @property
    def adapters(self):
        return list(self._adapters)

    async def start(self):
        pass

    async def stop(self):
        pass

    def register_tools(self, registry):
        count = 0
        for a in self._adapters:
            registry.register(a)
            count += 1
        return count


def _write_agent_mcp(cwd: str, agent_id: str, server: str) -> None:
    path = os.path.join(cwd, ".pi", "mcp", "agents", f"{agent_id}.mcp.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"mcpServers": {server: {"command": "echo", "args": ["hi"]}}}, f)


def _agent(aid: str, private_server: str) -> AgentDefinition:
    return AgentDefinition(
        id=aid,
        name=aid.upper(),
        description="",
        system_prompt=f"You are {aid}",
        tools=AgentTools(shared_mcp=["shared"], private_mcp=[private_server]),
    )


def _stub_pool(cwd: str) -> MCPPool:
    def factory(configs):
        return StubMCPManager(
            [StubAdapter(f"tool_{cfg.name}", cfg.name) for cfg in configs]
        )

    return MCPPool(
        shared=StubMCPManager([StubAdapter("shared_tool", "shared")]),
        cwd=cwd,
        manager_factory=factory,
    )


@pytest.mark.asyncio
async def test_private_mcp_tools_are_mutually_invisible(tmp_path):
    cwd = str(tmp_path)
    _write_agent_mcp(cwd, "a", "a-server")
    _write_agent_mcp(cwd, "b", "b-server")

    pool = _stub_pool(cwd)
    agent_a = _agent("a", "a-server")
    agent_b = _agent("b", "b-server")

    assistant_a = await ChatAssistant.create(
        session_store=InMemoryStore(),
        session_id="sa",
        cwd=cwd,
        mcp_pool=pool,
        agent=agent_a,
        owner="u1",
        enable_multi_agent=False,
    )
    assistant_b = await ChatAssistant.create(
        session_store=InMemoryStore(),
        session_id="sb",
        cwd=cwd,
        mcp_pool=pool,
        agent=agent_b,
        owner="u1",
        enable_multi_agent=False,
    )

    try:
        names_a = assistant_a.tool_names
        names_b = assistant_b.tool_names

        # Each agent sees only its own private server's tool.
        assert "tool_a-server" in names_a
        assert "tool_b-server" in names_b
        assert "tool_a-server" not in names_b
        assert "tool_b-server" not in names_a
        # Shared tools are visible to both.
        assert "shared_tool" in names_a
        assert "shared_tool" in names_b
    finally:
        await assistant_a.dispose()
        await assistant_b.dispose()


@pytest.mark.asyncio
async def test_session_manager_start_builds_pool(tmp_path, monkeypatch):
    # Avoid real MCP connections: from_env returns an empty manager.
    monkeypatch.setattr(
        MCPManager,
        "from_env",
        classmethod(lambda cls: MCPManager([])),
    )
    # Avoid embedding model warm-up (would download a model on first call).
    monkeypatch.setattr(
        "agent_core.knowledge.local_kb._get_model",
        lambda: None,
    )

    mgr = SessionManager(cwd=str(tmp_path), session_store_dir=str(tmp_path))
    await mgr.start()

    assert mgr._mcp_manager is not None
    assert mgr._mcp_pool is not None
    assert mgr._mcp_pool.shared is mgr._mcp_manager

    await mgr.dispose_all()
