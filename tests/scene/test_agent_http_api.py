"""Scene-level tests for the /agents API and agent_id on chat/sessions.

Covers:
- resolve_agent_request (agent_id priority, persona->agent aliasing, V6 compat)
- SessionManager.get_or_create(agent_id=...): header.agent_id + _agent_id
- PermissionError when accessing a session with a different agent
- list_sessions(agent_id=...) filtering
- V6 persona-only compat (no AgentDefinition synthesized)
- unknown agent_id -> ValueError (manager) / (None, agent_id) (resolver)

Uses the tmp-cwd + no-real-MCP pattern from test_agent_mcp_wiring.py.
"""

from __future__ import annotations

import json
import os

import pytest

from agent_core.resources.agents import AgentDefinition, AgentKnowledge, save_agent
from agent_core.session.inmemory_store import InMemoryStore
from scene.http_sse.chat_assistant import ChatAssistant
from scene.http_sse.manager import SessionManager

# server.py calls load_dotenv() at import time, which can leak .env values
# (e.g. AGENT_PROVIDER=deepseek) into the process env and break sibling scene
# tests that rely on the openai default. Snapshot and restore the provider env
# so this module's import is side-effect-free for the rest of the suite.
_saved_provider_env = {k: os.environ.get(k) for k in ("AGENT_PROVIDER", "AGENT_MODEL", "AGENT_API_KEY_ENV")}

from scene.http_sse.server import resolve_agent_request  # noqa: E402

for _k, _v in _saved_provider_env.items():
    if _v is None:
        os.environ.pop(_k, None)
    else:
        os.environ[_k] = _v
del _k, _v, _saved_provider_env


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _agent(aid: str) -> AgentDefinition:
    return AgentDefinition(
        id=aid,
        name=aid.upper(),
        description="",
        system_prompt=f"You are {aid}",
        knowledge=AgentKnowledge(),
    )


def _write_persona(cwd: str, pid: str) -> None:
    path = os.path.join(cwd, ".pi", "personas", f"{pid}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "id": pid,
            "name": pid,
            "description": "",
            "system_prompt": f"You are persona {pid}",
        }, f)


def _manager(cwd: str, store_dir: str | None = None) -> SessionManager:
    return SessionManager(cwd=cwd, session_store_dir=store_dir or str(cwd))


async def _create_agent_session(mgr: SessionManager, agent_id: str, owner: str = "u1"):
    return await mgr.get_or_create(
        None, agent_id=agent_id, owner=owner,
        provider_name="openai", model_id="gpt-4o",
    )


# ---------------------------------------------------------------------------
# resolve_agent_request
# ---------------------------------------------------------------------------

def test_resolve_agent_request_agent_id(tmp_path):
    cwd = str(tmp_path)
    save_agent(_agent("support"), cwd=cwd)
    agent, effective = resolve_agent_request("support", None, cwd)
    assert agent is not None
    assert agent.id == "support"
    assert effective == "support"


def test_resolve_agent_request_unknown_agent(tmp_path):
    cwd = str(tmp_path)
    # Contract: unknown agent_id -> (None, agent_id) so callers can surface a
    # "not found" error while the manager raises ValueError on get_or_create.
    agent, effective = resolve_agent_request("nope", None, cwd)
    assert agent is None
    assert effective == "nope"


def test_resolve_agent_request_persona_aliases_agent(tmp_path):
    cwd = str(tmp_path)
    save_agent(_agent("coder"), cwd=cwd)
    # persona_id that aliases an existing agent -> the agent wins.
    agent, effective = resolve_agent_request(None, "coder", cwd)
    assert agent is not None
    assert agent.id == "coder"
    assert effective == "coder"


def test_resolve_agent_request_persona_no_matching_agent(tmp_path):
    cwd = str(tmp_path)
    _write_persona(cwd, "coder")
    # persona with no matching agent -> no agent resolved (V6 persona path).
    agent, effective = resolve_agent_request(None, "coder", cwd)
    assert agent is None
    assert effective is None


def test_resolve_agent_request_neither(tmp_path):
    agent, effective = resolve_agent_request(None, None, str(tmp_path))
    assert agent is None
    assert effective is None


# ---------------------------------------------------------------------------
# SessionManager agent binding
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_or_create_agent_writes_header_agent_id(tmp_path):
    cwd = str(tmp_path)
    save_agent(_agent("support"), cwd=cwd)
    mgr = _manager(cwd)
    try:
        sid, assistant = await _create_agent_session(mgr, "support")
        assert assistant._agent_id == "support"
        snap = await mgr._store.load_session(sid)
        assert snap.header.agent_id == "support"
        assert snap.header.owner == "u1"
    finally:
        await mgr.dispose_all()


