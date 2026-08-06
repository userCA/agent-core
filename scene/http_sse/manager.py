"""Session manager for the HTTP SSE chat scene.

Note: Concurrent access to the same session_id is not fully serialized.
This is acceptable for a demo scene; production would need a more robust
session lifecycle (e.g., tracking creation-in-progress futures).
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any

from agent_core.resources.agents import get_agent
from agent_core.resources.personas import get_persona
from agent_core.tools.mcp_pool import MCPPool
from agent_core.tools.mcp_tool import MCPManager
from agent_core.session.factory import create_session_store
from agent_core.session.store import SessionMeta, SessionStore

from scene.http_sse.chat_assistant import ChatAssistant


_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _generate_session_id() -> str:
    return f"scene-{int(time.time() * 1000)}"


def _validate_session_id(sid: str) -> None:
    if not _SESSION_ID_RE.match(sid):
        raise ValueError(f"Invalid session_id: {sid}")


class SessionManager:
    """Manages ChatAssistant instances and their persistent storage."""

    def __init__(
        self,
        *,
        cwd: str = "",
        session_store_dir: str = "./sessions",
    ) -> None:
        self._cwd = cwd or os.getcwd()
        self._store_dir = session_store_dir
        self._store: SessionStore = create_session_store(directory=session_store_dir)
        self._sessions: dict[str, ChatAssistant] = {}
        self._session_owners: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._create_locks: dict[str, asyncio.Lock] = {}
        self._mcp_manager: MCPManager | None = None
        self._mcp_pool: MCPPool | None = None

    async def start(self) -> None:
        """Pre-load MCP tools and warm up embedding model at startup."""
        import logging
        _log = logging.getLogger(__name__)
        self._mcp_manager = MCPManager.from_env()
        self._mcp_pool = MCPPool(shared=self._mcp_manager, cwd=self._cwd)
        await self._mcp_pool.start_shared()
        if len(self._mcp_manager.adapters) > 0:
            _log.info("MCP tools pre-loaded: %d tools", len(self._mcp_manager.adapters))
        # Pre-download/warm embedding model in background (avoids first-request lag)
        try:
            import asyncio
            from agent_core.knowledge.local_kb import _get_model
            await asyncio.to_thread(_get_model)
            _log.info("Embedding model ready")
        except Exception:
            _log.warning("Embedding model warm-up failed (pip install sentence-transformers?)")

    @staticmethod
    def _should_rebuild(
        existing: ChatAssistant,
        persona_id: str | None,
        agent_id: str | None,
        provider_name: str | None,
        model_id: str | None,
    ) -> bool:
        """Return True only when the caller explicitly requests a different config.

        ``persona_id`` / ``agent_id`` are the EFFECTIVE values (agent wins over
        persona). A ``None`` value means "no change requested" for that
        dimension, so an agent-bound session is not spuriously rebuilt by a
        plain access that omits both.
        """
        current_pid = getattr(existing, '_persona_id', None)
        current_agent_id = getattr(existing, '_agent_id', None)
        current_provider = getattr(existing, '_provider_name', None)
        current_model = getattr(existing, '_model_id', None)
        if persona_id is not None and current_pid != persona_id:
            return True
        if agent_id is not None and current_agent_id != agent_id:
            return True
        if provider_name is not None and current_provider != provider_name:
            return True
        if model_id is not None and current_model != model_id:
            return True
        return False

    @staticmethod
    def _assert_rebind_allowed(
        existing: ChatAssistant, session_id: str, requested_agent_id: str | None
    ) -> None:
        """Guard against rebuilding an agent-bound session into a different agent.

        An existing session bound to an agent may only be rebuilt when the SAME
        agent is requested (e.g. a provider/model change). A request whose
        effective agent differs — including a persona-only request where no
        agent is resolved — must fail closed rather than silently rebind the
        session. Rebinding to another agent requires a new session.
        """
        bound_agent = getattr(existing, '_agent_id', None)
        if bound_agent and bound_agent != requested_agent_id:
            raise PermissionError(f"Session {session_id} bound to agent {bound_agent}")

    async def _assert_owner(
        self, session_id: str, owner: str, agent_id: str | None = None
    ) -> None:
        known = self._session_owners.get(session_id)
        if known is not None and known != owner:
            raise PermissionError(f"Session {session_id} not owned by caller")
        header_agent: str | None = None
        session_exists = known is not None
        if known is None:
            try:
                snap = await self._store.load_session(session_id)
                session_exists = True
                header_owner = getattr(snap.header, "owner", "") or ""
                header_agent = getattr(snap.header, "agent_id", "") or ""
                if header_owner and header_owner != owner:
                    raise PermissionError(f"Session {session_id} not owned by caller")
                if header_owner:
                    self._session_owners[session_id] = header_owner
            except KeyError:
                pass
        elif agent_id:
            try:
                snap = await self._store.load_session(session_id)
                header_agent = getattr(snap.header, "agent_id", "") or ""
            except KeyError:
                session_exists = False
        # Agent binding: an existing session may only be accessed with the same
        # agent it was created with. A legacy session (no agent_id recorded)
        # cannot be attributed to an agent. New sessions (not yet in the store)
        # are never blocked here.
        if agent_id and session_exists:
            if not header_agent:
                raise PermissionError(
                    f"Session {session_id} not bound to an agent"
                )
            if header_agent != agent_id:
                raise PermissionError(
                    f"Session {session_id} bound to a different agent"
                )

    async def get_or_create(
        self, session_id: str | None, persona_id: str | None = None,
        agent_id: str | None = None,
        provider_name: str | None = None, model_id: str | None = None,
        companion_queue: "asyncio.Queue[Any] | None" = None,
        companion_uid: str = "",
        owner: str = "anonymous",
    ) -> tuple[str, ChatAssistant]:
        """Get an existing assistant or create a new one.

        ``agent_id`` wins over ``persona_id``. When only ``persona_id`` is given
        and it aliases an existing AgentDefinition, that agent is used (V6
        persona-only clients keep working while honoring agent config). When
        no agent is resolved, ``persona_id`` is passed through to the legacy
        persona path below.

        A synthesized AgentDefinition is deliberately NOT built from a Persona:
        Persona.enabled_tools is a flat whitelist of tool NAMES (incl. MCP tool
        names) while AgentDefinition.tools selects MCP SERVERs, so a synthesis
        would silently drop MCP tools. The persona fallback preserves V6.

        An unknown ``agent_id`` is NOT an error up front: for an existing
        session it flows through the raw-string binding check in ``_assert_owner``
        (fails closed), and only raises ``ValueError`` when we actually have to
        build a new assistant (chat path).
        """
        # Resolve agent/persona once. agent_id wins; a persona_id that aliases
        # an existing agent is treated as that agent.
        agent = None
        persona = None
        if agent_id:
            agent = get_agent(agent_id, cwd=self._cwd)
        elif persona_id:
            agent = get_agent(persona_id, cwd=self._cwd)
            if agent is None:
                persona = get_persona(persona_id, cwd=self._cwd)
        effective_agent_id = agent_id or (persona_id if agent is not None else None)
        effective_persona_id = persona_id if agent is None else None

        if session_id:
            _validate_session_id(session_id)
            await self._assert_owner(session_id, owner, agent_id=effective_agent_id)
            existing = self._sessions.get(session_id)
            if existing is not None:
                if not self._should_rebuild(existing, effective_persona_id, effective_agent_id, provider_name, model_id):
                    return session_id, existing
                self._assert_rebind_allowed(existing, session_id, effective_agent_id)
                await self.dispose(session_id)

        sid = session_id or _generate_session_id()
        _validate_session_id(sid)
        await self._assert_owner(sid, owner, agent_id=effective_agent_id)
        lock = self._create_locks.setdefault(sid, asyncio.Lock())
        async with lock:
            # Re-check inside lock
            existing = self._sessions.get(sid)
            if existing is not None:
                if not self._should_rebuild(existing, effective_persona_id, effective_agent_id, provider_name, model_id):
                    return sid, existing
                self._assert_rebind_allowed(existing, sid, effective_agent_id)
                await self.dispose(sid)

            # Building (or rebuilding) a new assistant is the only place an
            # unknown agent_id is an error.
            if agent_id and agent is None:
                raise ValueError(f"Agent {agent_id} not found")

            store = self._store

            provider_name = provider_name or os.environ.get("AGENT_PROVIDER", "openai")
            model_id = model_id or os.environ.get("AGENT_MODEL", "gpt-4o")
            api_key_env = os.environ.get("AGENT_API_KEY_ENV")

            assistant = await ChatAssistant.create(
                session_store=store,
                session_id=sid,
                cwd=self._cwd,
                provider_name=provider_name,
                model_id=model_id,
                api_key_env=api_key_env,
                persona=persona,
                agent=agent,
                mcp_pool=self._mcp_pool,
                companion_queue=companion_queue,
                companion_uid=companion_uid,
                owner=owner,
            )
            # Remember agent (effective — persona_id when it aliases an agent) +
            # persona + model used to create this assistant, so _should_rebuild
            # stays stable across identical requests.
            assistant._agent_id = effective_agent_id
            assistant._persona_id = effective_persona_id
            assistant._provider_name = provider_name
            assistant._model_id = model_id
            async with self._lock:
                self._sessions[sid] = assistant
                self._session_owners[sid] = owner
        self._create_locks.pop(sid, None)
        return sid, assistant

    async def dispose(self, session_id: str) -> None:
        """Dispose a session and remove it from memory."""
        _validate_session_id(session_id)
        lock = self._create_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            assistant = self._sessions.pop(session_id, None)
            self._create_locks.pop(session_id, None)
        if assistant:
            await assistant.dispose()

    async def list_sessions(
        self, limit: int = 50, *, owner: str | None = None, agent_id: str | None = None
    ) -> list[SessionMeta]:
        """List persisted sessions, optionally filtered by owner/agent."""
        return await self._store.list_sessions(owner=owner, agent_id=agent_id, limit=limit)

    async def reload_mcp(self) -> None:
        """Reload MCP configs from .mcp.json and reconnect."""
        if self._mcp_manager is not None:
            await self._mcp_manager.reload(cwd=self._cwd)

    async def reload_private(self, agent_id: str) -> None:
        """Reload an agent's private MCP manager after its config file changed."""
        if self._mcp_pool is not None:
            await self._mcp_pool.reload_private(agent_id)

    async def delete_session(
        self, session_id: str, *, owner: str | None = None, agent_id: str | None = None
    ) -> bool:
        """Delete a persisted session and dispose from memory if active."""
        _validate_session_id(session_id)
        if owner is not None:
            await self._assert_owner(session_id, owner, agent_id=agent_id)
        # Remove from in-memory active sessions
        assistant = self._sessions.pop(session_id, None)
        self._session_owners.pop(session_id, None)
        if assistant:
            await assistant.dispose()
        deleted = await self._store.delete_session(session_id)
        # Cascade-delete sub-agent audit sessions.
        prefix = f"{session_id}__sub__"
        for meta in await self._store.list_sessions(owner=owner, limit=500):
            if meta.session_id.startswith(prefix):
                await self._store.delete_session(meta.session_id)
                self._session_owners.pop(meta.session_id, None)
        return deleted

    async def dispose_all(self) -> None:
        """Dispose all active sessions."""
        async with self._lock:
            items = list(self._sessions.items())
            self._sessions.clear()
            self._create_locks.clear()
        for _, assistant in items:
            await assistant.dispose()
        if self._mcp_pool is not None:
            await self._mcp_pool.stop()
        elif self._mcp_manager is not None:
            await self._mcp_manager.stop()
