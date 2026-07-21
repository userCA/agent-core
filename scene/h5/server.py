"""HTTP SSE chat assistant scene — FastAPI server."""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from agent_core.core.content import ImageContent
from agent_core.core.events import AgentEnd, AgentEvent
from agent_core.resources.personas import load_personas

from scene.h5.events import agent_event_to_sse_json, companion_event_to_v1, create_tracker
from agent_core.tools.mcp_tool import add_mcp_server_to_json, remove_mcp_server_from_json
from scene.h5.manager import SessionManager
from scene.h5.request_context import current_request_headers


class ContentBlockInput(BaseModel):
    """Multimodal content block per spec §9.1."""
    type: str = Field(..., pattern=r'^(text|image|audio|video|file)$')
    content: str = Field(..., min_length=1)
    meta: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=100_000)
    content: list[ContentBlockInput] | None = None
    provider: str | None = Field(default=None, max_length=50)
    model: str | None = Field(default=None, max_length=50)

    @field_validator("message", mode="before")
    @classmethod
    def _validate_message_or_content(cls, v: Any, info: Any) -> Any:
        return v if v is not None else ""


class KnowledgeDocRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=500_000)


class SkillImportRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=100_000)


class HumanInputRequest(BaseModel):
    tool_call_id: str = Field(..., min_length=1)
    values: dict[str, Any] = Field(default_factory=dict)


class _HumanInputSubmitted:
    """Synthetic event injected into the SSE stream when HITL input is received."""
    __slots__ = ("tool_call_id",)
    def __init__(self, tool_call_id: str) -> None:
        self.tool_call_id = tool_call_id


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
manager = SessionManager(cwd=_PROJECT_ROOT, session_store_dir=os.path.join(_PROJECT_ROOT, "sessions"))

