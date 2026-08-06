"""MCP integration tests — config parsing, manager lifecycle, tool registration."""

import asyncio

import pytest

from agent_core.tools.base import ToolDefinition, ToolRegistry
from agent_core.tools.mcp_tool import (
    MCPServerConfig,
    MCPManager,
    parse_mcp_servers,
)


class TestMCPConfig:
    def test_parse_empty(self):
        assert parse_mcp_servers("") == []
        assert parse_mcp_servers("   ") == []

    def test_parse_single_stdio(self):
        servers = parse_mcp_servers("stdio:echo:python:-m:agent_core.skills.mcp_example_server")
        assert len(servers) == 1
        assert servers[0].name == "echo"
        assert servers[0].transport == "stdio"
        assert servers[0].command == ["python", "-m", "agent_core.skills.mcp_example_server"]

    def test_parse_single_sse(self):
        servers = parse_mcp_servers("sse:remote:http://localhost:8080/sse")
        assert len(servers) == 1
        assert servers[0].name == "remote"
        assert servers[0].transport == "sse"
        assert servers[0].url == "http://localhost:8080/sse"

    def test_parse_multi(self):
        servers = parse_mcp_servers("stdio:a:cmd:arg1|sse:b:http://x:8080")
        assert len(servers) == 2
        assert servers[0].name == "a"
        assert servers[1].name == "b"

    def test_parse_streamable_http(self):
        servers = parse_mcp_servers(
            "streamable_http:amap:https://mcp.amap.com/mcp?key=abc123"
        )
        assert len(servers) == 1
        assert servers[0].name == "amap"
        assert servers[0].transport == "streamable_http"
        assert servers[0].url == "https://mcp.amap.com/mcp?key=abc123"


class TestMCPManager:
    @pytest.mark.asyncio
    async def test_empty_manager_noops(self):
        manager = MCPManager(configs=[])
        assert len(manager.adapters) == 0
        await manager.start()
        assert len(manager.adapters) == 0
        await manager.stop()
        assert len(manager.adapters) == 0

    @pytest.mark.asyncio
    async def test_register_tools(self):
        manager = MCPManager(configs=[])
        # Simulate a discovered adapter without actual MCP server
        from agent_core.tools.mcp_tool import MCPToolAdapter, MCPConnection

        conn = _FakeConnection()
        adapter = MCPToolAdapter(conn, {
            "name": "fake_echo",
            "description": "Fake echo tool",
            "inputSchema": {"type": "object", "properties": {}},
        })
        manager._adapters.append(adapter)

        registry = ToolRegistry()
        count = manager.register_tools(registry)
        assert count == 1
        assert "fake_echo" in registry

    @pytest.mark.asyncio
    async def test_register_tools_conflict_rename_does_not_mutate_shared_adapter(self):
        """Rename-on-conflict registers a COPY; the shared adapter's
        definition.name stays pristine so later agent sessions see the
        original name."""
        from agent_core.tools.mcp_tool import MCPToolAdapter, MCPConnection

        conn = _FakeConnection()
        adapter = MCPToolAdapter(conn, {
            "name": "echo",
            "description": "Echo tool",
            "inputSchema": {"type": "object", "properties": {}},
        }, server_name="srv")
        manager = MCPManager(configs=[])
        manager._adapters.append(adapter)

        registry = ToolRegistry()

        class _Other:
            definition = ToolDefinition(name="echo", description="other", parameters={})

        registry.register(_Other())  # pre-existing conflict by name

        manager.register_tools(registry)
        assert "echo" in registry
        assert "srv_echo" in registry
        # Shared adapter is never mutated.
        assert adapter.definition.name == "echo"

        # A subsequent call re-renames correctly (still a conflict).
        manager.register_tools(registry)
        assert "srv_echo" in registry
        assert registry.get("srv_echo") is not adapter
        assert adapter.definition.name == "echo"


class _FakeConnection:
    """Stub MCPConnection for unit testing tool adapter registration."""
    async def call_tool(self, name, arguments):
        from unittest.mock import MagicMock
        result = MagicMock()
        result.content = [MagicMock(text=f"Fake: {name}({arguments})")]
        return result
