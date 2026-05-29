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
async def list_sessions() -> dict[str, Any]:
    """List all persisted sessions with metadata."""
    sessions = await manager.list_sessions()
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
            "tools": assistant.tool_names,
        }
    return _capabilities_cache


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
