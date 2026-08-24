"""A2A (Agent2Agent) protocol client — JSON-RPC + SSE transport.

Implements the standard A2A wire protocol against a remote agent:

- Agent Card discovery:  ``GET /.well-known/agent-card.json``
- Task lifecycle:        ``message/send``, ``tasks/get``, ``tasks/cancel``
- Streaming (optional):  ``tasks/resubscribe`` over SSE

The client is intentionally thin: it speaks JSON-RPC 2.0 over HTTP(S) and
maps A2A ``Task`` objects onto :class:`A2ATask`.  Orchestration concerns
(progress events, abort, timeout) live in :class:`A2AClient.run_task`.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import time
import uuid
from typing import Any, Awaitable, Callable

import httpx
from pydantic import BaseModel, ConfigDict

TERMINAL_STATES = frozenset({"completed", "failed", "canceled", "rejected"})
INPUT_REQUIRED_STATE = "input-required"


class A2AError(Exception):
    """Raised when the remote A2A agent returns an RPC error or times out."""


# ---------------------------------------------------------------------------
# A2A objects (tolerant models — servers vary in optional fields)
# ---------------------------------------------------------------------------

class A2AAgentCard(BaseModel):
    """Agent Card as advertised at ``/.well-known/agent-card.json``."""

    model_config = ConfigDict(extra="allow")

    name: str
    description: str = ""
    url: str | None = None
    version: str | None = None
    skills: list[dict[str, Any]] = []
    capabilities: dict[str, Any] = {}
    defaultInputModes: list[str] = []
    defaultOutputModes: list[str] = []
    securitySchemes: dict[str, Any] = {}


class A2AStatus(BaseModel):
    model_config = ConfigDict(extra="allow")

    state: str
    message: dict[str, Any] | None = None
    timestamp: str | None = None


class A2ATask(BaseModel):
    """A2A Task — one execution of a message against a remote agent."""

    model_config = ConfigDict(extra="allow")

    id: str
    status: A2AStatus
    artifacts: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    historyLength: int | None = None
    metadata: dict[str, Any] = {}

    # -- helpers ---------------------------------------------------------

    @property
    def state(self) -> str:
        return self.status.state

    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def needs_input(self) -> bool:
        return self.state == INPUT_REQUIRED_STATE

    def output_text(self) -> str:
        """Concatenate text from agent messages and artifacts (best effort)."""
        parts: list[str] = []
        for msg in self.messages:
            if isinstance(msg, dict) and msg.get("role") == "agent":
                parts.extend(_parts_to_text(msg.get("parts", [])))
        for artifact in self.artifacts:
            if isinstance(artifact, dict):
                parts.extend(_parts_to_text(artifact.get("parts", [])))
        return "\n".join(t for t in parts if t)

    def status_message(self) -> str:
        """Human-readable message attached to the status, if any."""
        m = self.status.message or {}
        if not isinstance(m, dict):
            return ""
        return str(m.get("message") or "")


def _parts_to_text(parts: list[Any]) -> list[str]:
    out: list[str] = []
    for p in parts or []:
        if not isinstance(p, dict):
            continue
        kind = p.get("type")
        if kind == "text":
            text = p.get("text")
            if text:
                out.append(str(text))
        elif kind == "file":
            f = p.get("file") or {}
            out.append(f"[file: {f.get('name', 'file')} ({f.get('mimeType', '')})]")
        elif kind == "data":
            data = p.get("data") or {}
            out.append(f"[data: {json.dumps(data, ensure_ascii=False)}]")
        else:
            out.append(f"[part: {kind}]")
    return out


ProgressCallback = Callable[[A2ATask], Any]


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class A2AClient:
    """JSON-RPC 2.0 A2A client over HTTP(S)."""

    def __init__(
        self,
        base_url: str,
        *,
        token_env: str | None = None,
        token: str | None = None,
        timeout: float = 120.0,
        poll_interval: float = 2.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._token = token or (os.environ.get(token_env) if token_env else None)
        self._http = http_client
        self._owns_client = http_client is None

    # -- transport -------------------------------------------------------

    def _headers(self, *, sse: bool = False) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if sse:
            headers["Accept"] = "text/event-stream"
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _post_rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """POST a JSON-RPC request and return ``result`` (raising on error)."""
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
        client = self._http or httpx.AsyncClient(timeout=self.timeout)
        try:
            resp = await client.post(self.base_url, json=payload, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
        finally:
            if self._owns_client:
                await client.aclose()
        if isinstance(data, dict) and data.get("error"):
            err = data["error"]
            raise A2AError(
                f"A2A RPC {method} failed: code={err.get('code')} "
                f"message={err.get('message')}"
            )
        result = data.get("result") if isinstance(data, dict) else None
        if not isinstance(result, dict):
            raise A2AError(f"A2A RPC {method} returned no result")
        return result

    # -- discovery -------------------------------------------------------

    async def fetch_agent_card(self, *, card_url: str | None = None) -> A2AAgentCard:
        """Fetch the remote Agent Card from ``/.well-known/agent-card.json``."""
        url = card_url or f"{self.base_url}/.well-known/agent-card.json"
        client = self._http or httpx.AsyncClient(timeout=self.timeout)
        try:
            resp = await client.get(url, headers=self._headers())
            resp.raise_for_status()
            return A2AAgentCard.model_validate(resp.json())
        finally:
            if self._owns_client:
                await client.aclose()

    # -- task lifecycle --------------------------------------------------

    async def send_message(
        self,
        prompt: str,
        *,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> A2ATask:
        """Create (or continue) a task with a user text message."""
        params: dict[str, Any] = {
            "message": {"role": "user", "parts": [{"type": "text", "text": prompt}]},
        }
        if task_id:
            params["id"] = task_id
        if metadata:
            params["metadata"] = metadata
        result = await self._post_rpc("message/send", params)
        return A2ATask.model_validate(result)

    async def get_task(self, task_id: str) -> A2ATask:
        result = await self._post_rpc("tasks/get", {"id": task_id})
        return A2ATask.model_validate(result)

    async def cancel_task(self, task_id: str) -> A2ATask:
        result = await self._post_rpc("tasks/cancel", {"id": task_id})
        return A2ATask.model_validate(result)

    async def subscribe(
        self,
        task_id: str,
        *,
        on_update: ProgressCallback | None = None,
    ) -> A2ATask | None:
        """Subscribe to task events over SSE (``tasks/resubscribe``).

        Returns the last task observed, or ``None`` if the stream closed
        without a terminal state.  ``on_update`` is invoked for every event
        (sync or async callables are both supported).
        """
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tasks/resubscribe",
            "params": {
                "id": task_id,
                "pushNotificationConfig": {
                    "types": ["STATE_UPDATED", "TASK_INPUT_REQUIRED"],
                },
            },
        }
        client = self._http or httpx.AsyncClient(timeout=self.timeout)
        try:
            async with client.stream(
                "POST", self.base_url, json=payload, headers=self._headers(sse=True)
            ) as resp:
                resp.raise_for_status()
                final: A2ATask | None = None
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if not data_str:
                        continue
                    try:
                        frame = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    result = frame.get("result") if isinstance(frame, dict) else None
                    if not isinstance(result, dict):
                        continue
                    task = A2ATask.model_validate(result)
                    final = task
                    if on_update is not None:
                        res = on_update(task)
                        if inspect.isawaitable(res):
                            await res
                    if task.is_terminal():
                        return task
                return final
        finally:
            if self._owns_client:
                await client.aclose()

    # -- orchestration helper -------------------------------------------

    async def run_task(
        self,
        prompt: str,
        *,
        ctx: Any | None = None,
        metadata: dict[str, Any] | None = None,
        task_id: str | None = None,
        max_wait_seconds: float | None = None,
        poll_interval: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> A2ATask:
        """Send a task, then poll ``tasks/get`` until terminal / input-required.

        - ``ctx.signal`` (asyncio.Event) aborts via ``tasks/cancel``.
        - ``on_progress`` is invoked after each status change (sync or async).
        - Raises :class:`A2AError` on timeout.
        """
        max_wait = max_wait_seconds if max_wait_seconds is not None else self.timeout
        poll = poll_interval if poll_interval is not None else self.poll_interval
        started = time.monotonic()

        task = await self.send_message(prompt, task_id=task_id, metadata=metadata)
        await self._notify(on_progress, task)
        if task.is_terminal() or task.needs_input():
            return task

        while True:
            if ctx is not None and getattr(ctx, "signal", None) is not None and ctx.signal.is_set():
                return await self.cancel_task(task.id)
            if time.monotonic() - started >= max_wait:
                raise A2AError(
                    f"A2A task {task.id} timed out after {max_wait:.0f}s "
                    f"(status={task.state})"
                )
            await asyncio.sleep(poll)
            task = await self.get_task(task.id)
            await self._notify(on_progress, task)
            if task.is_terminal() or task.needs_input():
                return task

    @staticmethod
    async def _notify(cb: ProgressCallback | None, task: A2ATask) -> None:
        if cb is None:
            return
        res = cb(task)
        if inspect.isawaitable(res):
            await res
