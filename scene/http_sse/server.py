"""HTTP SSE chat assistant scene — FastAPI server."""

from __future__ import annotations

import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent_core.core.events import AgentEnd, AgentEvent, MessageEnd
from agent_core.resources.agents import (
    AgentDefinition,
    AgentKnowledge,
    AgentTools,
    delete_agent,
    get_agent,
    load_agents,
    save_agent,
)
from agent_core.resources.personas import load_personas

from agent_core.extensions.companion import companion_event_to_sse
from agent_core.knowledge.local_kb import knowledge_agent_dir, knowledge_shared_dir
from scene.http_sse.events import agent_event_to_sse_frames
from agent_core.tools.mcp_tool import add_mcp_server_to_json, remove_mcp_server_from_json
from scene.http_sse.manager import SessionManager
from scene.http_sse.request_context import current_request_headers


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=100_000)
    provider: str | None = Field(default=None, max_length=50)
    model: str | None = Field(default=None, max_length=50)


class KnowledgeDocRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=500_000)


class SkillImportRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=100_000)


class HumanInputRequest(BaseModel):
    tool_call_id: str = Field(..., min_length=1)
    values: dict[str, Any] = Field(default_factory=dict)


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
manager = SessionManager(cwd=_PROJECT_ROOT, session_store_dir=os.path.join(_PROJECT_ROOT, "sessions"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Enable structured logging with context vars (session_id/run_id/turn)
    from agent_core.logging_config import configure_logging
    configure_logging(level=os.environ.get("AGENT_CORE_LOG_LEVEL", "INFO"))

    # Optional OTEL exporter (console or otlp/Jaeger) — no-op if not configured
    from agent_core.observability import configure_otel_exporter
    configure_otel_exporter()

    await manager.start()

    evolution_scheduler = None
    if os.environ.get("ENABLE_SKILL_EVOLUTION", "1").strip().lower() not in ("0", "false", "no", "off"):
        from scene.http_sse.evolution_scheduler import create_evolution_scheduler
        evolution_scheduler = create_evolution_scheduler(
            os.path.join(manager._cwd, ".pi", "skills"),
        )
        if evolution_scheduler is not None:
            evolution_scheduler.start()
            app.state.evolution_scheduler = evolution_scheduler

    # Configure companion naming provider (reuses same auth as chat)
    try:
        from agent_core.companion.naming import configure_naming
        from agent_core.providers.auth import AuthSource
        from agent_core.providers.openai_provider import OpenAIProvider
        from agent_core.providers.types import Model

        auth = await AuthSource.env("MINIMAX_API_KEY").resolve("minimax")
        provider = OpenAIProvider(
            base_url=os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.chat/v1"),
            provider_name="minimax",
            models=[
                Model(provider="minimax", id="minimax-m2.7",
                      context_window=128_000, max_output_tokens=4096),
            ],
        )
        configure_naming(provider, auth, model_id="minimax-m2.7")
    except Exception:
        pass  # naming falls back to name pool

    # Auto-start Feishu bots when channels are configured (default on)
    if os.environ.get("FEISHU_BOT_ENABLED", "true").lower() != "false":
        try:
            from scene.feishu.server import start_channels
            start_channels(manager)
        except Exception:
            pass
    yield
    sched = getattr(app.state, "evolution_scheduler", None)
    if sched is not None:
        await sched.stop()
    await manager.dispose_all()


app = FastAPI(title="Agent Core HTTP SSE Chat", lifespan=lifespan)


def _format_sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _resolve_owner(request: Request) -> str:
    uid = request.headers.get("uid") or request.query_params.get("user_id") or ""
    uid = uid.strip()
    if uid:
        return uid
    import os

    if os.environ.get("REQUIRE_SESSION_OWNER", "").strip() in ("1", "true", "yes"):
        return ""
    return "anonymous"


def resolve_agent_request(
    agent_id: str | None, persona_id: str | None, cwd: str
) -> tuple[AgentDefinition | None, str | None]:
    """Resolve a chat request's agent binding.

    Returns ``(agent, effective_agent_id)``. ``effective_agent_id`` is the id
    to record when an AgentDefinition is in effect — including when a
    ``persona_id`` aliases an existing agent (agent preference). When no agent
    is resolved it is ``None`` and ``persona_id`` is left to the manager's
    legacy persona path.

    Deliberately does NOT synthesize an AgentDefinition from a Persona:
    Persona.enabled_tools is a flat whitelist of tool NAMES (incl. MCP tool
    names) while AgentDefinition.tools selects MCP SERVERs, so a synthesis
    would silently drop MCP tools. The persona fallback keeps V6 persona-only
    clients working. When ``agent_id`` names an unknown agent, ``agent`` is
    ``None`` but ``effective_agent_id`` is still the requested id so callers
    can surface a not-found error.
    """
    if agent_id:
        return get_agent(agent_id, cwd=cwd), agent_id
    if persona_id:
        agent = get_agent(persona_id, cwd=cwd)
        if agent is not None:
            return agent, persona_id
        return None, None
    return None, None


async def _event_stream(
    session_id: str | None,
    message: str,
    persona_id: str | None = None,
    agent_id: str | None = None,
    provider_name: str | None = None,
    model_id: str | None = None,
    companion_uid: str = "",
    owner: str = "anonymous",
) -> AsyncIterator[str]:
    """Yield SSE-formatted events for a chat turn."""
    if not owner:
        yield _format_sse({"event": "error", "message": "Missing owner (uid or user_id)"})
        return
    agent, effective_agent_id = resolve_agent_request(agent_id, persona_id, manager._cwd)
    if agent_id and agent is None:
        yield _format_sse({"event": "error", "message": f"Agent {agent_id} not found"})
        return
    # An explicit agent takes priority over a persona; the persona is only used
    # as a fallback when no AgentDefinition was resolved (V6 compat).
    effective_persona_id = persona_id if agent is None else None
    companion_queue: asyncio.Queue[Any] = asyncio.Queue() if companion_uid else None  # type: ignore[assignment]
    try:
        sid, assistant = await manager.get_or_create(
            session_id, persona_id=effective_persona_id,
            agent_id=effective_agent_id,
            provider_name=provider_name, model_id=model_id,
            companion_queue=companion_queue,
            companion_uid=companion_uid,
            owner=owner,
        )
    except PermissionError as exc:
        yield _format_sse({"event": "error", "message": str(exc)})
        return

    # Send session_id first
    yield _format_sse({"event": "session_id", "session_id": sid})

    queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()

    def _handler(evt: AgentEvent) -> None:
        queue.put_nowait(evt)

    unsub = assistant.on_event(_handler)

    try:
        # Run prompt in background to allow streaming
        run_task = asyncio.create_task(assistant.send_message(message))

        # Check for immediate synchronous errors before starting
        agent_error = getattr(assistant.harness.state, "error_message", None)
        if agent_error:
            yield _format_sse({"event": "error", "message": agent_error})
            return

        # Wait until message_end arrives, then send done
        while True:
            # Poll both agent events and companion events
            if companion_queue is not None and not companion_queue.empty():
                cevt = companion_queue.get_nowait()
                yield _format_sse(companion_event_to_sse(cevt))
                continue

            evt = await asyncio.wait_for(queue.get(), timeout=600.0)
            if evt is None:
                break
            for data in agent_event_to_sse_frames(evt):
                yield _format_sse(data)
            if isinstance(evt, AgentEnd):
                break

        # Ensure the task is completed
        await run_task
    except asyncio.TimeoutError:
        yield _format_sse({"event": "error", "message": "Request timed out"})
    except Exception as exc:
        yield _format_sse({"event": "error", "message": f"{type(exc).__name__}: {exc}"})
    finally:
        unsub()
        yield _format_sse({"event": "done"})


@app.post("/chat/stream")
async def chat_stream(request: Request, chat_request: ChatRequest) -> StreamingResponse:
    session_id = request.query_params.get("session_id")
    persona_id = request.query_params.get("persona_id")
    agent_id = request.query_params.get("agent_id")
    current_request_headers.set(dict(request.headers))
    headers: dict[str, str] = dict(request.headers)
    companion_uid = headers.get("uid", "")
    owner = _resolve_owner(request)
    return StreamingResponse(
        _event_stream(session_id, chat_request.message, persona_id=persona_id,
                      agent_id=agent_id,
                      provider_name=chat_request.provider, model_id=chat_request.model,
                      companion_uid=companion_uid, owner=owner),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.post("/human-input")
async def human_input(request: Request, human_request: HumanInputRequest) -> dict[str, Any]:
    """Provide human input to resume a paused tool execution."""
    session_id = request.query_params.get("session_id")
    if not session_id:
        return {"success": False, "error": "Missing session_id"}

    _, assistant = await manager.get_or_create(session_id)
    accepted = assistant.provide_human_input(human_request.tool_call_id, human_request.values)
    return {"success": accepted}


@app.get("/sessions")
async def list_sessions(request: Request) -> dict[str, Any]:
    """List persisted sessions with metadata. Supports pagination."""
    limit = min(int(request.query_params.get("limit", "50")), 100)
    offset = int(request.query_params.get("offset", "0"))
    owner = _resolve_owner(request) or "anonymous"
    agent_id = request.query_params.get("agent_id")
    all_sessions = await manager.list_sessions(limit=200, owner=owner, agent_id=agent_id)
    # Hide sub-agent audit sessions from the main list.
    all_sessions = [s for s in all_sessions if "__sub__" not in s.session_id]
    sessions = all_sessions[offset:offset + limit]
    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "created_at": s.created_at,
                "entry_count": s.entry_count,
                "title": s.title,
            }
            for s in sessions
        ],
        "total": len(all_sessions),
        "offset": offset,
        "limit": limit,
    }