# Active SSE stream queues per session — used to inject human_input.submitted events
_active_streams: dict[str, asyncio.Queue[AgentEvent | None]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await manager.start()

    # Configure companion naming provider (reuses same auth as chat)
    try:
        from agent_core.companion.naming import configure_naming
        from agent_core.providers.auth import AuthSource
        from agent_core.providers.openai_provider import OpenAIProvider
        from agent_core.providers.types import Model

        auth = await AuthSource.env("MINIMAX_API_KEY").resolve("minimax")
        provider = OpenAIProvider(
            base_url="https://api.minimax.chat/v1",
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
    await manager.dispose_all()


app = FastAPI(title="Agent Core HTTP SSE Chat", lifespan=lifespan)


def _content_blocks_to_images(blocks: list[ContentBlockInput] | None) -> list[ImageContent]:
    """Convert multimodal ContentBlockInput items to ImageContent for the Agent."""
    images: list[ImageContent] = []
    if not blocks:
        return images
    _mime_map = {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "gif": "image/gif", "webp": "image/webp", "svg": "image/svg+xml",
        "mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg",
        "mp4": "video/mp4", "webm": "video/webm",
    }
    for block in blocks:
        if block.type in ("image", "audio", "video"):
            fmt = (block.meta or {}).get("format", "")
            mime = _mime_map.get(fmt, f"image/{fmt}" if fmt else "image/png")
            images.append(ImageContent(data=block.content, mime_type=mime))
    return images


def _classify_error(msg: str) -> dict[str, Any]:
    """Classify an error message into spec ErrorDetail (type/code/retryable)."""
    lower = msg.lower()
    if any(k in lower for k in ("401", "unauthorized", "api key", "auth", "authentication")):
        return {"type": "authentication_error", "code": "E00002", "retryable": False}
    if any(k in lower for k in ("404", "not found", "session not")):
        return {"type": "not_found", "code": "E00003", "retryable": False}
    if any(k in lower for k in ("model", "502", "bad gateway", "model_error")):
        return {"type": "model_error", "code": "E00004", "retryable": True}
    if any(k in lower for k in ("context_length", "context overflow", "413", "too long", "max token")):
        return {"type": "context_overflow", "code": "E00005", "retryable": True}
    if any(k in lower for k in ("rate_limit", "429", "too many", "用量上限")):
        return {"type": "rate_limit", "code": "E00006", "retryable": True}
    if any(k in lower for k in ("tool", "execution", "tool_error")):
        return {"type": "tool_execution_error", "code": "E00007", "retryable": False}
    if any(k in lower for k in ("timeout", "timed out", "504")):
        return {"type": "timeout", "code": "E00008", "retryable": True}
    if any(k in lower for k in ("cancel", "abort")):
        return {"type": "cancelled", "code": "E00010", "retryable": False}
    if any(k in lower for k in ("overload", "529", "service unavailable")):
        return {"type": "overloaded", "code": "E00011", "retryable": True}
    return {"type": "internal_error", "code": "E00009", "retryable": False}


def _format_sse(data: dict[str, Any], event: str | None = None) -> str:
    """Format a dict as an SSE frame with optional ``event:`` channel."""
    lines = ""
    if event:
        lines += f"event: {event}\n"
    lines += f"data: {json.dumps(data)}\n\n"
    return lines


def _emit_v1(event_dict: dict[str, Any] | list[dict[str, Any]] | None) -> str:
    """Convert one or more v1 event dicts to SSE frames."""
    if event_dict is None:
        return ""
    if isinstance(event_dict, list):
        return "".join(_emit_v1(item) for item in event_dict)
    return _format_sse(event_dict["data"], event=event_dict.get("sse_event"))


async def _event_stream(
    session_id: str | None,
    message: str,
    content_blocks: list[ContentBlockInput] | None = None,
    persona_id: str | None = None,
    provider_name: str | None = None,
    model_id: str | None = None,
    companion_uid: str = "",
) -> AsyncIterator[str]:
    """Yield SSE-formatted events for a chat turn."""
    companion_queue: asyncio.Queue[Any] = asyncio.Queue() if companion_uid else None  # type: ignore[assignment]
    sid, assistant = await manager.get_or_create(
        session_id, persona_id=persona_id,
        provider_name=provider_name, model_id=model_id,
        companion_queue=companion_queue,
        companion_uid=companion_uid,
    )

    # Create per-stream content-block tracker (message_id must match message.start)
    _msg_id = f"msg_{sid}"
    tracker = create_tracker(message_id=_msg_id)

    # Send message.start (v1)
    yield _format_sse(
        {"type": "message.start", "messageId": _msg_id, "sessionId": sid, "runId": f"run_{int(time.time())}", "createdAt": int(time.time())},
        event="message",
    )

    queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()

    # Register queue so /human-input can inject submitted events
    _active_streams[sid] = queue

    def _handler(evt: AgentEvent) -> None:
        queue.put_nowait(evt)

    unsub = assistant.on_event(_handler)

    try:
        # Convert multimodal content blocks to images for the Agent
        images = _content_blocks_to_images(content_blocks)

        # Run prompt in background to allow streaming
        run_task = asyncio.create_task(
            assistant.send_message(message, images=images or None)
        )

        # Check for immediate synchronous errors before starting
        agent_error = getattr(assistant.harness.state, "error_message", None)
        if agent_error:
            err = _classify_error(agent_error)
            yield _format_sse(
                {"type": "message.error", "messageId": _msg_id, "error": {**err, "message": agent_error}},
                event="message",
            )
            return

        # Stream events until AgentEnd
        while True:
            # Poll companion events
            if companion_queue is not None and not companion_queue.empty():
                cevt = companion_queue.get_nowait()
                yield _emit_v1(companion_event_to_v1(cevt))
                continue

            try:
                evt = await asyncio.wait_for(queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive (spec: every 15-30s)
                yield _format_sse({"type": "heart"}, event="heart")
                continue
            if evt is None:
                break
            # Handle synthetic HITL submitted events (not AgentEvent)
            if isinstance(evt, _HumanInputSubmitted):
                yield _format_sse(
                    {"actionType": "human_input.submitted", "toolCallId": evt.tool_call_id, "status": "accepted"},
                    event="action",
                )
                continue
            sse_out = agent_event_to_sse_json(evt, tracker=tracker)
            if sse_out is not None:
                yield _emit_v1(sse_out)
            if isinstance(evt, AgentEnd):
                break

        # Ensure the task is completed
        await run_task

        # Check for errors that occurred during agent execution
        agent_error = getattr(assistant.harness.state, "error_message", None)
        if agent_error:
            err = _classify_error(agent_error)
            err["retryable"] = True  # runtime errors are generally retryable
            yield _format_sse(
                {"type": "message.error", "messageId": _msg_id, "error": {**err, "message": agent_error}},
                event="message",
            )
    except asyncio.TimeoutError:
        yield _format_sse(
            {"type": "message.error", "messageId": _msg_id, "error": {"type": "timeout", "code": "E00008", "retryable": True, "message": "Request timed out"}},
            event="message",
        )
    except Exception as exc:
        err = _classify_error(str(exc))
        yield _format_sse(
            {"type": "message.error", "messageId": _msg_id, "error": {**err, "message": str(exc)}},
            event="message",
        )
    finally:
        _active_streams.pop(sid, None)
        unsub()
        yield "data: [DONE]\n\n"


@app.post("/chat/stream")
async def chat_stream(request: Request, chat_request: ChatRequest) -> StreamingResponse:
    session_id = request.query_params.get("session_id")
    persona_id = request.query_params.get("persona_id")
    current_request_headers.set(dict(request.headers))
    headers: dict[str, str] = dict(request.headers)
    companion_uid = headers.get("uid", "")
    # Validate: at least message or content must be provided
    if not chat_request.message and not chat_request.content:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=400,
            content={"code": "E00001", "info": "message or content is required",
                     "error": {"type": "invalid_request", "code": "missing_parameter", "retryable": False}},
        )
    return StreamingResponse(
        _event_stream(session_id, chat_request.message,
                      content_blocks=chat_request.content,
                      persona_id=persona_id,
                      provider_name=chat_request.provider, model_id=chat_request.model,
                      companion_uid=companion_uid),
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

    # Emit human_input.submitted event to the active SSE stream (spec §5.1)
    if accepted:
        q = _active_streams.get(session_id)
        if q is not None:
            q.put_nowait(_HumanInputSubmitted(
                tool_call_id=human_request.tool_call_id,
            ))

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


@app.get("/session")
async def get_session(request: Request) -> dict[str, Any]:
    """Get session history messages with skill mapping metadata."""
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

    # Load skill mapping from JSONL for history restoration
    skill_mapping = await manager.load_skill_mapping(session_id)

    return {
        "success": True,
        "session_id": session_id,
        "messages": messages,
        "skill_mapping": skill_mapping,
    }


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


@app.get("/models")
async def list_models() -> dict[str, Any]:
    """List available model configurations."""
    return {
        "current": {
            "provider": os.environ.get("AGENT_PROVIDER", "openai"),
            "model": os.environ.get("AGENT_MODEL", "gpt-4o"),
        },
        "available": [
            {"provider": "deepseek", "model": "deepseek-v4-flash", "label": "DeepSeek V4 Flash", "desc": "128K context, fast & cheap"},
            {"provider": "deepseek", "model": "deepseek-chat", "label": "DeepSeek Chat", "desc": "64K context, general"},
            {"provider": "deepseek", "model": "deepseek-reasoner", "label": "DeepSeek Reasoner", "desc": "64K context, reasoning"},
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

from scene.h5.channel_config import load_channels, save_channels  # noqa: E402

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


class EvolutionFeedbackRequest(BaseModel):
    trace_id: str = Field(..., min_length=1, max_length=200)
    feedback: str = Field(..., min_length=1, max_length=4000)
    was_helpful: bool | None = None


class EvolutionProposalAction(BaseModel):
    skill_name: str = Field(..., min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=500)


_evolution_cache: dict[str, list[dict[str, Any]]] = {}


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

    from scene.h5.evolution_config import build_skill_trace_collector

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
    """Run an evolution cycle and return proposals with diffs."""
    from agent_core.skill_evolution import (
        create_offline_evolution_agent,
        create_validation_gate,
    )

    agent = create_offline_evolution_agent("jsonl")
    result = await agent.run_evolution_cycle(
        skill_name=body.skill_name,
        min_traces=body.min_traces,
    )

    if result.get("status") != "completed" or not result.get("final_proposals"):
        return {
            "status": result.get("status", "error"),
            "reason": result.get("reason", result.get("message", "")),
            "trace_count": result.get("trace_count", result.get("traces_analyzed", 0)),
            "proposals": [],
        }

    gate = create_validation_gate(skill_dir=_get_skill_dir())
    proposals_out: list[dict[str, Any]] = []

    for p_dict in result["final_proposals"]:
        from agent_core.skill_evolution import PatchProposal
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
        diff = gate.diff_proposal(proposal)
        proposals_out.append({
            **p_dict,
            "diff": diff,
        })

    _evolution_cache[body.skill_name] = proposals_out

    return {
        "status": "completed",
        "cycle_id": result.get("cycle_id", ""),
        "traces_analyzed": result.get("traces_analyzed", 0),
        "proposals_generated": result.get("proposals_generated", 0),
        "conflicts": result.get("conflicts", 0),
        "discarded": result.get("discarded", 0),
        "proposals": proposals_out,
    }


@app.get("/skills/evolution/proposals/{skill_name}")
async def get_evolution_proposals(skill_name: str) -> dict[str, Any]:
    """Get cached proposals for a skill from the last analyze call."""
    proposals = _evolution_cache.get(skill_name, [])
    return {"skill_name": skill_name, "proposals": proposals}


@app.post("/skills/evolution/proposals/{proposal_id}/accept")
async def accept_evolution_proposal(
    proposal_id: str,
    body: EvolutionProposalAction,
) -> dict[str, Any]:
    """Validate and apply an accepted proposal, writing audit log."""
    from agent_core.skill_evolution import (
        PatchProposal,
        create_validation_gate,
        write_audit_entry,
    )

    proposals = _evolution_cache.get(body.skill_name, [])
    p_dict = next((p for p in proposals if p.get("proposal_id") == proposal_id), None)
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

    gate = create_validation_gate(skill_dir=_get_skill_dir(), require_human_review=False)
    result = await gate.validate(proposal)
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

    # Remove from cache on success
    if applied:
        _evolution_cache[body.skill_name] = [
            p for p in proposals if p.get("proposal_id") != proposal_id
        ]

    return {"success": applied, "audit_id": audit_id, "validation_score": result.score_delta}


@app.post("/skills/evolution/proposals/{proposal_id}/reject")
async def reject_evolution_proposal(
    proposal_id: str,
    body: EvolutionProposalAction,
) -> dict[str, Any]:
    """Reject a proposal and write audit log (no skill file modification)."""
    from agent_core.skill_evolution import write_audit_entry

    proposals = _evolution_cache.get(body.skill_name, [])
    p_dict = next((p for p in proposals if p.get("proposal_id") == proposal_id), None)
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

    _evolution_cache[body.skill_name] = [
        p for p in proposals if p.get("proposal_id") != proposal_id
    ]

    return {"success": True, "audit_id": audit_id}


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
    uvicorn.run("scene.h5.server:app", host="0.0.0.0", port=port, reload=False)
