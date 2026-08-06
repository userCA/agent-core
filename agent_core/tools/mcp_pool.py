"""MCPPool — shared + per-agent private MCP manager pool.

One shared :class:`MCPManager` holds servers available to every agent.
Per-agent private managers are created lazily from
``<cwd>/.pi/mcp/agents/<agent_id>.mcp.json`` and cached so repeated lookups
don't re-read the file.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable

from agent_core.resources.agents import AgentDefinition
from agent_core.tools.base import ToolRegistry
from agent_core.tools.mcp_tool import (
    MCPManager,
    MCPServerConfig,
    MCPToolAdapter,
    parse_mcp_json,
)

logger = logging.getLogger(__name__)


class MCPPool:
    """Pool of shared + private MCP managers, filtered per agent.

    Selection semantics (see plan §1.1 / §1.4):

    - ``agent.tools is None`` — unrestricted: include **all** shared
      adapters. Private adapters from ``tools.private_mcp`` are never
      included (knowledge-private servers still apply).
    - ``agent.tools.shared_mcp`` — include only shared adapters whose
      ``.server_name`` is listed.
    - ``agent.tools.private_mcp`` — include only the agent's private
      adapters whose ``.server_name`` is listed.
    - Knowledge servers — shared adapters in
      ``knowledge.shared_mcp_knowledge`` and private adapters in
      ``knowledge.private_mcp_knowledge`` are also included.

    Private adapters are registered after shared ones, so on tool-name
    conflict the private adapter wins (a warning is logged).
    """

    def __init__(
        self,
        *,
        shared: MCPManager,
        cwd: str = "",
        manager_factory: Callable[[list[MCPServerConfig]], MCPManager] = MCPManager,
    ) -> None:
        self._shared = shared
        self._cwd = cwd
        self._manager_factory = manager_factory
        self._private: dict[str, MCPManager] = {}
        # Single-flight locks so concurrent ensure_private calls for the same
        # agent_id only build + start one manager.
        self._locks: dict[str, asyncio.Lock] = {}

    @property
    def shared(self) -> MCPManager:
        """The shared MCP manager holding servers available to every agent."""
        return self._shared

    async def start_shared(self) -> None:
        """Start the shared MCP manager."""
        await self._shared.start()

    async def ensure_private(self, agent_id: str) -> MCPManager:
        """Load ``.pi/mcp/agents/<agent_id>.mcp.json`` if needed.

        Returns the cached manager for ``agent_id`` if already loaded;
        otherwise loads configs from disk, starts the manager, and caches
        it. Empty results are cached too, so repeated calls don't re-read
        the file.

        Concurrent calls for the same ``agent_id`` are serialized so only
        one manager is created and started.
        """
        existing = self._private.get(agent_id)
        if existing is not None:
            return existing

        lock = self._locks.setdefault(agent_id, asyncio.Lock())
        async with lock:
            # Another coroutine may have created it while we waited on the lock.
            existing = self._private.get(agent_id)
            if existing is not None:
                return existing

            # Strict private loading: read only the agent's own config file.
            # No MCP_SERVERS env fallback — a private agent without a config
            # file must not inherit global env servers.
            path = os.path.join(
                self._cwd, ".pi", "mcp", "agents", f"{agent_id}.mcp.json"
            )
            configs = parse_mcp_json(path)
            manager = self._manager_factory(configs)
            if configs:
                await manager.start()
            self._private[agent_id] = manager
            return manager

    async def reload_private(self, agent_id: str) -> MCPManager:
        """Drop and reload an agent's private MCP manager from disk.

        Stops and removes any cached manager for ``agent_id``, then reloads via
        ``ensure_private`` so connector edits on ``.pi/mcp/agents/<id>.mcp.json``
        take effect.
        """
        manager = self._private.pop(agent_id, None)
        if manager is not None:
            await manager.stop()
        return await self.ensure_private(agent_id)

    def adapters_for_agent(self, agent: AgentDefinition) -> list[MCPToolAdapter]:
        """Union of shared∩shared_mcp and private∩private_mcp (+ knowledge servers).

        Precondition: ``ensure_private(agent.id)`` must be called first so
        the agent's private manager exists. This method is synchronous and
        does NOT lazily load private configs; if the private manager is
        absent it is silently skipped.

        Shared adapters come first, then private ones, so registering in
        this order lets private adapters overwrite shared adapters by name.
        """
        adapters: list[MCPToolAdapter] = []
        seen: set[int] = set()
        shared_adapters = self._shared.adapters

        def _append(adapter: MCPToolAdapter) -> None:
            if id(adapter) in seen:
                return
            seen.add(id(adapter))
            adapters.append(adapter)

        # Shared — tools-based selection.
        if agent.tools is None:
            for adapter in shared_adapters:
                _append(adapter)
        else:
            names = set(agent.tools.shared_mcp)
            for adapter in shared_adapters:
                if adapter.server_name in names:
                    _append(adapter)

        # Shared — knowledge servers.
        if agent.knowledge is not None:
            names = set(agent.knowledge.shared_mcp_knowledge)
            for adapter in shared_adapters:
                if adapter.server_name in names:
                    _append(adapter)

        # Private adapters.
        private = self._private.get(agent.id)
        if private is not None:
            private_adapters = private.adapters
            if agent.tools is not None:
                names = set(agent.tools.private_mcp)
                for adapter in private_adapters:
                    if adapter.server_name in names:
                        _append(adapter)
            if agent.knowledge is not None:
                names = set(agent.knowledge.private_mcp_knowledge)
                for adapter in private_adapters:
                    if adapter.server_name in names:
                        _append(adapter)

        return adapters

    def register_tools(self, registry: ToolRegistry, agent: AgentDefinition) -> int:
        """Register the agent's MCP tools into ``registry``.

        Precondition: ``ensure_private(agent.id)`` must be called first
        (see :meth:`adapters_for_agent`); private configs are not lazily
        loaded here.

        Shared adapters are registered first, then private ones. When a
        name is already present the previous tool is overwritten and a
        warning is logged. Returns the number of tools registered.
        """
        count = 0
        for adapter in self.adapters_for_agent(agent):
            name = adapter.definition.name
            if name in registry:
                logger.warning(
                    "Overwriting existing tool '%s' with MCP tool from server '%s'",
                    name,
                    adapter.server_name,
                )
            registry.register(adapter)
            count += 1
        return count

    async def stop(self) -> None:
        """Stop the shared manager and all private managers."""
        await self._shared.stop()
        for manager in self._private.values():
            await manager.stop()