def _resolve_access_agent(request: Request) -> str | None:
    """Return the raw agent_id query param for session access routes.

    The manager applies the binding check against this raw id (fails closed: a
    session bound to an agent may only be read/deleted with that same
    ``agent_id``, even when the named agent no longer exists). With no
    ``agent_id`` there is no agent binding check, so legacy/persona sessions
    stay readable.
    """
    return request.query_params.get("agent_id") or None


@app.get("/session")
async def get_session(request: Request) -> dict[str, Any]:
    """Get session history messages."""
    session_id = request.query_params.get("session_id")
    if not session_id:
        return {"success": False, "error": "Missing session_id"}

    try:
        _, assistant = await manager.get_or_create(
            session_id,
            owner=_resolve_owner(request) or "anonymous",
            agent_id=_resolve_access_agent(request),
        )
    except (PermissionError, ValueError) as exc:
        return {"success": False, "error": str(exc)}
    messages = []
    for msg in assistant.messages:
        try:
            messages.append(msg.model_dump(mode="json"))
        except Exception:
            pass
    return {"success": True, "session_id": session_id, "messages": messages}


@app.get("/session/export")
async def export_session(request: Request):
    """Export session messages as readable text file."""
    session_id = request.query_params.get("session_id")
    if not session_id:
        return {"success": False, "error": "Missing session_id"}

    try:
        _, assistant = await manager.get_or_create(
            session_id,
            owner=_resolve_owner(request) or "anonymous",
            agent_id=_resolve_access_agent(request),
        )
    except (PermissionError, ValueError) as exc:
        return {"success": False, "error": str(exc)}
    lines = []
    for msg in assistant.messages:
        role = getattr(msg, 'role', 'unknown')
        content = getattr(msg, 'content', '')
        if isinstance(content, list):
            content = ' '.join(p.get('text', '') for p in content if isinstance(p, dict) and p.get('type') == 'text')
        lines.append(f"## {role}\n\n{content}\n")

    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        "\n".join(lines),
        headers={"Content-Disposition": f"attachment; filename=session-{session_id}.txt"},
    )