@pytest.mark.asyncio
async def test_get_or_create_different_agent_permission_error(tmp_path):
    cwd = str(tmp_path)
    save_agent(_agent("support"), cwd=cwd)
    save_agent(_agent("coder"), cwd=cwd)
    mgr = _manager(cwd)
    try:
        sid, _ = await _create_agent_session(mgr, "support")
        # An existing session is bound to "support"; requesting "coder" must fail.
        with pytest.raises(PermissionError):
            await mgr.get_or_create(
                sid, agent_id="coder", owner="u1",
                provider_name="openai", model_id="gpt-4o",
            )
    finally:
        await mgr.dispose_all()


@pytest.mark.asyncio
async def test_get_or_create_unknown_agent_raises(tmp_path):
    cwd = str(tmp_path)
    mgr = _manager(cwd)
    try:
        # Building a NEW assistant with an unknown agent_id is a ValueError.
        with pytest.raises(ValueError):
            await mgr.get_or_create(None, agent_id="nope", owner="u1")
    finally:
        await mgr.dispose_all()


@pytest.mark.asyncio
async def test_existing_session_unknown_agent_fails_closed(tmp_path):
    """Issue 1: reading an existing agent-bound session with an unknown
    agent_id fails closed with PermissionError, never ValueError/500."""
    cwd = str(tmp_path)
    save_agent(_agent("support"), cwd=cwd)
    mgr = _manager(cwd)
    try:
        sid, _ = await _create_agent_session(mgr, "support")
        with pytest.raises(PermissionError):
            await mgr.get_or_create(
                sid, agent_id="nope", owner="u1",
                provider_name="openai", model_id="gpt-4o",
            )
    finally:
        await mgr.dispose_all()


@pytest.mark.asyncio
async def test_existing_legacy_session_unknown_agent_fails_closed(tmp_path):
    """Issue 1: an unknown agent_id on a legacy (unbound) session also fails
    closed (PermissionError), never ValueError/500."""
    cwd = str(tmp_path)
    _write_persona(cwd, "coder")
    mgr = _manager(cwd)
    try:
        sid, _ = await mgr.get_or_create(
            None, persona_id="coder", owner="u1",
            provider_name="openai", model_id="gpt-4o",
        )
        with pytest.raises(PermissionError):
            await mgr.get_or_create(
                sid, agent_id="nope", owner="u1",
                provider_name="openai", model_id="gpt-4o",
            )
    finally:
        await mgr.dispose_all()


@pytest.mark.asyncio
async def test_agent_bound_session_reused_on_plain_access(tmp_path):
    """A plain get_or_create(sid) (no agent/persona) must REUSE an agent-bound
    session instead of rebuilding it as a no-agent session."""
    cwd = str(tmp_path)
    save_agent(_agent("support"), cwd=cwd)
    mgr = _manager(cwd)
    try:
        sid, assistant = await _create_agent_session(mgr, "support")
        sid2, assistant2 = await mgr.get_or_create(
            sid, owner="u1", provider_name="openai", model_id="gpt-4o",
        )
        assert sid2 == sid
        assert assistant2 is assistant
        assert assistant._agent_id == "support"
    finally:
        await mgr.dispose_all()


@pytest.mark.asyncio
async def test_persona_request_cannot_rebind_agent_session(tmp_path):
    """Issue 2: a persona-only request on an agent-bound session raises
    PermissionError and does NOT dispose/rebind the session."""
    cwd = str(tmp_path)
    save_agent(_agent("support"), cwd=cwd)
    _write_persona(cwd, "coder")
    mgr = _manager(cwd)
    try:
        sid, assistant = await mgr.get_or_create(
            None, agent_id="support", owner="u1",
            provider_name="openai", model_id="gpt-4o",
        )
        with pytest.raises(PermissionError):
            await mgr.get_or_create(
                sid, persona_id="coder", owner="u1",
                provider_name="openai", model_id="gpt-4o",
            )
        # Session was NOT disposed/rebound; still the same assistant.
        assert mgr._sessions.get(sid) is assistant
        # Store binding unchanged.
        snap = await mgr._store.load_session(sid)
        assert snap.header.agent_id == "support"
    finally:
        await mgr.dispose_all()


@pytest.mark.asyncio
async def test_delete_respects_agent_binding(tmp_path):
    """Issue 1: deleting an agent-bound session with a wrong/unknown agent_id
    is blocked (PermissionError, no ValueError/500); the matching agent works."""
    cwd = str(tmp_path)
    save_agent(_agent("support"), cwd=cwd)
    mgr = _manager(cwd)
    try:
        sid, _ = await mgr.get_or_create(
            "sess-s", agent_id="support", owner="u1",
            provider_name="openai", model_id="gpt-4o",
        )
        with pytest.raises(PermissionError):
            await mgr.delete_session(sid, owner="u1", agent_id="nope")
        # Session survives the blocked delete.
        assert (await mgr._store.load_session(sid)).header.agent_id == "support"
        assert await mgr.delete_session(sid, owner="u1", agent_id="support") is True
    finally:
        await mgr.dispose_all()


