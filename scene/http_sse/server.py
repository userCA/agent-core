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

from scene.http_sse.events import agent_event_to_sse_json
from scene.http_sse.manager import SessionManager
from scene.http_sse.request_context import current_request_headers


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=100_000)


class HumanInputRequest(BaseModel):
    tool_call_id: str = Field(..., min_length=1)
    values: dict[str, Any] = Field(default_factory=dict)


manager = SessionManager(cwd=os.getcwd())


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await manager.dispose_all()


app = FastAPI(title="Agent Core HTTP SSE Chat", lifespan=lifespan)


def _format_sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def _event_stream(
    session_id: str | None,
    message: str,
) -> AsyncIterator[str]:
    """Yield SSE-formatted events for a chat turn."""
    sid, assistant = await manager.get_or_create(session_id)

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
    current_request_headers.set(dict(request.headers))
    return StreamingResponse(
        _event_stream(session_id, chat_request.message),
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


@app.post("/abort")
async def abort_session(request: Request) -> dict[str, Any]:
    """Abort the current operation for a session."""
    session_id = request.query_params.get("session_id")
    if not session_id:
        return {"success": False, "error": "Missing session_id"}

    _, assistant = await manager.get_or_create(session_id)
    assistant.abort()
    return {"success": True}


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