@app.delete("/session")
async def delete_session(request: Request) -> dict[str, Any]:
    """Delete a persisted session."""
    session_id = request.query_params.get("session_id")
    if not session_id:
        return {"success": False, "error": "Missing session_id"}
    try:
        deleted = await manager.delete_session(
            session_id,
            owner=_resolve_owner(request) or "anonymous",
            agent_id=_resolve_access_agent(request),
        )
    except (PermissionError, ValueError) as exc:
        return {"success": False, "error": str(exc)}
    return {"success": deleted}


@app.post("/abort")
async def abort_session(request: Request) -> dict[str, Any]:
    """Abort the current operation for a session."""
    session_id = request.query_params.get("session_id")
    if not session_id:
        return {"success": False, "error": "Missing session_id"}

    try:
        _, assistant = await manager.get_or_create(
            session_id,
            owner=_resolve_owner(request) or "anonymous",
            agent_id=_resolve_access_agent(request),
        )
    except (PermissionError, ValueError) as exc:
        return {"success": False, "error": str(exc)}
    assistant.abort()
    return {"success": True}


class PersonaRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    system_prompt: str = Field(default="", max_length=5000)
    enabled_tools: list[str] | None = None
    knowledge_bases: list[str] | None = None


class AgentRequest(BaseModel):
    """Agent definition payload mirroring the .pi/agents/*.json schema.

    ``tools`` / ``knowledge`` are kept loose dicts so they round-trip through
    ``save_agent`` / ``load_agents`` untouched (same shape as the loader).
    """
    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    system_prompt: str = Field(default="", max_length=100_000)
    tools: dict[str, Any] | None = None
    knowledge: dict[str, Any] | None = None


class ConnectorRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    transport: str = Field(..., pattern=r"^(stdio|sse|streamable_http)$")
    command: str | None = None
    args: list[str] | None = None
    url: str | None = None
    env: dict[str, str] | None = None


