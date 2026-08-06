"""Tests for scoped connectors (shared vs per-agent) — Task 4.2.

Covers:
- mcp_tool writers resolve like the loader: with a ``.pi/mcp/shared.mcp.json``
  present, ``add/remove_mcp_server_to_json(cwd=...)`` target the shared file and
  leave the legacy root ``.mcp.json`` alone; without one they target root.
- ``add/remove_mcp_server_to_json(..., path=...)`` write an explicit file
  (used for the per-agent ``.pi/mcp/agents/<id>.mcp.json`` scope).
- ``MCPPool.reload_private`` drops the cached manager, stops it, and reloads
  from disk so connector edits take effect.
- server.py connector scope helpers (``_connector_scope_error`` /
  ``_agent_mcp_path``) and the agent-scoped POST route writing the agent file.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from agent_core.tools.mcp_pool import MCPPool
from agent_core.tools.mcp_tool import (
    add_mcp_server_to_json,
    remove_mcp_server_from_json,
)

# server.py calls load_dotenv() at import time, which can leak .env values
# (e.g. AGENT_PROVIDER=deepseek) into the process env and break sibling scene
# tests that rely on the openai default. Snapshot and restore the provider env
# so this module's import is side-effect-free for the rest of the suite.
_saved_provider_env = {k: os.environ.get(k) for k in ("AGENT_PROVIDER", "AGENT_MODEL", "AGENT_API_KEY_ENV")}

from scene.http_sse.server import (  # noqa: E402
    _agent_mcp_path,
    _connector_scope_error,
)

for _k, _v in _saved_provider_env.items():
    if _v is None:
        os.environ.pop(_k, None)
    else:
        os.environ[_k] = _v
del _k, _v, _saved_provider_env


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path, servers: dict) -> None:
    path = str(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"mcpServers": servers}, f)


def _read(path) -> dict:
    with open(str(path), "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# mcp_tool writers resolve like the loader
# ---------------------------------------------------------------------------

def test_add_prefers_shared_over_root(tmp_path):
    shared = tmp_path / ".pi" / "mcp" / "shared.mcp.json"
    _write(shared, {"existing": {"command": "echo", "args": ["hi"]}})
    root = tmp_path / ".mcp.json"

    add_mcp_server_to_json(
        "new-srv", "stdio", command="python", args=["-m", "demo"], cwd=str(tmp_path),
    )

    assert not root.exists()  # legacy root untouched/absent
    data = _read(shared)
    assert "new-srv" in data["mcpServers"]
    assert data["mcpServers"]["existing"]["command"] == "echo"  # preserved


def test_add_falls_back_to_root_when_no_shared(tmp_path):
    add_mcp_server_to_json(
        "srv", "sse", url="http://localhost:8080/sse", cwd=str(tmp_path),
    )

    data = _read(tmp_path / ".mcp.json")
    assert data["mcpServers"]["srv"] == {"url": "http://localhost:8080/sse"}


def test_remove_prefers_shared_over_root(tmp_path):
    shared = tmp_path / ".pi" / "mcp" / "shared.mcp.json"
    _write(shared, {"a": {"command": "echo", "args": []}, "b": {"command": "echo", "args": []}})

    assert remove_mcp_server_from_json("a", cwd=str(tmp_path)) is True
    assert "a" not in _read(shared)["mcpServers"]
    assert "b" in _read(shared)["mcpServers"]
    assert not (tmp_path / ".mcp.json").exists()

    assert remove_mcp_server_from_json("a", cwd=str(tmp_path)) is False  # idempotent


def test_explicit_path_writes_agent_file(tmp_path):
    agent_path = str(tmp_path / ".pi" / "mcp" / "agents" / "support.mcp.json")

    add_mcp_server_to_json(
        "crm", "stdio", command="python", args=["-m", "crm_server"], path=agent_path,
    )
    assert "crm" in _read(agent_path)["mcpServers"]

    assert remove_mcp_server_from_json("crm", path=agent_path) is True
    assert "crm" not in _read(agent_path)["mcpServers"]
    assert remove_mcp_server_from_json("crm", path=agent_path) is False


# ---------------------------------------------------------------------------
# MCPPool.reload_private
# ---------------------------------------------------------------------------

class StubAdapter:
    def __init__(self, name, server_name=""):
        from agent_core.tools.base import ToolDefinition
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


def _shared():
    return StubManager()


@pytest.fixture(autouse=True)
def _no_env_servers(monkeypatch):
    """Isolate ensure_private/reload_private from any ambient MCP_SERVERS env."""
    monkeypatch.setenv("MCP_SERVERS", "")


async def test_reload_private_reloads_and_stops_old_manager(tmp_path):
    agent_file = tmp_path / ".pi" / "mcp" / "agents" / "x.mcp.json"
    _write(agent_file, {"s1": {"command": "echo", "args": []}})

    received = []

    def factory(configs):
        received.append([c.name for c in configs])
        return StubManager([_a(c.name, "priv") for c in configs])

    pool = MCPPool(shared=_shared(), cwd=str(tmp_path), manager_factory=factory)

    m1 = await pool.ensure_private("x")
    assert [a.definition.name for a in m1.adapters] == ["s1"]

    # Change the config on disk, then reload.
    _write(agent_file, {"s2": {"command": "echo", "args": []}})
    m2 = await pool.reload_private("x")

    assert m2 is not m1
    assert [a.definition.name for a in m2.adapters] == ["s2"]
    assert received == [["s1"], ["s2"]]
    assert m1.stop_calls == 1  # old manager was stopped
    assert pool._private["x"] is m2


async def test_reload_private_with_no_cache_loads_once(tmp_path):
    agent_file = tmp_path / ".pi" / "mcp" / "agents" / "x.mcp.json"
    _write(agent_file, {"s1": {"command": "echo", "args": []}})

    received = []

    def factory(configs):
        received.append([c.name for c in configs])
        return StubManager([_a(c.name, "priv") for c in configs])

    pool = MCPPool(shared=_shared(), cwd=str(tmp_path), manager_factory=factory)

    m = await pool.reload_private("x")
    assert [a.definition.name for a in m.adapters] == ["s1"]
    assert received == [["s1"]]


# ---------------------------------------------------------------------------
# server.py scope helpers + agent-scoped POST route
# ---------------------------------------------------------------------------

def test_connector_scope_validation():
    assert _connector_scope_error("shared", "") is None
    assert _connector_scope_error("shared", "anything") is None
    assert _connector_scope_error("agent", "support") is None
    assert _connector_scope_error("agent", "") is not None
    assert _connector_scope_error("agent", "bad id!") is not None
    assert _connector_scope_error("tenant", "") is not None


def test_agent_mcp_path(monkeypatch, tmp_path):
    from scene.http_sse.manager import SessionManager
    import scene.http_sse.server as server_module

    monkeypatch.setattr(server_module, "manager", SessionManager(cwd=str(tmp_path), session_store_dir=str(tmp_path)))
    assert _agent_mcp_path("support") == str(
        tmp_path / ".pi" / "mcp" / "agents" / "support.mcp.json"
    )


async def test_add_connector_agent_scope_writes_agent_file(monkeypatch, tmp_path):
    from starlette.datastructures import QueryParams

    from scene.http_sse.manager import SessionManager
    import scene.http_sse.server as server_module

    monkeypatch.setattr(server_module, "manager", SessionManager(cwd=str(tmp_path), session_store_dir=str(tmp_path)))

    body = server_module.ConnectorRequest(
        name="crm", transport="stdio", command="python", args=["-m", "crm_server"],
    )
    req = SimpleNamespace(query_params=QueryParams({"scope": "agent", "agent_id": "support"}))

    result = await server_module.add_connector(req, body)

    assert result == {"success": True}
    agent_file = tmp_path / ".pi" / "mcp" / "agents" / "support.mcp.json"
    assert agent_file.exists()
    assert "crm" in _read(agent_file)["mcpServers"]


async def test_add_connector_agent_scope_rejects_bad_agent_id(monkeypatch, tmp_path):
    from starlette.datastructures import QueryParams

    from scene.http_sse.manager import SessionManager
    import scene.http_sse.server as server_module

    monkeypatch.setattr(server_module, "manager", SessionManager(cwd=str(tmp_path), session_store_dir=str(tmp_path)))

    body = server_module.ConnectorRequest(name="crm", transport="stdio", command="python")
    req = SimpleNamespace(query_params=QueryParams({"scope": "agent", "agent_id": "bad id!"}))

    result = await server_module.add_connector(req, body)

    assert result["success"] is False
    assert "agent_id" in result["error"]
    assert not (tmp_path / ".pi" / "mcp" / "agents").exists()
