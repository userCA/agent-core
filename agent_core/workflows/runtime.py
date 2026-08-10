"""Workflow runtime primitives — WorkflowContext."""

from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any, Awaitable, Callable

from agent_core.multi_agent.profile_registry import AgentProfileRegistry
from agent_core.multi_agent.sub_agent_runner import SubAgentRunner
from agent_core.multi_agent.types import AgentProfile
from agent_core.session.harness import AgentHarness
from agent_core.workflows.errors import QuotaExceeded
from agent_core.workflows.types import WorkflowCheckpoint, WorkflowProgress

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None] | None]

_MAX_LOG_ENTRIES = 200


class WorkflowContext:
    def __init__(
        self,
        *,
        run_id: str,
        workflow_name: str,
        phases: list[str],
        args: dict[str, Any],
        runner: SubAgentRunner,
        registry: AgentProfileRegistry,
        parent_harness: AgentHarness | None = None,
        max_agent_invocations: int = 100,
        on_progress: ProgressCallback | None = None,
        resume: WorkflowCheckpoint | None = None,
        abort_signal: asyncio.Event | None = None,
    ) -> None:
        self._run_id = run_id
        self._workflow_name = workflow_name
        self._phases = list(phases)
        self._args = dict(args)
        self._runner = runner
        self._registry = registry
        self._parent_harness = parent_harness
        self._max_agent_invocations = max_agent_invocations
        self._on_progress = on_progress
        self._abort_signal = abort_signal

        self._current_phase: str | None = None
        self._agent_invocation_count = 0
        self._log: list[str] = []
        self._completed_phases: set[str] = set()
        self._phase_outputs: dict[str, Any] = {}

        if resume is not None:
            self._completed_phases = set(resume.completed_phases)
            self._phase_outputs = dict(resume.phase_outputs)
            self._agent_invocation_count = resume.agent_invocation_count
            if resume.log:
                self._log = list(resume.log[-_MAX_LOG_ENTRIES:])

    @property
    def args(self) -> dict[str, Any]:
        return dict(self._args)

    @property
    def current_phase(self) -> str | None:
        return self._current_phase

    @property
    def agent_invocation_count(self) -> int:
        return self._agent_invocation_count

    @property
    def logs(self) -> list[str]:
        return list(self._log)

    async def _emit_progress(self, *, phase: str | None = None) -> None:
        if self._on_progress is None:
            return
        payload = WorkflowProgress(
            run_id=self._run_id,
            name=self._workflow_name,
            status="running",
            phase=phase if phase is not None else self._current_phase,
            phases=self._phases,
            log=list(self._log),
            progress={
                "completed_phases": len(self._completed_phases),
                "total_phases": len(self._phases),
            },
        ).model_dump()
        result = self._on_progress(payload)
        if inspect.isawaitable(result):
            await result

    async def phase(self, name: str) -> None:
        if name in self._completed_phases:
            return
        self._current_phase = name
        await self._emit_progress(phase=name)

    def log(self, message: str) -> None:
        self._log.append(message)
        if len(self._log) > _MAX_LOG_ENTRIES:
            self._log = self._log[-_MAX_LOG_ENTRIES:]

    def is_phase_done(self, name: str) -> bool:
        return name in self._completed_phases

    def set_phase_output(self, name: str, value: Any) -> None:
        self._phase_outputs[name] = value
        self._completed_phases.add(name)

    def get_phase_output(self, name: str) -> Any:
        return self._phase_outputs[name]

    def _resolve_profile(self, profile_name: str | None) -> AgentProfile:
        if profile_name is not None:
            profile = self._registry.resolve(profile_name)
            if profile is None:
                raise ValueError(f"Unknown agent profile: {profile_name}")
            return profile
        profile = self._registry.resolve("default")
        if profile is not None:
            return profile
        profiles = self._registry.list()
        if not profiles:
            raise ValueError("No agent profiles registered")
        return profiles[0]

    async def agent(
        self,
        prompt: str,
        *,
        profile: str | None = None,
        label: str | None = None,
        schema: dict | None = None,
    ) -> Any:
        if self._abort_signal is not None and self._abort_signal.is_set():
            raise RuntimeError("Workflow aborted")

        self._agent_invocation_count += 1
        if self._agent_invocation_count > self._max_agent_invocations:
            raise QuotaExceeded(
                f"max_agent_invocations ({self._max_agent_invocations}) exceeded"
            )

        resolved = self._resolve_profile(profile)
        task = prompt
        if schema is not None:
            task = (
                f"{prompt}\n\n"
                "Respond with JSON only, matching this schema:\n"
                f"{json.dumps(schema, indent=2)}"
            )

        delegation_id = f"{self._run_id}:{self._agent_invocation_count}"
        result = await self._runner.run_single(
            resolved,
            task,
            delegation_id=delegation_id,
            signal=self._abort_signal,
        )
        text = result.response_text or ""

        if schema is None:
            return text

        return await self._parse_json_response(resolved, task, text, schema, delegation_id)

    async def _parse_json_response(
        self,
        profile: AgentProfile,
        task: str,
        text: str,
        schema: dict,
        delegation_id: str,
    ) -> Any:
        for attempt in range(2):
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                if attempt == 0:
                    retry_task = (
                        f"{task}\n\n"
                        "Your previous response was not valid JSON. "
                        "Respond with JSON only, no markdown fences."
                    )
                    retry = await self._runner.run_single(
                        profile,
                        retry_task,
                        delegation_id=f"{delegation_id}:retry",
                        signal=self._abort_signal,
                    )
                    text = retry.response_text or ""
                else:
                    return {"raw": text, "parse_error": str(exc)}
        return {"raw": text, "parse_error": "unknown parse failure"}

    async def pipeline(
        self,
        items: list[Any],
        map_fn: Callable[..., Awaitable[Any]],
        *,
        concurrency: int | None = None,
    ) -> list[Any]:
        if not items:
            return []

        if concurrency is None or concurrency <= 1:
            results: list[Any] = []
            for index, item in enumerate(items):
                results.append(await map_fn(item, index))
            return results

        sem = asyncio.Semaphore(concurrency)
        ordered: list[Any | None] = [None] * len(items)

        async def _run(index: int, item: Any) -> None:
            async with sem:
                ordered[index] = await map_fn(item, index)

        await asyncio.gather(*[_run(i, item) for i, item in enumerate(items)])
        return ordered  # type: ignore[return-value]