@app.post("/skills/import")
async def import_skill(body: SkillImportRequest) -> dict[str, Any]:
    """Import a skill file into .pi/skills/ directory and reload capabilities."""
    import os as _os

    skills_dir = _os.path.join(manager._cwd, ".pi", "skills")
    _os.makedirs(skills_dir, exist_ok=True)
    file_path = _os.path.join(skills_dir, f"{body.name}.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(body.content)

    # Invalidate capability cache so next fetch reloads
    global _capabilities_cache
    _capabilities_cache = None
    return {"success": True}


# ---- File upload ----

@app.post("/upload")
async def upload_file(request: Request) -> dict[str, Any]:
    """Upload a file: save locally and push to remote Migu storage.

    Returns ``url`` (public remote URL) for use as image input by agents/tools.
    """
    from scene.common.upload_handler import save_and_remote_upload

    form = await request.form()
    file = form.get("file")
    if file is None:
        return {"success": False, "error": "Missing file"}

    raw = await file.read()
    content_type = getattr(file, "content_type", None)
    try:
        return await save_and_remote_upload(
            raw=raw,
            filename=file.filename,
            cwd=manager._cwd,
            content_type=content_type,
        )
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ---- Knowledge base endpoints ----

_SAFE_AGENT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _knowledge_dir(scope: str, agent_id: str) -> str:
    """Resolve a KB root for a scope (shared | agent)."""
    if scope not in ("shared", "agent"):
        raise ValueError(f"Invalid scope: {scope!r}")
    if scope == "agent":
        if not agent_id or not _SAFE_AGENT_ID_RE.match(agent_id):
            raise ValueError("agent scope requires a valid agent_id")
        return knowledge_agent_dir(agent_id, manager._cwd)
    return knowledge_shared_dir(manager._cwd)


@app.get("/knowledge")
async def list_knowledge_docs(request: Request) -> dict[str, Any]:
    """List all documents in the local knowledge base."""
    scope = request.query_params.get("scope", "shared")
    agent_id = request.query_params.get("agent_id", "")
    try:
        kb_dir = _knowledge_dir(scope, agent_id)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    from agent_core.knowledge.local_kb import LocalKnowledgeBase
    kb = LocalKnowledgeBase(kb_dir)
    return {"docs": kb.list_docs()}


@app.post("/knowledge")
async def add_knowledge_doc(body: KnowledgeDocRequest, request: Request) -> dict[str, Any]:
    """Add or update a document in the local knowledge base."""
    scope = request.query_params.get("scope", "shared")
    agent_id = request.query_params.get("agent_id", "")
    try:
        kb_dir = _knowledge_dir(scope, agent_id)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    from agent_core.knowledge.local_kb import LocalKnowledgeBase
    kb = LocalKnowledgeBase(kb_dir)
    _, chunk_count = await kb.add_async(body.name, body.content)
    return {"success": True, "chunks": chunk_count}


@app.post("/knowledge/upload")
async def upload_knowledge_file(request: Request) -> dict[str, Any]:
    """Upload a file (txt, md, pdf) to the knowledge base."""
    from agent_core.knowledge.local_kb import LocalKnowledgeBase

    scope = request.query_params.get("scope", "shared")
    agent_id = request.query_params.get("agent_id", "")
    try:
        kb_dir = _knowledge_dir(scope, agent_id)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    form = await request.form()
    file = form.get("file")
    if file is None:
        return {"success": False, "error": "Missing file"}

    filename = file.filename or "doc"
    content = ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        try:
            from io import BytesIO
            from pypdf import PdfReader
        except ImportError:
            return {"success": False, "error": "pypdf not installed. Run: pip install pypdf"}
        raw = await file.read()
        reader = PdfReader(BytesIO(raw))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        content = "\n".join(pages)
    else:
        raw = await file.read()
        content = raw.decode("utf-8", errors="replace")

    if not content.strip():
        return {"success": False, "error": "Empty file or could not extract text"}

    kb = LocalKnowledgeBase(kb_dir)
    name = filename.rsplit(".", 1)[0] if "." in filename else filename
    _, chunk_count = await kb.add_async(name, content)
    return {"success": True, "chunks": chunk_count}


@app.put("/knowledge/{name}/tags")
async def set_knowledge_tags(name: str, request: Request) -> dict[str, Any]:
    """Set tags for a knowledge document."""
    from agent_core.knowledge.local_kb import LocalKnowledgeBase

    scope = request.query_params.get("scope", "shared")
    agent_id = request.query_params.get("agent_id", "")
    try:
        kb_dir = _knowledge_dir(scope, agent_id)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    body = await request.json()
    tags = body.get("tags", [])
    kb = LocalKnowledgeBase(kb_dir)
    ok = kb.set_tags(name, tags)
    return {"success": ok}


@app.get("/knowledge/{name}")
async def get_knowledge_doc(name: str, request: Request) -> dict[str, Any]:
    """Get a single knowledge document with chunk previews."""
    from agent_core.knowledge.local_kb import LocalKnowledgeBase

    scope = request.query_params.get("scope", "shared")
    agent_id = request.query_params.get("agent_id", "")
    try:
        kb_dir = _knowledge_dir(scope, agent_id)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    kb = LocalKnowledgeBase(kb_dir)
    doc = kb.get_doc(name)
    if doc is None:
        return {"success": False, "error": "Not found"}
    return {"success": True, "doc": doc}


@app.delete("/knowledge")
async def delete_knowledge_doc(request: Request) -> dict[str, Any]:
    """Delete a document from the local knowledge base."""
    name = request.query_params.get("name")
    if not name:
        return {"success": False, "error": "Missing name"}
    scope = request.query_params.get("scope", "shared")
    agent_id = request.query_params.get("agent_id", "")
    try:
        kb_dir = _knowledge_dir(scope, agent_id)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    from agent_core.knowledge.local_kb import LocalKnowledgeBase
    kb = LocalKnowledgeBase(kb_dir)
    found = kb.delete(name)
    return {"success": found}


_capabilities_cache: dict[str, Any] | None = None


def _agent_mcp_path(agent_id: str) -> str:
    """Agent-scoped connector file: .pi/mcp/agents/<agent_id>.mcp.json."""
    return os.path.join(manager._cwd, ".pi", "mcp", "agents", f"{agent_id}.mcp.json")


def _connector_scope_error(scope: str, agent_id: str) -> str | None:
    """Validate connector scope/agent_id; return an error message or None."""
    if scope not in ("shared", "agent"):
        return f"Invalid scope: {scope!r}"
    if scope == "agent" and (not agent_id or not _SAFE_AGENT_ID_RE.match(agent_id)):
        return "agent scope requires a valid agent_id"
    return None


@app.post("/connectors")
async def add_connector(request: Request, body: ConnectorRequest) -> dict[str, Any]:
    """Add or update an MCP server (shared or per-agent) and reload."""
    scope = request.query_params.get("scope", "shared")
    agent_id = request.query_params.get("agent_id", "")
    err = _connector_scope_error(scope, agent_id)
    if err:
        return {"success": False, "error": err}
    if scope == "agent":
        add_mcp_server_to_json(
            name=body.name, transport=body.transport,
            command=body.command, args=body.args,
            url=body.url, env=body.env,
            path=_agent_mcp_path(agent_id),
        )
        await manager.reload_private(agent_id)
    else:
        add_mcp_server_to_json(
            name=body.name, transport=body.transport,
            command=body.command, args=body.args,
            url=body.url, env=body.env,
            cwd=manager._cwd,
        )
        await manager.reload_mcp()
    global _capabilities_cache
    _capabilities_cache = None
    return {"success": True}


@app.post("/connectors/health")
async def check_connectors_health(request: Request) -> dict[str, Any]:
    """Check health of MCP connections (shared or per-agent)."""
    scope = request.query_params.get("scope", "shared")
    agent_id = request.query_params.get("agent_id", "")
    err = _connector_scope_error(scope, agent_id)
    if err:
        return {"success": False, "error": err}
    results = []
    if scope == "agent":
        if manager._mcp_pool is not None:
            private = await manager._mcp_pool.ensure_private(agent_id)
            results = await private.check_health()
    elif manager._mcp_manager is not None:
        results = await manager._mcp_manager.check_health()
    return {"results": results}


@app.delete("/connectors")
async def remove_connector(request: Request) -> dict[str, Any]:
    """Remove an MCP server (shared or per-agent) and reload."""
    name = request.query_params.get("name")
    if not name:
        return {"success": False, "error": "Missing name"}
    scope = request.query_params.get("scope", "shared")
    agent_id = request.query_params.get("agent_id", "")
    err = _connector_scope_error(scope, agent_id)
    if err:
        return {"success": False, "error": err}
    if scope == "agent":
        found = remove_mcp_server_from_json(name, path=_agent_mcp_path(agent_id))
    else:
        found = remove_mcp_server_from_json(name, cwd=manager._cwd)
    if not found:
        return {"success": False, "error": "Connector not found"}
    if scope == "agent":
        await manager.reload_private(agent_id)
    else:
        await manager.reload_mcp()
    global _capabilities_cache
    _capabilities_cache = None
    return {"success": True}


@app.get("/connectors")
async def list_connectors(request: Request) -> dict[str, Any]:
    """List connected MCP servers and their tools (shared or per-agent)."""
    scope = request.query_params.get("scope", "shared")
    agent_id = request.query_params.get("agent_id", "")
    err = _connector_scope_error(scope, agent_id)
    if err:
        return {"success": False, "error": err}
    connectors = []
    if scope == "agent":
        if manager._mcp_pool is not None:
            private = await manager._mcp_pool.ensure_private(agent_id)
            connectors = private.get_connector_info()
    elif manager._mcp_manager is not None:
        connectors = manager._mcp_manager.get_connector_info()
    return {"connectors": connectors}


@app.get("/personas")
async def list_personas() -> dict[str, Any]:
    """List available agent personas / experts."""
    personas = load_personas(cwd=manager._cwd)
    return {
        "personas": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "system_prompt": p.system_prompt,
                "enabled_tools": p.enabled_tools,
                "knowledge_bases": p.knowledge_bases,
            }
            for p in personas
        ]
    }


