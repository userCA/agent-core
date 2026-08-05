"""MCP (Model Context Protocol) tool adapter — connect, discover, register.

Connects to MCP servers (stdio / SSE) and exposes their tools as agent_core Tools.
Supports auto-registration via MCPManager + ChatAssistant integration.

Config format (env MCP_SERVERS):
  stdio:server_name:command:arg1:arg2|sse:server_name:url
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolRegistry, ToolResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MCP server configuration
# ---------------------------------------------------------------------------

@dataclass
class MCPServerConfig:
    name: str
    transport: str  # "stdio" | "sse" | "streamable_http"
    command: list[str] | None = None
    url: str | None = None
    env: dict[str, str] | None = None
    server_type: str = "tool"  # "tool" | "knowledge"


def parse_mcp_servers(raw: str) -> list[MCPServerConfig]:
    """Parse MCP_SERVERS env string into server configs.

    Format: stdio:name:cmd:arg1:arg2|sse:name:url|streamable_http:name:url

    Examples:
        stdio:echo:python:-m:agent_core.skills.mcp_example_server
        sse:remote:http://localhost:8080/sse
        streamable_http:amap:https://mcp.amap.com/mcp?key=YOUR_KEY
    """
    servers: list[MCPServerConfig] = []
    if not raw or not raw.strip():
        return servers

    for spec in raw.strip().split("|"):
        parts = spec.strip().split(":")
        if len(parts) < 3:
            logger.warning("Invalid MCP server spec (too few parts): %s", spec)
            continue

        transport, name = parts[0].strip(), parts[1].strip()

        if transport == "stdio":
            servers.append(MCPServerConfig(
                name=name,
                transport="stdio",
                command=[p.strip() for p in parts[2:]],
            ))
        elif transport == "sse":
            servers.append(MCPServerConfig(
                name=name,
                transport="sse",
                url=":".join(p.strip() for p in parts[2:]),
            ))
        elif transport == "streamable_http":
            servers.append(MCPServerConfig(
                name=name,
                transport="streamable_http",
                url=":".join(p.strip() for p in parts[2:]),
            ))
        else:
            logger.warning("Unknown MCP transport '%s' for server '%s'", transport, name)

    return servers


def parse_mcp_json(path: str) -> list[MCPServerConfig]:
    """Parse a Claude Desktop-style .mcp.json config file.

    Format:
        {"mcpServers": {"name": {"command": "...", "args": [...], "env": {...}}}}}
    """
    import json as _json

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
    except (FileNotFoundError, _json.JSONDecodeError, OSError):
        return []

    servers_data = data.get("mcpServers", {})
    if not isinstance(servers_data, dict):
        return []

    servers: list[MCPServerConfig] = []
    for name, cfg in servers_data.items():
        if not isinstance(cfg, dict):
            continue
        command = cfg.get("command", "")
        args = cfg.get("args", [])
        env = cfg.get("env")
        url = cfg.get("url")
        server_type = cfg.get("type", "tool")

        # Detect transport from config fields
        if url:
            transport = "sse"  # could be streamable_http, default to sse
            servers.append(MCPServerConfig(
                name=name, transport=transport, url=url,
                env=env if isinstance(env, dict) else None,
                server_type=server_type,
            ))
        elif command:
            full_cmd = [command] + list(args) if args else [command]
            servers.append(MCPServerConfig(
                name=name, transport="stdio", command=full_cmd,
                env={k: str(v) for k, v in env.items()} if isinstance(env, dict) else None,
                server_type=server_type,
            ))

    return servers


def load_mcp_server_configs(
    cwd: str = "", *, path: str | None = None
) -> list[MCPServerConfig]:
    """Load MCP server configs from config files, then fall back to MCP_SERVERS env var.

    When ``path`` is given explicitly, only that file is read before falling
    back to ``MCP_SERVERS``.

    When ``path`` is None (default), the resolution chain is:
        1. ``<cwd>/.pi/mcp/shared.mcp.json``
        2. ``<cwd>/.mcp.json``
        3. ``MCP_SERVERS`` env var
    """
    import os as _os

    search_dir = cwd or _os.getcwd()

    if path is not None:
        configs = parse_mcp_json(path)
        if configs:
            return configs
    else:
        shared_path = _os.path.join(search_dir, ".pi", "mcp", "shared.mcp.json")
        configs = parse_mcp_json(shared_path)
        if configs:
            return configs

        json_path = _os.path.join(search_dir, ".mcp.json")
        configs = parse_mcp_json(json_path)
        if configs:
            return configs

    # Fall back to env var for backward compatibility
    return parse_mcp_servers(_os.environ.get("MCP_SERVERS", ""))


def read_mcp_json_raw(cwd: str = "") -> dict[str, Any]:
    """Read raw .mcp.json content for editing via API."""
    import json as _json
    import os as _os

    search_dir = cwd or _os.getcwd()
    json_path = _os.path.join(search_dir, ".mcp.json")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return _json.load(f)
    except (FileNotFoundError, _json.JSONDecodeError, OSError):
        return {"mcpServers": {}}


def write_mcp_json_raw(data: dict[str, Any], cwd: str = "") -> None:
    """Write .mcp.json file with the given data."""
    import json as _json
    import os as _os

    search_dir = cwd or _os.getcwd()
    json_path = _os.path.join(search_dir, ".mcp.json")
    with open(json_path, "w", encoding="utf-8") as f:
        _json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def add_mcp_server_to_json(
    name: str,
    transport: str,
    *,
    command: str | None = None,
    args: list[str] | None = None,
    url: str | None = None,
    env: dict[str, str] | None = None,
    server_type: str = "tool",
    cwd: str = "",
) -> None:
    """Add or update an MCP server entry in .mcp.json."""
    data = read_mcp_json_raw(cwd)
    data.setdefault("mcpServers", {})

    cfg: dict[str, Any] = {}
    if transport in ("sse", "streamable_http") and url:
        cfg["url"] = url
    elif transport == "stdio" and command:
        cfg["command"] = command
        if args:
            cfg["args"] = args
    if env:
        cfg["env"] = env
    if server_type != "tool":
        cfg["type"] = server_type

    data["mcpServers"][name] = cfg
    write_mcp_json_raw(data, cwd)


def remove_mcp_server_from_json(name: str, cwd: str = "") -> bool:
    """Remove an MCP server entry from .mcp.json. Returns True if found."""
    data = read_mcp_json_raw(cwd)
    servers = data.get("mcpServers", {})
    if name not in servers:
        return False
    del servers[name]
    write_mcp_json_raw(data, cwd)
    return True


# ---------------------------------------------------------------------------
# MCP connection
# ---------------------------------------------------------------------------

class MCPConnection:
    """Manages a single MCP server connection lifecycle."""

    def __init__(
        self,
        *,
        command: list[str] | None = None,
        url: str | None = None,
        transport: str = "",
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        if command is None and url is None:
            raise ValueError("Either 'command' (stdio) or 'url' (SSE/streamable_http) must be provided")
        self._command = command
        self._url = url
        self._transport = transport
        self._env = env
        self._timeout = timeout
        self._session: Any = None
        self._exit_stack: Any = None

    async def connect(self) -> None:
        """Connect to the MCP server and initialize the session."""
        from contextlib import AsyncExitStack

        from mcp import ClientSession

        self._exit_stack = AsyncExitStack()

        if self._transport == "streamable_http":
            from mcp.client.streamable_http import streamable_http_client

            if self._url is None:
                raise RuntimeError("URL is required for streamable HTTP transport")
            read, write, _ = await self._exit_stack.enter_async_context(
                streamable_http_client(self._url)
            )
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await self._session.initialize()
            return

        if self._command is not None:
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client

            params = StdioServerParameters(
                command=self._command[0],
                args=self._command[1:] if len(self._command) > 1 else [],
                env=self._env,
            )
            read, write = await self._exit_stack.enter_async_context(
                stdio_client(params)
            )
        elif self._url is not None:
            from mcp.client.sse import sse_client

            read, write = await self._exit_stack.enter_async_context(
                sse_client(url=self._url)
            )
        else:
            raise RuntimeError("No connection parameters configured")

        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        await self._session.initialize()

    def is_connected(self) -> bool:
        return self._session is not None and self._exit_stack is not None

    async def ping(self) -> bool:
        """Health check — try listing tools. Returns True if healthy."""
        try:
            await self.list_tools()
            return True
        except Exception:
            logger.debug("MCP ping failed", exc_info=True)
            return False

    async def close(self) -> None:
        """Close the MCP server connection."""
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
            self._exit_stack = None
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

    def __init__(self, connection: MCPConnection, tool_def: dict[str, Any], server_name: str = "") -> None:
        self._connection = connection
        self._tool_def = tool_def
        self.server_name = server_name
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
            display = _build_map_display(self._tool_def["name"], text)
            return ToolResult(content=[TextContent(text=text)], display=display)
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


# ---------------------------------------------------------------------------
# MCP manager — multi-server lifecycle
# ---------------------------------------------------------------------------

class MCPManager:
    """Manages multiple MCP server connections and their tool registrations.

    Usage:
        manager = MCPManager(configs)
        await manager.start()
        manager.register_tools(tool_registry)
        # ... agent runs, calling MCP tools ...
        await manager.stop()
    """

    def __init__(self, configs: list[MCPServerConfig] | None = None) -> None:
        self._configs: list[MCPServerConfig] = configs or []
        self._connections: list[MCPConnection] = []
        self._adapters: list[MCPToolAdapter] = []

    @property
    def adapters(self) -> list[MCPToolAdapter]:
        return list(self._adapters)

    @classmethod
    def from_env(cls) -> "MCPManager":
        """Create an MCPManager from MCP_SERVERS env var."""
        configs = load_mcp_server_configs()
        return cls(configs)

    async def start(self) -> None:
        """Connect to all configured MCP servers and discover their tools."""
        for cfg in self._configs:
            try:
                if cfg.transport == "stdio":
                    conn = MCPConnection(
                        command=cfg.command,
                        env=cfg.env or os.environ.copy(),
                        transport="stdio",
                    )
                elif cfg.transport == "sse":
                    conn = MCPConnection(url=cfg.url, env=cfg.env, transport="sse")
                elif cfg.transport == "streamable_http":
                    conn = MCPConnection(url=cfg.url, transport="streamable_http")
                else:
                    logger.warning("Skip unknown transport: %s", cfg.transport)
                    continue

                await conn.connect()
                tool_defs = await conn.list_tools()
                for td in tool_defs:
                    self._adapters.append(MCPToolAdapter(conn, td, server_name=cfg.name))

                self._connections.append(conn)
                logger.info(
                    "MCP server '%s' connected — %d tools discovered",
                    cfg.name, len(tool_defs),
                )
            except Exception:
                logger.exception("Failed to connect MCP server '%s'", cfg.name)

    async def stop(self) -> None:
        """Close all MCP connections."""
        for conn in self._connections:
            try:
                await conn.close()
            except Exception:
                logger.exception("Error closing MCP connection")
        self._connections.clear()
        self._adapters.clear()

    async def check_health(self) -> list[dict[str, Any]]:
        """Ping all connections. Returns health status for each server."""
        results = []
        for i, conn in enumerate(self._connections):
            name = self._configs[i].name if i < len(self._configs) else f"conn-{i}"
            healthy = await conn.ping()
            results.append({"name": name, "healthy": healthy})
        return results

    async def reload(self, cwd: str = "") -> None:
        """Stop all connections and reload configs from .mcp.json."""
        await self.stop()
        self._configs = load_mcp_server_configs(cwd)
        await self.start()

    def get_connector_info(self) -> list[dict[str, Any]]:
        """Return info about each connected MCP server and its tools."""
        from collections import defaultdict

        tools_by_server: dict[str, list[str]] = defaultdict(list)
        for adapter in self._adapters:
            tools_by_server[adapter.server_name].append(adapter.definition.name)

        # Map connection to config for transport info
        config_map = {cfg.name: cfg for cfg in self._configs}

        result = []
        for cfg in self._configs:
            tools = tools_by_server.get(cfg.name, [])
            status = "connected" if tools else "error"
            result.append({
                "name": cfg.name,
                "transport": cfg.transport,
                "status": status,
                "type": cfg.server_type,
                "tools": sorted(tools),
            })
        return result

    def register_tools(self, registry: ToolRegistry) -> int:
        """Register all discovered MCP tools into the given registry.

        If a tool name conflicts with an existing tool, prefix with server_name
        to avoid overwriting. Otherwise keep the original name.
        """
        count = 0
        for adapter in self._adapters:
            name = adapter.definition.name
            if adapter.server_name and (name in registry):
                # Rename on conflict only
                new_name = f"{adapter.server_name}_{name}"
                adapter.definition = ToolDefinition(
                    name=new_name,
                    description=adapter.definition.description,
                    parameters=adapter.definition.parameters,
                )
            registry.register(adapter)
            count += 1
        return count


def _build_map_display(tool_name: str, text: str) -> dict[str, Any] | None:
    """Build an interactive Amap widget for geo / direction results."""
    import html as _html
    import json as _json

    api_key = os.environ.get("AMAP_MAPS_API_KEY", "")
    if not api_key:
        return None

    try:
        data = _json.loads(text)
    except (_json.JSONDecodeError, TypeError):
        return None

    # --- geo / regeocode: single marker ---
    if tool_name in ("maps_geo", "maps_regeocode"):
        items = data.get("return") if isinstance(data.get("return"), list) else [data]
        if items and isinstance(items[0], dict):
            loc = items[0].get("location", "")
            if loc:
                lng, lat = loc.split(",")
                title = _html.escape(
                    items[0].get("name") or items[0].get("address", "") or items[0].get("district", "") or loc
                )
                return {
                    "widget": {
                        "title": f"地图: {title}",
                        "html": _INTERACTIVE_MARKER_HTML.format(
                            key=api_key, lng=lng, lat=lat, title=title, zoom=14,
                        ),
                        "height": 400,
                    }
                }

    # --- direction tools: interactive map with origin/destination markers ---
    if tool_name in ("maps_direction_driving", "maps_direction_walking",
                     "maps_bicycling", "maps_direction_transit_integrated"):
        route = data.get("route", {})
        origin_coord = (route.get("origin") or "").strip()
        dest_coord = (route.get("destination") or "").strip()
        if not origin_coord or not dest_coord:
            return None
        origin_lng, origin_lat = origin_coord.split(",")
        dest_lng, dest_lat = dest_coord.split(",")
        return {
            "widget": {
                "title": "路线地图",
                "html": _INTERACTIVE_ROUTE_HTML.format(
                    key=api_key,
                    origin_lng=origin_lng, origin_lat=origin_lat,
                    dest_lng=dest_lng, dest_lat=dest_lat,
                ),
                "height": 400,
            }
        }

    return None


_INTERACTIVE_MARKER_HTML = """\
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>html,body{{margin:0;padding:0;width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:#f5f3f0}}
img{{max-width:100%;max-height:100%;object-fit:contain;border-radius:8px}}</style>
</head><body>
<img src="https://restapi.amap.com/v3/staticmap?key={key}&location={lng},{lat}&zoom={zoom}&size=600*300&scale=2&markers=mid,0xFF0000,A:{lng},{lat}" alt="map" style="width:100%" />
</body></html>"""

_INTERACTIVE_ROUTE_HTML = """\
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>html,body{{margin:0;padding:0;width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:#f5f3f0}}
img{{max-width:100%;max-height:100%;object-fit:contain;border-radius:8px}}</style>
</head><body>
<img src="https://restapi.amap.com/v3/staticmap?key={key}&size=600*300&scale=2&markers=mid,0xFF0000,A:{origin_lng},{origin_lat}|mid,0x3388FF,B:{dest_lng},{dest_lat}" alt="map" style="width:100%" />
</body></html>"""


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
