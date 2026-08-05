"""Tests for MCPPool — shared/private MCP manager pool.

Uses stub adapters and stub managers; no real MCP connections are made.
"""

import asyncio
import json
import logging

import pytest

from agent_core.resources.agents import AgentDefinition, AgentKnowledge, AgentTools
from agent_core.tools.base import ToolDefinition, ToolRegistry
from agent_core.tools.mcp_pool import MCPPool


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class StubAdapter:
    def __init__(self, name, server_name=""):
        self.server_name = server_name
        self.definition = ToolDefinition(name=name, description="", parameters={})

    async def execute(self, tool_call_id, params, ctx):
        return None


class StubManager:
    def __init__(self, adapters=None):
        self._adapters = list(adapters or [])
        self.start_calls = 0
        self.stop_calls = 0

    @property
    def adapters(self):
        return list(self._adapters)

    async def start(self):
        self.start_calls += 1

    async def stop(self):
        self.stop_calls += 1


def _a(name, server=""):
    return StubAdapter(name, server)


def _shared(*adapters):
    return StubManager(list(adapters))


def _agent(aid="a", tools=None, knowledge=None):
    return AgentDefinition(
        id=aid,
        name="",
        description="",
        system_prompt="",
        tools=tools,
        knowledge=knowledge,
    )


def _names(adapters):
    return [a.definition.name for a in adapters]


@pytest.fixture(autouse=True)
def _no_env_servers(monkeypatch):
    """Isolate ensure_private from any ambient MCP_SERVERS env var."""
    monkeypatch.setenv("MCP_SERVERS", "")


# ---------------------------------------------------------------------------
# Shared filtering
# ---------------------------------------------------------------------------

def test_shared_tools_none_includes_all_shared():
    pool = MCPPool(shared=_shared(_a("t1", "a"), _a("t2", "a"), _a("t3", "b")))
    adapters = pool.adapters_for_agent(_agent(tools=None))
    assert _names(adapters) == ["t1", "t2", "t3"]


def test_shared_filter_by_server_name():
    pool = MCPPool(shared=_shared(_a("t1", "a"), _a("t2", "a"), _a("t3", "b")))
    adapters = pool.adapters_for_agent(_agent(tools=AgentTools(shared_mcp=["a"])))
    assert _names(adapters) == ["t1", "t2"]
    assert [a.server_name for a in adapters] == ["a", "a"]


def test_shared_empty_list_selects_nothing():
    pool = MCPPool(shared=_shared(_a("t1", "a"), _a("t3", "b")))
    adapters = pool.adapters_for_agent(_agent(tools=AgentTools(shared_mcp=[])))
    assert adapters == []


# ---------------------------------------------------------------------------
# Private filtering
# ---------------------------------------------------------------------------

async def test_private_filter_by_server_name():
    factory = lambda configs: StubManager([_a("p1", "priv"), _a("o1", "other")])
    pool = MCPPool(shared=_shared(), manager_factory=factory)
    agent = _agent(tools=AgentTools(private_mcp=["priv"]))
    await pool.ensure_private(agent.id)

    adapters = pool.adapters_for_agent(agent)
    assert _names(adapters) == ["p1"]


async def test_private_without_named_server_contributes_nothing():
    factory = lambda configs: StubManager([_a("o1", "other")])
    pool = MCPPool(shared=_shared(), manager_factory=factory)
    agent = _agent(tools=AgentTools(private_mcp=["priv"]))
    await pool.ensure_private(agent.id)

    assert pool.adapters_for_agent(agent) == []


async def test_private_excluded_when_tools_none():
    factory = lambda configs: StubManager([_a("p1", "priv")])
    pool = MCPPool(shared=_shared(_a("s1", "shared")), manager_factory=factory)
    agent = _agent(tools=None)
    await pool.ensure_private(agent.id)

    adapters = pool.adapters_for_agent(agent)
    assert _names(adapters) == ["s1"]  # shared only, no private


# ---------------------------------------------------------------------------
# Knowledge servers
# ---------------------------------------------------------------------------

async def test_knowledge_shared_and_private():
    factory = lambda configs: StubManager([_a("pk", "kbpriv")])
    pool = MCPPool(
        shared=_shared(_a("t1", "kb"), _a("t2", "other")),
        manager_factory=factory,
    )
    agent = _agent(
        tools=None,
        knowledge=AgentKnowledge(
            shared_mcp_knowledge=["kb"],
            private_mcp_knowledge=["kbpriv"],
        ),
    )
    await pool.ensure_private(agent.id)

    # tools=None includes all shared; private knowledge appended last.
    adapters = pool.adapters_for_agent(agent)
    assert _names(adapters) == ["t1", "t2", "pk"]