@app.post("/personas")
async def save_persona(body: PersonaRequest) -> dict[str, Any]:
    """Create or update a persona."""
    from agent_core.resources.personas import Persona, save_persona as save_p
    p = Persona(
        id=body.id,
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        enabled_tools=body.enabled_tools,
        knowledge_bases=body.knowledge_bases,
    )
    save_p(p, cwd=manager._cwd)
    return {"success": True}


@app.delete("/personas")
async def remove_persona(request: Request) -> dict[str, Any]:
    """Delete a persona by id."""
    pid = request.query_params.get("id")
    if not pid:
        return {"success": False, "error": "Missing id"}
    from agent_core.resources.personas import delete_persona
    found = delete_persona(pid, cwd=manager._cwd)
    return {"success": found}


# ---- Agent definitions ----

def _agent_to_dict(a: AgentDefinition) -> dict[str, Any]:
    """Serialize an AgentDefinition for the API (tools/knowledge round-trip)."""
    from dataclasses import asdict
    return {
        "id": a.id,
        "name": a.name,
        "description": a.description,
        "system_prompt": a.system_prompt,
        "tools": asdict(a.tools) if a.tools is not None else None,
        "knowledge": asdict(a.knowledge) if a.knowledge is not None else None,
    }


def _parse_agent_request(body: AgentRequest) -> AgentDefinition:
    """Build an AgentDefinition from a request, reusing the loader's schema."""
    tools = None
    if body.tools is not None:
        tools = AgentTools(
            builtin=body.tools.get("builtin"),
            shared_mcp=body.tools.get("shared_mcp") or [],
            private_mcp=body.tools.get("private_mcp") or [],
        )
    knowledge = None
    if body.knowledge is not None:
        knowledge = AgentKnowledge(
            shared=body.knowledge.get("shared") or [],
            private=body.knowledge.get("private") or [],
            shared_mcp_knowledge=body.knowledge.get("shared_mcp_knowledge") or [],
            private_mcp_knowledge=body.knowledge.get("private_mcp_knowledge") or [],
        )
    return AgentDefinition(
        id=body.id,
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        tools=tools,
        knowledge=knowledge,
    )


