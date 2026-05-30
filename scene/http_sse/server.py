"""HTTP SSE chat assistant scene — FastAPI server."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent_core.core.events import AgentEnd, AgentEvent, MessageEnd
from agent_core.resources.personas import load_personas

from scene.http_sse.events import agent_event_to_sse_json
from agent_core.tools.mcp_tool import add_mcp_server_to_json, remove_mcp_server_from_json
from scene.http_sse.manager import SessionManager
from scene.http_sse.request_context import current_request_headers


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=100_000)


class KnowledgeDocRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=500_000)


class SkillImportRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=100_000)


class HumanInputRequest(BaseModel):
    tool_call_id: str = Field(..., min_length=1)
    values: dict[str, Any] = Field(default_factory=dict)


manager = SessionManager(cwd=os.getcwd())


@asynccontextmanager
async def lifespan(app: FastAPI):
    await manager.start()
    yield
    await manager.dispose_all()


app = FastAPI(title="Agent Core HTTP SSE Chat", lifespan=lifespan)


def _format_sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def _event_stream(
    session_id: str | None,
    message: str,
    persona_id: str | None = None,
) -> AsyncIterator[str]:
    """Yield SSE-formatted events for a chat turn."""
    sid, assistant = await manager.get_or_create(session_id, persona_id=persona_id)

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
        agent_error = getattr(assistant._agent.state, "error_message", None)
        if agent_error:
            yield _format_sse({"event": "error", "message": agent_error})
            return

        # Wait until message_end arrives, then send done
        while True:
            evt = await asyncio.wait_for(queue.get(), timeout=60.0)
            if evt is None:
                break
            data = agent_event_to_sse_json(evt)
            if data is not None:
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
    current_request_headers.set(dict(request.headers))
    return StreamingResponse(
        _event_stream(session_id, chat_request.message, persona_id=persona_id),
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
    all_sessions = await manager.list_sessions(limit=200)
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
    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "created_at": s.created_at,
                "entry_count": s.entry_count,
                "title": s.title,
            }
            for s in sessions
        ]
    }


@app.get("/session")
async def get_session(request: Request) -> dict[str, Any]:
    """Get session history messages."""
    session_id = request.query_params.get("session_id")
    if not session_id:
        return {"success": False, "error": "Missing session_id"}

    _, assistant = await manager.get_or_create(session_id)
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

    _, assistant = await manager.get_or_create(session_id)
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
    deleted = await manager.delete_session(session_id)
    return {"success": deleted}


@app.post("/abort")
async def abort_session(request: Request) -> dict[str, Any]:
    """Abort the current operation for a session."""
    session_id = request.query_params.get("session_id")
    if not session_id:
        return {"success": False, "error": "Missing session_id"}

    _, assistant = await manager.get_or_create(session_id)
    assistant.abort()
    return {"success": True}


class PersonaRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    system_prompt: str = Field(default="", max_length=5000)
    enabled_tools: list[str] | None = None
    knowledge_bases: list[str] | None = None


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
    """Upload a file to .pi/uploads/, return the saved path."""
    import os as _os
    import uuid as _uuid

    form = await request.form()
    file = form.get("file")
    if file is None:
        return {"success": False, "error": "Missing file"}

    uploads_dir = _os.path.join(manager._cwd, ".pi", "uploads")
    _os.makedirs(uploads_dir, exist_ok=True)

    ext = ""
    if file.filename and "." in file.filename:
        ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    saved_name = f"{_uuid.uuid4().hex[:12]}{ext}"
    saved_path = _os.path.join(uploads_dir, saved_name)

    raw = await file.read()
    with open(saved_path, "wb") as f:
        f.write(raw)

    return {
        "success": True,
        "filename": file.filename or saved_name,
        "path": f".pi/uploads/{saved_name}",
        "size": len(raw),
    }


# ---- Knowledge base endpoints ----

@app.get("/knowledge")
async def list_knowledge_docs() -> dict[str, Any]:
    """List all documents in the local knowledge base."""
    from agent_core.knowledge.local_kb import LocalKnowledgeBase
    import os as _os
    kb_dir = _os.path.join(manager._cwd, ".pi", "knowledge")
    kb = LocalKnowledgeBase(kb_dir)
    return {"docs": kb.list_docs()}


@app.post("/knowledge")
async def add_knowledge_doc(body: KnowledgeDocRequest) -> dict[str, Any]:
    """Add or update a document in the local knowledge base."""
    from agent_core.knowledge.local_kb import LocalKnowledgeBase
    import os as _os
    kb_dir = _os.path.join(manager._cwd, ".pi", "knowledge")
    kb = LocalKnowledgeBase(kb_dir)
    _, chunk_count = await kb.add_async(body.name, body.content)
    return {"success": True, "chunks": chunk_count}


@app.post("/knowledge/upload")
async def upload_knowledge_file(request: Request) -> dict[str, Any]:
    """Upload a file (txt, md, pdf) to the knowledge base."""
    from agent_core.knowledge.local_kb import LocalKnowledgeBase
    import os as _os

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

    kb_dir = _os.path.join(manager._cwd, ".pi", "knowledge")
    kb = LocalKnowledgeBase(kb_dir)
    name = filename.rsplit(".", 1)[0] if "." in filename else filename
    _, chunk_count = await kb.add_async(name, content)
    return {"success": True, "chunks": chunk_count}


@app.put("/knowledge/{name}/tags")
async def set_knowledge_tags(name: str, request: Request) -> dict[str, Any]:
    """Set tags for a knowledge document."""
    from agent_core.knowledge.local_kb import LocalKnowledgeBase
    import os as _os
    body = await request.json()
    tags = body.get("tags", [])
    kb_dir = _os.path.join(manager._cwd, ".pi", "knowledge")
    kb = LocalKnowledgeBase(kb_dir)
    ok = kb.set_tags(name, tags)
    return {"success": ok}


@app.get("/knowledge/{name}")
async def get_knowledge_doc(name: str) -> dict[str, Any]:
    """Get a single knowledge document with chunk previews."""
    from agent_core.knowledge.local_kb import LocalKnowledgeBase
    import os as _os
    kb_dir = _os.path.join(manager._cwd, ".pi", "knowledge")
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
    from agent_core.knowledge.local_kb import LocalKnowledgeBase
    import os as _os
    kb_dir = _os.path.join(manager._cwd, ".pi", "knowledge")
    kb = LocalKnowledgeBase(kb_dir)
    found = kb.delete(name)
    return {"success": found}


_capabilities_cache: dict[str, Any] | None = None


@app.post("/connectors")
async def add_connector(body: ConnectorRequest) -> dict[str, Any]:
    """Add or update an MCP server in .mcp.json and reload."""
    add_mcp_server_to_json(
        name=body.name,
        transport=body.transport,
        command=body.command,
        args=body.args,
        url=body.url,
        env=body.env,
        cwd=manager._cwd,
    )
    await manager.reload_mcp()
    return {"success": True}


@app.post("/connectors/health")
async def check_connectors_health() -> dict[str, Any]:
    """Check health of all MCP connections."""
    if manager._mcp_manager is None:
        return {"results": []}
    results = await manager._mcp_manager.check_health()
    return {"results": results}


@app.delete("/connectors")
async def remove_connector(request: Request) -> dict[str, Any]:
    """Remove an MCP server from .mcp.json and reload."""
    name = request.query_params.get("name")
    if not name:
        return {"success": False, "error": "Missing name"}
    found = remove_mcp_server_from_json(name, cwd=manager._cwd)
    if not found:
        return {"success": False, "error": "Connector not found"}
    await manager.reload_mcp()
    return {"success": True}


@app.get("/connectors")
async def list_connectors() -> dict[str, Any]:
    """List all connected MCP servers and their tools."""
    connectors = []
    if manager._mcp_manager is not None:
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


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
DIST_DIR = os.path.join(STATIC_DIR, "dist")
DIST_ASSETS = os.path.join(DIST_DIR, "assets")

# Serve built Vite assets if dist exists
if os.path.isdir(DIST_ASSETS):
    app.mount("/assets", StaticFiles(directory=DIST_ASSETS), name="assets")


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


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("scene.http_sse.server:app", host="0.0.0.0", port=port, reload=False)
