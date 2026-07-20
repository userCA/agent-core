"""Execute sub-agents: single / parallel / chain with concurrency limits."""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Awaitable, Callable

from agent_core.core.content import TextContent
from agent_core.core.messages import AssistantMessage
from agent_core.multi_agent.profile_registry import AgentProfileRegistry
from agent_core.multi_agent.sub_agent_factory import SubAgentFactory
from agent_core.multi_agent.types import AgentProfile, SubAgentResult, SubAgentStatus
from agent_core.session.harness import AgentHarness
from agent_core.session.store import SessionStore

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


def _assistant_text(msg: AssistantMessage | None) -> str:
    if msg is None:
        return ""
    parts: list[str] = []
    for c in msg.content:
        if isinstance(c, TextContent):
            parts.append(c.text)
    return "".join(parts)


def _usage_dict(msg: AssistantMessage | None) -> dict[str, int | float]:
    if msg is None or msg.usage is None:
        return {}
    u = msg.usage
    return {
        "input": u.input_tokens,
        "output": u.output_tokens,
    }


class SubAgentRunner:
    def __init__(
        self,
        *,
        factory: SubAgentFactory,
        registry: AgentProfileRegistry,
        store: SessionStore,
        max_concurrent_agents: int = 4,
        cleanup_sub_sessions: bool = False,
    ) -> None:
        self._factory = factory
        self._registry = registry
        self._store = store
        self._global_sem = asyncio.Semaphore(max_concurrent_agents)
        self._profile_sems: dict[str, asyncio.Semaphore] = {}
        self._cleanup = cleanup_sub_sessions
        self._active: dict[str, AgentHarness] = {}
        self._lock = asyncio.Lock()

    def _profile_sem(self, profile: AgentProfile) -> asyncio.Semaphore:
        if profile.name not in self._profile_sems:
            self._profile_sems[profile.name] = asyncio.Semaphore(
                max(1, profile.max_concurrency)
            )
        return self._profile_sems[profile.name]

    async def abort_all(self) -> None:
        async with self._lock:
            harnesses = list(self._active.values())
        for h in harnesses:
            h.abort()

    async def _emit(
        self, on_progress: ProgressCallback | None, payload: dict[str, Any]
    ) -> None:
        if on_progress is None:
            return
        result = on_progress(payload)
        if inspect.isawaitable(result):
            await result

    async def run_single(
        self,
        profile: AgentProfile,
        task: str,
        *,
        delegation_id: str,
        mode: str = "single",
        index: int = 0,
        total: int = 1,
        signal: asyncio.Event | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> SubAgentResult:
        await self._emit(
            on_progress,
            {
                "type": "delegation",
                "phase": "agent_start",
                "mode": mode,
                "delegation_id": delegation_id,
                "agent": profile.name,
                "task": task,
                "status": "running",
                "index": index,
                "total": total,
            },
        )
        started = time.perf_counter()
        harness: AgentHarness | None = None
        session_id: str | None = None
        try:
            async with self._global_sem:
                async with self._profile_sem(profile):
                    if signal is not None and signal.is_set():
                        return SubAgentResult(
                            agent_name=profile.name,
                            task=task,
                            status="aborted",
                            response_text="",
                            error_message="aborted before start",
                            duration_ms=int((time.perf_counter() - started) * 1000),
                        )
                    harness, session_id = await self._factory.create(profile)
                    async with self._lock:
                        self._active[session_id] = harness
                    if signal is not None:

                        async def _watch_abort() -> None:
                            while not signal.is_set():
                                await asyncio.sleep(0.05)
                            harness.abort()

                        watcher = asyncio.create_task(_watch_abort())
                    else:
                        watcher = None
                    try:
                        assistant = await harness.prompt(task)
                    finally:
                        if watcher is not None:
                            watcher.cancel()
                            try:
                                await watcher
                            except asyncio.CancelledError:
                                pass
                    text = _assistant_text(assistant)
                    result_status: SubAgentStatus
                    if signal is not None and signal.is_set():
                        result_status = "aborted"
                    elif assistant.stop_reason == "aborted":
                        result_status = "aborted"
                    elif assistant.stop_reason == "error":
                        result_status = "failed"
                    else:
                        result_status = "completed"
                    result = SubAgentResult(
                        agent_name=profile.name,
                        task=task,
                        status=result_status,
                        response_text=text,
                        usage=_usage_dict(assistant),
                        duration_ms=int((time.perf_counter() - started) * 1000),
                        error_message=assistant.error_message,
                        session_id=session_id,
                    )
        except Exception as exc:
            result = SubAgentResult(
                agent_name=profile.name,
                task=task,
                status="failed",
                response_text="",
                duration_ms=int((time.perf_counter() - started) * 1000),
                error_message=str(exc),
                session_id=session_id,
            )
        finally:
            if session_id is not None:
                async with self._lock:
                    self._active.pop(session_id, None)
                if harness is not None:
                    await harness.dispose()
                if self._cleanup:
                    await self._store.delete_session(session_id)

        await self._emit(
            on_progress,
            {
                "type": "delegation",
                "phase": "agent_end",
                "mode": mode,
                "delegation_id": delegation_id,
                "agent": profile.name,
                "task": task,
                "status": result.status,
                "index": index,
                "total": total,
                "summary": (result.response_text or "")[:200],
                "error_message": result.error_message,
                "session_id": result.session_id,
            },
        )
        return result

    async def run_parallel(
        self,
        tasks: list[tuple[AgentProfile, str]],
        *,
        delegation_id: str,
        signal: asyncio.Event | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[SubAgentResult]:
        total = len(tasks)

        async def _one(i: int, profile: AgentProfile, task: str) -> SubAgentResult:
            return await self.run_single(
                profile,
                task,
                delegation_id=delegation_id,
                mode="parallel",
                index=i,
                total=total,
                signal=signal,
                on_progress=on_progress,
            )

        return list(
            await asyncio.gather(
                *[_one(i, p, t) for i, (p, t) in enumerate(tasks)]
            )
        )

    async def run_chain(
        self,
        tasks: list[tuple[AgentProfile, str]],
        *,
        delegation_id: str,
        signal: asyncio.Event | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[SubAgentResult]:
        results: list[SubAgentResult] = []
        previous = ""
        total = len(tasks)
        for i, (profile, task) in enumerate(tasks):
            resolved = task.replace("{previous}", previous)
            result = await self.run_single(
                profile,
                resolved,
                delegation_id=delegation_id,
                mode="chain",
                index=i,
                total=total,
                signal=signal,
                on_progress=on_progress,
            )
            results.append(result)
            previous = result.response_text or ""
            if result.status != "completed":
                break
        return results
