"""Scene-level tests: AgentDefinition.tools.builtin whitelist enforcement.

R4 (builtin ∩ whitelist): an agent declaring ``builtin`` must only expose the
listed builtin tool names, PLUS the MCP tools selected for the agent and
``search_knowledge`` when a KB was assembled. ``builtin is None`` (or a tools
block absent) means unrestricted — no filtering.

Uses the tmp-cwd stub-MCPPool pattern from test_agent_mcp_wiring.py.
"""

from __future__ import annotations

from agent_core.resources.agents import AgentDefinition, AgentTools
from agent_core.resources.personas import Persona
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.tools.base import ToolDefinition
from agent_core.tools.mcp_pool import MCPPool
from scene.http_sse.chat_assistant import ChatAssistant


# ---------------------------------------------------------------------------
# Stubs (mirrors test_agent_mcp_wiring.py)
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


def _agent(aid: str, tools: AgentTools | None = None) -> AgentDefinition:
    return AgentDefinition(
        id=aid,
        name=aid.upper(),
        description="",
        system_prompt=f"You are {aid}",
        tools=tools,
    )


async def _create(cwd: str, agent: AgentDefinition, pool=None):
    return await ChatAssistant.create(
        session_store=InMemoryStore(),
        session_id=f"sid-{agent.id}",
        cwd=cwd,
        mcp_pool=pool,
        agent=agent,
        owner="u1",
        enable_multi_agent=False,
    )


# ---------------------------------------------------------------------------
# builtin whitelist filtering
# ---------------------------------------------------------------------------

async def test_builtin_whitelist_filters_builtin_tools(tmp_path):
    cwd = str(tmp_path)
    agent = _agent("minimal", AgentTools(builtin=["read"]))
    assistant = await _create(cwd, agent)
    try:
        names = set(assistant.tool_names)
        assert "read" in names
        assert "write" not in names
        assert "bash" not in names
        assert "edit" not in names
    finally:
        await assistant.dispose()


async def test_builtin_whitelist_keeps_selected_mcp_tools(tmp_path):
    cwd = str(tmp_path)
    pool = _stub_pool(cwd)
    agent = _agent("mcpagent", AgentTools(builtin=["read"], shared_mcp=["shared"]))
    assistant = await _create(cwd, agent, pool=pool)
    try:
        names = set(assistant.tool_names)
        assert "read" in names
        assert "shared_tool" in names
        assert "write" not in names
        assert "bash" not in names
    finally:
        await assistant.dispose()


async def test_builtin_none_means_unrestricted(tmp_path):
    cwd = str(tmp_path)
    agent = _agent("full", AgentTools())  # builtin None
    assistant = await _create(cwd, agent)
    try:
        names = set(assistant.tool_names)
        assert {"read", "write", "bash", "edit", "ls", "find", "grep", "confirm"} <= names
    finally:
        await assistant.dispose()


async def test_tools_block_absent_means_unrestricted(tmp_path):
    cwd = str(tmp_path)
    agent = _agent("plain")  # tools=None
    assistant = await _create(cwd, agent)
    try:
        names = set(assistant.tool_names)
        assert "read" in names
        assert "write" in names
        assert "bash" in names
    finally:
        await assistant.dispose()