@app.get("/agents")
async def list_agents() -> dict[str, Any]:
    """List available agent definitions."""
    return {"agents": [_agent_to_dict(a) for a in load_agents(cwd=manager._cwd)]}


@app.post("/agents")
async def save_agent_route(body: AgentRequest) -> dict[str, Any]:
    """Create or update an agent definition."""
    save_agent(_parse_agent_request(body), cwd=manager._cwd)
    return {"success": True}


@app.delete("/agents")
async def remove_agent(request: Request) -> dict[str, Any]:
    """Delete an agent definition by id."""
    aid = request.query_params.get("id")
    if not aid:
        return {"success": False, "error": "Missing id"}
    found = delete_agent(aid, cwd=manager._cwd)
    return {"success": found}


@app.get("/models")
async def list_models() -> dict[str, Any]:
    """List available model configurations."""
    return {
        "current": {
            "provider": os.environ.get("AGENT_PROVIDER", "openai"),
            "model": os.environ.get("AGENT_MODEL", "gpt-4o"),
        },
        "available": [
            {"provider": "agnes", "model": "agnes-2.0-flash", "label": "Agnes 2.0 Flash", "desc": "256K context, fast agentic"},
            {"provider": "minimax", "model": "minimax-m2.7", "label": "MiniMax M2.7", "desc": "256K context, 4K output"},
            {"provider": "openai", "model": "gpt-4o", "label": "GPT-4o", "desc": "OpenAI flagship"},
            {"provider": "anthropic", "model": "claude-sonnet-4-20250514", "label": "Claude Sonnet 4", "desc": "Anthropic high-perf"},
        ],
    }


@app.get("/capabilities")
async def get_capabilities() -> dict[str, Any]:
    """Get available skills and tools (cached after first call)."""
    global _capabilities_cache
    if _capabilities_cache is None:
        _, assistant = await manager.get_or_create(None)
        _capabilities_cache = {
            "skills": [
                {"name": s.name, "description": s.description}
                for s in assistant.skills
            ],
            "tools": assistant.tool_infos,
        }
    return _capabilities_cache


# ---- Channel management ----

from scene.http_sse.channel_config import load_channels, save_channels  # noqa: E402

_channel_runner: Any = None  # reference to running channel process


class ChannelRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=50)
    type: str = Field(default="feishu")
    enabled: bool = Field(default=True)
    app_id: str = Field(default="")
    app_secret: str = Field(default="")
    allowed_users: str = Field(default="")


@app.get("/channels")
async def list_channels() -> dict[str, Any]:
    """List all channel configurations (secrets masked)."""
    channels = load_channels(manager._cwd)
    # Mask secrets in response
    safe = []
    for c in channels:
        sc = dict(c)
        if sc.get("app_secret"):
            sc["app_secret"] = sc["app_secret"][:4] + "****" + sc["app_secret"][-4:] if len(sc["app_secret"]) > 8 else "****"
        safe.append(sc)
    return {"channels": safe}


@app.post("/channels")
async def save_channel(body: ChannelRequest) -> dict[str, Any]:
    """Add or update a channel configuration."""
    channels = load_channels(manager._cwd)
    existing = next((c for c in channels if c["id"] == body.id), None)
    if existing:
        existing.update({
            "name": body.name, "type": body.type,
            "enabled": body.enabled, "app_id": body.app_id,
        })
        if body.app_secret and body.app_secret != "****":
            existing["app_secret"] = body.app_secret
        if body.allowed_users:
            existing["allowed_users"] = body.allowed_users
    else:
        channels.append({
            "id": body.id, "name": body.name, "type": body.type,
            "enabled": body.enabled, "app_id": body.app_id,
            "app_secret": body.app_secret,
        })
    save_channels(manager._cwd, channels)
    # Reload channel runner
    _reload_channels(channels)
    return {"success": True}


@app.delete("/channels/{channel_id}")
async def delete_channel(channel_id: str) -> dict[str, Any]:
    """Delete a channel configuration."""
    channels = load_channels(manager._cwd)
    channels = [c for c in channels if c["id"] != channel_id]
    save_channels(manager._cwd, channels)
    _reload_channels(channels)
    return {"success": True}


def _reload_channels(channels: list[dict[str, Any]]) -> None:
    """Reload channel configurations — restart enabled channel runners."""
    global _channel_runner
    # Find feishu config
    feishu = next((c for c in channels if c["type"] == "feishu" and c.get("enabled")), None)
    if feishu:
        os.environ["FEISHU_APP_ID"] = feishu.get("app_id", "")
        os.environ["FEISHU_APP_SECRET"] = feishu.get("app_secret", "")
    else:
        os.environ.pop("FEISHU_APP_ID", None)
        os.environ.pop("FEISHU_APP_SECRET", None)


# ---- Skill Evolution ----

class EvolutionAnalyzeRequest(BaseModel):
    skill_name: str = Field(..., min_length=1, max_length=100)
    min_traces: int = Field(default=10, ge=1, le=10000)
    force: bool = Field(default=False, description="Force evolution even if pending proposals exist")


class EvolutionFeedbackRequest(BaseModel):
    trace_id: str = Field(..., min_length=1, max_length=200)
    feedback: str = Field(..., min_length=1, max_length=4000)
    was_helpful: bool | None = None


