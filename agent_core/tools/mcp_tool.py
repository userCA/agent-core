"""MCP (Model Context Protocol) tool adapter.

Connects to MCP servers (stdio / SSE) and exposes their tools as agent_core Tools.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)


class MCPConnection:
    """Manages a single MCP server connection lifecycle."""

    def __init__(
        self,
        *,
        command: list[str] | None = None,
        url: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        if command is None and url is None:
            raise ValueError("Either 'command' (stdio) or 'url' (SSE) must be provided")
        self._command = command
        self._url = url
        self._env = env
        self._timeout = timeout
        self._session: Any = None
        self._context_stack: Any = None

    async def connect(self) -> None:
        """Connect to the MCP server and initialize the session."""
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        from mcp.client.sse import sse_client

        if self._command is not None:
            from mcp import StdioServerParameters

            params = StdioServerParameters(
                command=self._command[0],
                args=self._command[1:] if len(self._command) > 1 else [],
                env=self._env,
            )
            ctx = stdio_client(params)
        elif self._url is not None:
            ctx = sse_client(url=self._url)
        else:
            raise RuntimeError("No connection parameters configured")

        self._context_stack = ctx
        read, write = await ctx.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.initialize()

    async def close(self) -> None:
        """Close the MCP server connection."""
        if self._context_stack is not None:
            await self._context_stack.__aexit__(None, None, None)
            self._context_stack = None
        self._session = None

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools from the MCP server."""
        if self._session is None:
            raise RuntimeError("Not connected; call connect() first")
        result = await self._session.list_tools()
        return [t.model_dump() if hasattr(t, "model_dump") else t for t in result.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on the MCP server."""
        if self._session is None:
            raise RuntimeError("Not connected; call connect() first")
        return await self._session.call_tool(name, arguments)


class MCPToolAdapter:
    """Wraps a single MCP server tool as an agent_core Tool."""

    def __init__(self, connection: MCPConnection, tool_def: dict[str, Any]) -> None:
        self._connection = connection
        self._tool_def = tool_def
        self.definition = ToolDefinition(
            name=tool_def["name"],
            description=tool_def.get("description", ""),
            parameters=tool_def.get("inputSchema", {"type": "object", "properties": {}}),
        )

    async def execute(
        self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext
    ) -> ToolResult:
        try:
            result = await self._connection.call_tool(self._tool_def["name"], params)
            text = _extract_mcp_result(result)
            return ToolResult(content=[TextContent(text=text)])
        except Exception as exc:
            return ToolResult(
                content=[TextContent(text=f"MCP tool error: {exc}")],
                is_error=True,
            )


async def discover_mcp_tools(
    connection: MCPConnection,
) -> list[MCPToolAdapter]:
    """Connect to an MCP server and create adapters for all its tools."""
    await connection.connect()
    tool_defs = await connection.list_tools()
    return [MCPToolAdapter(connection, td) for td in tool_defs]


def _extract_mcp_result(result: Any) -> str:
    """Convert an MCP CallToolResult to a plain-text string."""
    if hasattr(result, "content"):
        parts: list[str] = []
        for block in result.content:
            if hasattr(block, "text"):
                parts.append(block.text)
            elif hasattr(block, "model_dump"):
                parts.append(str(block.model_dump()))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(result)