@pytest.mark.asyncio
async def test_list_sessions_filters_by_agent(tmp_path):
    cwd = str(tmp_path)
    save_agent(_agent("support"), cwd=cwd)
    save_agent(_agent("coder"), cwd=cwd)
    mgr = _manager(cwd)
    try:
        sid_a, _ = await mgr.get_or_create(
            "sess-support", agent_id="support", owner="u1",
            provider_name="openai", model_id="gpt-4o",
        )
        sid_b, _ = await mgr.get_or_create(
            "sess-coder", agent_id="coder", owner="u1",
            provider_name="openai", model_id="gpt-4o",
        )
        metas = await mgr.list_sessions(owner="u1", agent_id="support")
        ids = {m.session_id for m in metas}
        assert sid_a in ids
        assert sid_b not in ids
        assert all(m.agent_id == "support" for m in metas)
    finally:
        await mgr.dispose_all()


# ---------------------------------------------------------------------------
# V6 persona compat
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persona_compat_no_agent_synthesized(tmp_path):
    cwd = str(tmp_path)
    _write_persona(cwd, "coder")
    mgr = _manager(cwd)
    try:
        sid, assistant = await mgr.get_or_create(
            None, persona_id="coder", owner="u1",
            provider_name="openai", model_id="gpt-4o",
        )
        assert assistant._persona_id == "coder"
        assert getattr(assistant, "_agent_id", None) is None
        # No agent binding check fires on the persona path.
        snap = await mgr._store.load_session(sid)
        assert snap.header.agent_id == ""

        # Reuse is stable (no spurious rebuild on identical persona requests).
        sid2, assistant2 = await mgr.get_or_create(
            sid, persona_id="coder", owner="u1",
            provider_name="openai", model_id="gpt-4o",
        )
        assert sid2 == sid
        assert assistant2 is assistant
    finally:
        await mgr.dispose_all()


# ---------------------------------------------------------------------------
# ChatAssistant.create header
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_assistant_create_records_agent_id_header(tmp_path):
    cwd = str(tmp_path)
    agent = _agent("support")
    store = InMemoryStore()
    assistant = await ChatAssistant.create(
        session_store=store,
        session_id="sa",
        cwd=cwd,
        agent=agent,
        owner="u1",
        enable_multi_agent=False,
    )
    try:
        assert assistant._agent is agent
        snap = await store.load_session("sa")
        assert snap.header.agent_id == "support"
    finally:
        await assistant.dispose()


# ---------------------------------------------------------------------------
# Agent id path-traversal hardening (Issue 2)
# ---------------------------------------------------------------------------

async def test_post_agents_rejects_path_traversal_id(tmp_path, monkeypatch):
    """POST /agents with an id that escapes .pi/agents/ is rejected (422) and
    nothing is written to disk."""
    from httpx import ASGITransport, AsyncClient

    from scene.http_sse import server as server_mod

    monkeypatch.setattr(server_mod.manager, "_cwd", str(tmp_path))
    transport = ASGITransport(app=server_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/agents", json={
            "id": "../x",
            "name": "X",
            "description": "",
            "system_prompt": "",
        })
    assert resp.status_code == 422
    agents_dir = tmp_path / ".pi" / "agents"
    assert not agents_dir.exists() or not list(agents_dir.glob("*.json"))


async def test_delete_agents_rejects_path_traversal_id(tmp_path, monkeypatch):
    """DELETE /agents with a traversal id is refused and unlinks nothing."""
    from httpx import ASGITransport, AsyncClient

    from scene.http_sse import server as server_mod

    monkeypatch.setattr(server_mod.manager, "_cwd", str(tmp_path))
    # A decoy file OUTSIDE .pi/agents/ that a traversal would unlink.
    decoy = tmp_path / "pwned.json"
    decoy.write_text("{}")
    transport = ASGITransport(app=server_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete("/agents", params={"id": "../../pwned"})
    assert resp.status_code == 200
    assert resp.json() == {"success": False, "error": "Invalid agent id"}
    assert decoy.exists()


async def test_post_agents_accepts_safe_id(tmp_path, monkeypatch):
    """A well-formed id still round-trips through POST /agents."""
    from httpx import ASGITransport, AsyncClient

    from scene.http_sse import server as server_mod

    monkeypatch.setattr(server_mod.manager, "_cwd", str(tmp_path))
    transport = ASGITransport(app=server_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/agents", json={
            "id": "good_agent-1",
            "name": "Good",
            "description": "",
            "system_prompt": "",
        })
    assert resp.status_code == 200
    assert resp.json() == {"success": True}
    assert (tmp_path / ".pi" / "agents" / "good_agent-1.json").exists()