class EvolutionProposalAction(BaseModel):
    skill_name: str = Field(..., min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=500)
    force: bool = Field(default=False, description="Bypass validation gate (use with care)")


def _get_skill_dir() -> str:
    return os.path.join(manager._cwd, ".pi", "skills")


@app.get("/skills/evolution/summary")
async def get_evolution_summary() -> dict[str, Any]:
    """Get trace counts per skill and recent evolution cycles."""
    from agent_core.skill_evolution.store import JsonlSkillEvolutionStore

    trace_store = JsonlSkillEvolutionStore()
    skill_dir = _get_skill_dir()

    trace_counts: dict[str, dict[str, int]] = {}
    if os.path.isdir(skill_dir):
        for name in os.listdir(skill_dir):
            if os.path.isdir(os.path.join(skill_dir, name)):
                total = await trace_store.get_trace_count(skill_name=name)
                success = await trace_store.get_trace_count(skill_name=name, outcome="success")
                failure = await trace_store.get_trace_count(skill_name=name, outcome="failure")
                if total > 0:
                    trace_counts[name] = {"total": total, "success": success, "failure": failure}

    return {"trace_counts": trace_counts}


@app.post("/skills/evolution/feedback")
async def record_evolution_feedback(body: EvolutionFeedbackRequest) -> dict[str, Any]:
    """Attach user feedback to a skill evolution trace (append-only)."""
    from fastapi import HTTPException

    from scene.http_sse.evolution_config import build_skill_trace_collector

    collector = build_skill_trace_collector()
    if collector is None:
        raise HTTPException(status_code=404, detail="skill evolution disabled")
    await collector.record_user_feedback(
        body.trace_id,
        body.feedback,
        was_helpful=body.was_helpful,
    )
    return {"ok": True, "trace_id": body.trace_id}


@app.post("/skills/evolution/analyze")
async def analyze_skill_evolution(body: EvolutionAnalyzeRequest) -> dict[str, Any]:
    """Run an evolution cycle and return proposals with diffs.

    Blocks if there are pending proposals for this skill (unless force=True).
    """
    from scene.http_sse.evolution_service import run_skill_evolution_analyze

    return await run_skill_evolution_analyze(
        skill_dir=_get_skill_dir(),
        skill_name=body.skill_name,
        min_traces=body.min_traces,
        force=body.force,
    )


@app.get("/skills/evolution/scheduler/status")
async def get_evolution_scheduler_status() -> dict[str, Any]:
    """Return background scheduler state when ENABLE_EVOLUTION_SCHEDULER=1."""
    from scene.http_sse.evolution_scheduler import (
        evolution_scheduler_enabled,
        scheduler_interval_sec,
        scheduler_min_traces,
    )

    sched = getattr(app.state, "evolution_scheduler", None)
    return {
        "enabled": evolution_scheduler_enabled(),
        "running": sched is not None and sched.running,
        "interval_sec": scheduler_interval_sec(),
        "min_traces": scheduler_min_traces(),
        "last_run_at": getattr(sched, "last_run_at", None) if sched else None,
        "last_run_summary": getattr(sched, "last_run_summary", None) if sched else None,
    }


@app.get("/skills/evolution/proposals/{skill_name}")
async def get_evolution_proposals(skill_name: str) -> dict[str, Any]:
    """Get pending proposals for a skill awaiting review."""
    from scene.http_sse.evolution_pending import get_pending_proposals

    proposals = get_pending_proposals(skill_name)
    return {"skill_name": skill_name, "proposals": proposals}


@app.post("/skills/evolution/proposals/{proposal_id}/accept")
async def accept_evolution_proposal(
    proposal_id: str,
    body: EvolutionProposalAction,
) -> dict[str, Any]:
    """Validate and apply an accepted proposal, writing audit log."""
    from agent_core.skill_evolution import PatchProposal, write_audit_entry
    from scene.http_sse.evolution_pending import get_pending_proposals, remove_pending_proposal
    from scene.http_sse.evolution_validation import build_evolution_validation_gate

    p_dict = next(
        (p for p in get_pending_proposals(body.skill_name) if p.get("proposal_id") == proposal_id),
        None,
    )
    if p_dict is None:
        return {"success": False, "error": "Proposal not found"}

    proposal = PatchProposal(
        proposal_id=p_dict["proposal_id"],
        source_traces=p_dict.get("source_traces", []),
        skill_name=p_dict["skill_name"],
        operation=p_dict.get("operation", "add"),
        target_rule_id=p_dict.get("target_rule_id"),
        new_content=p_dict.get("new_content"),
        rationale=p_dict.get("rationale", ""),
        confidence=p_dict.get("confidence", 0.5),
    )

    gate = build_evolution_validation_gate(_get_skill_dir(), body.skill_name)
    result = await gate.validate(proposal)
    applied = False
    if result.passed or result.recommendation == "accept":
        applied = await gate.apply_proposal(proposal, backup=True, force=False)
    elif body.force:
        applied = await gate.apply_proposal(proposal, backup=True, force=True)

    audit_id = write_audit_entry(
        proposal_id=proposal_id,
        skill_name=body.skill_name,
        action="accept" if applied else "reject",
        operation=proposal.operation,
        target_rule_id=proposal.target_rule_id,
        diff_summary=(proposal.new_content or "")[:200],
        rationale=proposal.rationale,
        validation_score=result.score_delta,
    )

    # Remove from pending store on success
    if applied:
        remove_pending_proposal(proposal_id)

    return {
        "success": applied,
        "audit_id": audit_id,
        "validation_score": result.score_delta,
        "validation_passed": result.passed,
        "validation_recommendation": result.recommendation,
    }