async def test_knowledge_unions_with_shared_tools():
    pool = MCPPool(shared=_shared(_a("t1", "kb"), _a("t2", "other")))
    agent = _agent(
        tools=AgentTools(shared_mcp=["other"]),
        knowledge=AgentKnowledge(shared_mcp_knowledge=["kb"]),
    )
    adapters = pool.adapters_for_agent(agent)
    assert _names(adapters) == ["t2", "t1"]


# ---------------------------------------------------------------------------
# Name conflicts — private wins
# ---------------------------------------------------------------------------

async def test_private_wins_on_name_conflict(caplog):
    private_foo = _a("foo", "priv")
    factory = lambda configs: StubManager([private_foo])
    pool = MCPPool(shared=_shared(_a("foo", "shared")), manager_factory=factory)
    agent = _agent(tools=AgentTools(shared_mcp=["shared"], private_mcp=["priv"]))
    await pool.ensure_private(agent.id)

    registry = ToolRegistry()
    with caplog.at_level(logging.WARNING, logger="agent_core.tools.mcp_pool"):
        count = pool.register_tools(registry, agent)

    assert count == 2
    assert registry.get("foo") is private_foo
    assert any("Overwriting existing tool 'foo'" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# ensure_private caching / loading
# ---------------------------------------------------------------------------

async def test_ensure_private_caches(tmp_path):
    cfg_file = tmp_path / ".pi" / "mcp" / "agents" / "x.mcp.json"
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text(
        json.dumps({"mcpServers": {"priv": {"command": "echo", "args": []}}}),
        encoding="utf-8",
    )

    received = []

    def factory(configs):
        received.append(list(configs))
        return StubManager()

    pool = MCPPool(shared=_shared(), cwd=str(tmp_path), manager_factory=factory)

    m1 = await pool.ensure_private("x")
    m2 = await pool.ensure_private("x")

    assert m1 is m2
    assert len(received) == 1  # second call served from cache
    assert len(received[0]) == 1
    assert received[0][0].name == "priv"
    assert received[0][0].transport == "stdio"
    assert m1.start_calls == 1


async def test_ensure_private_no_config_file_ignores_env(tmp_path, monkeypatch):
    # Private loading is strict: even with MCP_SERVERS set, a missing private
    # config file must NOT inherit global env servers.
    monkeypatch.setenv("MCP_SERVERS", "stdio:env_srv:echo:hi")

    received = []

    def factory(configs):
        received.append(list(configs))
        return StubManager()

    pool = MCPPool(shared=_shared(), cwd=str(tmp_path), manager_factory=factory)
    agent = _agent(tools=AgentTools(private_mcp=["priv"]))

    manager = await pool.ensure_private(agent.id)

    assert manager.adapters == []
    assert received == [[]]  # no env fallback
    assert await pool.ensure_private(agent.id) is manager
    assert len(received) == 1  # cached, so no re-read
    assert pool.adapters_for_agent(agent) == []


async def test_ensure_private_concurrent_single_flight(tmp_path):
    cfg_file = tmp_path / ".pi" / "mcp" / "agents" / "x.mcp.json"
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text(
        json.dumps({"mcpServers": {"priv": {"command": "echo", "args": []}}}),
        encoding="utf-8",
    )

    received = []

    def factory(configs):
        received.append(list(configs))
        return StubManager()

    pool = MCPPool(shared=_shared(), cwd=str(tmp_path), manager_factory=factory)

    m1, m2 = await asyncio.gather(
        pool.ensure_private("x"),
        pool.ensure_private("x"),
    )

    assert m1 is m2
    assert len(received) == 1  # factory called exactly once under concurrency
    assert m1.start_calls == 1


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

async def test_start_shared():
    shared = _shared()
    pool = MCPPool(shared=shared)
    await pool.start_shared()
    assert shared.start_calls == 1


async def test_stop_stops_shared_and_all_private():
    shared = _shared()
    factory = lambda configs: StubManager()
    pool = MCPPool(shared=shared, manager_factory=factory)
    await pool.ensure_private("x")
    await pool.ensure_private("y")

    await pool.stop()

    assert shared.stop_calls == 1
    assert pool._private["x"].stop_calls == 1
    assert pool._private["y"].stop_calls == 1