@app.post("/skills/evolution/proposals/{proposal_id}/reject")
async def reject_evolution_proposal(
    proposal_id: str,
    body: EvolutionProposalAction,
) -> dict[str, Any]:
    """Reject a proposal and write audit log (no skill file modification)."""
    from agent_core.skill_evolution import write_audit_entry
    from scene.http_sse.evolution_pending import get_pending_proposals, remove_pending_proposal

    p_dict = next(
        (p for p in get_pending_proposals(body.skill_name) if p.get("proposal_id") == proposal_id),
        None,
    )
    if p_dict is None:
        return {"success": False, "error": "Proposal not found"}

    audit_id = write_audit_entry(
        proposal_id=proposal_id,
        skill_name=body.skill_name,
        action="reject",
        operation=p_dict.get("operation", ""),
        target_rule_id=p_dict.get("target_rule_id"),
        diff_summary=(p_dict.get("new_content") or "")[:200],
        rationale=p_dict.get("rationale", ""),
        reject_reason=body.reason,
    )

    remove_pending_proposal(proposal_id)

    return {"success": True, "audit_id": audit_id}


@app.get("/skills/evolution/pending")
async def get_evolution_pending() -> dict[str, Any]:
    """Get summary of all pending proposals awaiting review."""
    from scene.http_sse.evolution_pending import get_pending_proposals, get_pending_summary

    return {
        "summary": get_pending_summary(),
        "proposals": get_pending_proposals(),
    }


@app.delete("/skills/evolution/pending")
async def clear_evolution_pending(skill_name: str | None = None) -> dict[str, Any]:
    """Clear all pending proposals, or only for a specific skill."""
    from scene.http_sse.evolution_pending import clear_pending_proposals

    count = clear_pending_proposals(skill_name)
    return {"cleared": count, "skill_name": skill_name}


@app.get("/skills/evolution/audit")
async def get_evolution_audit(
    skill_name: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Read evolution audit log entries."""
    from agent_core.skill_evolution import read_audit_log

    entries = read_audit_log(skill_name=skill_name, limit=limit)
    return {"entries": entries, "total": len(entries)}


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
DIST_DIR = os.path.join(STATIC_DIR, "dist")
DIST_ASSETS = os.path.join(DIST_DIR, "assets")

# Serve built Vite assets if dist exists
if os.path.isdir(DIST_ASSETS):
    app.mount("/assets", StaticFiles(directory=DIST_ASSETS), name="assets")

# Serve local uploads for cached tool outputs (images, audio, etc.)
UPLOADS_DIR = os.path.join(manager._cwd, ".pi", "uploads")
if not os.path.isdir(UPLOADS_DIR):
    os.makedirs(UPLOADS_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

RENDERS_DIR = os.path.join(manager._cwd, ".pi", "renders")
if not os.path.isdir(RENDERS_DIR):
    os.makedirs(RENDERS_DIR, exist_ok=True)
app.mount("/renders", StaticFiles(directory=RENDERS_DIR), name="renders")


@app.get("/")
async def index() -> HTMLResponse:
    # Prefer built Vite output, fall back to legacy single-file HTML
    dist_html = os.path.join(DIST_DIR, "index.html")
    legacy_html = os.path.join(STATIC_DIR, "index.html")
    for path in (dist_html, legacy_html):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        except FileNotFoundError:
            continue
    return HTMLResponse(
        content="<html><body><h1>agent-core</h1><p>Frontend not found. Run `npm run build` in static/</p></body></html>"
    )


# ---- Companion API -----------------------------------------------------------


@app.get("/api/companion/{uid}")
async def get_companion(uid: str) -> dict[str, Any]:
    """Return deterministic companion bones for a uid."""
    from agent_core.companion import roll_companion
    bones = roll_companion(uid)
    return _bones_to_dict(bones)


@app.post("/api/companion/{uid}/hatch")
async def hatch_companion(uid: str) -> dict[str, Any]:
    """Hatch a companion — generate name + personality."""
    from agent_core.companion import roll_companion
    from agent_core.companion.naming import hatch_name

    bones = roll_companion(uid)
    soul = await hatch_name(bones)
    return {
        **_bones_to_dict(bones),
        "name": soul.name,
        "personality": soul.personality,
        "hatched_at": soul.hatched_at,
    }


def _bones_to_dict(bones) -> dict[str, Any]:
    return {
        "uid": bones.uid,
        "breed": bones.breed,
        "rarity": bones.rarity,
        "eye": bones.eye,
        "ear": bones.ear,
        "accent": bones.accent,
        "hat": bones.hat,
        "quirk": bones.quirk,
        "shiny": bones.shiny,
        "color": bones.color,
        "stats": bones.stats,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("scene.http_sse.server:app", host="0.0.0.0", port=port, reload=False)
