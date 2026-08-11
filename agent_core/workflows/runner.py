"""WorkflowRunner: load → validate → execute → checkpoint → progress."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from agent_core.multi_agent.profile_registry import AgentProfileRegistry
from agent_core.multi_agent.sub_agent_runner import SubAgentRunner
from agent_core.session.harness import AgentHarness
from agent_core.workflows.errors import CheckpointError, QuotaExceeded, SandboxError
from agent_core.workflows.loader import WorkflowLoader, _extract_meta
from agent_core.workflows.runtime import ProgressCallback, WorkflowContext
from agent_core.workflows.sandbox import (
    build_sandbox_globals,
    pattern_sandbox_extras,
    validate_workflow_source,
)
from agent_core.workflows.store import WorkflowStore
from agent_core.workflows.types import (
    WorkflowCheckpoint,
    WorkflowMeta,
    WorkflowOptions,
    WorkflowProgress,
    WorkflowRunResult,
    WorkflowStatus,
)


class _RunnerWorkflowContext(WorkflowContext):
    """WorkflowContext with checkpoint snapshot helper for the runner."""

    def to_checkpoint(
        self,
        *,
        status: WorkflowStatus,
        error_message: str | None = None,
    ) -> WorkflowCheckpoint:
        return WorkflowCheckpoint(
            run_id=self._run_id,
            workflow_name=self._workflow_name,
            status=status,
            current_phase=self._current_phase,
            completed_phases=sorted(self._completed_phases),
            all_phases=list(self._phases),
            phase_outputs=dict(self._phase_outputs),
            args=dict(self._args),
            agent_invocation_count=self._agent_invocation_count,
            updated_at=time.time(),
            log=list(self._log),
        )


class WorkflowRunner:
    """Orchestrates workflow loading, sandbox execution, checkpoints, and progress."""

    def __init__(
        self,
        *,
        loader: WorkflowLoader,
        store: WorkflowStore | None,
        runner: SubAgentRunner,
        registry: AgentProfileRegistry,
        options: WorkflowOptions,
        parent_harness: AgentHarness | None = None,
    ) -> None:
        self._loader = loader
        self._store = store
        self._runner = runner
        self._registry = registry
        self._options = options
        self._parent_harness = parent_harness
        self._abort_signal = asyncio.Event()
        self._current_run_id: str | None = None

    async def run(
        self,
        *,
        name: str | None = None,
        args: dict | None = None,
        resume_run_id: str | None = None,
        inline_source: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> WorkflowRunResult:
        self._abort_signal.clear()
        resume_cp: WorkflowCheckpoint | None = None

        if resume_run_id:
            if self._store is None:
                raise CheckpointError(f"No store configured for resume: {resume_run_id}")
            resume_cp = await self._store.load_checkpoint(resume_run_id)
            if resume_cp is None:
                raise CheckpointError(f"Checkpoint not found: {resume_run_id}")

        try:
            source, meta = self._resolve_source(
                name=name,
                inline_source=inline_source,
                resume_cp=resume_cp,
            )
        except (KeyError, SandboxError, ValueError) as exc:
            return WorkflowRunResult(
                run_id=resume_run_id or str(uuid.uuid4()),
                name=name or (resume_cp.workflow_name if resume_cp else "unknown"),
                status="failed",
                error_message=str(exc),
            )

        run_id = resume_run_id or str(uuid.uuid4())
        self._current_run_id = run_id
        run_args = dict(args if args is not None else (resume_cp.args if resume_cp else {}))

        tree = validate_workflow_source(source)
        ctx: _RunnerWorkflowContext | None = None

        async def _save_checkpoint(
            status: WorkflowStatus,
            *,
            error_message: str | None = None,
            result: Any | None = None,
        ) -> WorkflowCheckpoint | None:
            if ctx is None:
                return None
            cp = ctx.to_checkpoint(status=status, error_message=error_message)
            if self._store is not None:
                await self._store.save_checkpoint(cp)
            progress = WorkflowProgress(
                run_id=run_id,
                name=meta.name,
                status=status,
                phase=ctx.current_phase,
                phases=meta.phases,
                log=ctx.logs,
                progress={
                    "completed_phases": len(ctx._completed_phases),
                    "total_phases": len(meta.phases),
                    "completed_agents": ctx._pipeline_completed_agents,
                    "total_agents": ctx._pipeline_total_agents or 0,
                },
                error_message=error_message,
                result=result,
            )
            if on_progress is not None:
                cb_result = on_progress(progress.model_dump())
                if asyncio.iscoroutine(cb_result):
                    await cb_result
            return cp

        async def _emit_and_maybe_checkpoint(payload: dict[str, Any]) -> None:
            if on_progress is not None:
                cb_result = on_progress(payload)
                if asyncio.iscoroutine(cb_result):
                    await cb_result
            if self._options.auto_checkpoint_phases and ctx is not None:
                await _save_checkpoint("running")

        ctx = _RunnerWorkflowContext(
            run_id=run_id,
            workflow_name=meta.name,
            phases=meta.phases,
            args=run_args,
            runner=self._runner,
            registry=self._registry,
            parent_harness=self._parent_harness,
            max_agent_invocations=self._options.max_agent_invocations,
            on_progress=_emit_and_maybe_checkpoint,
            resume=resume_cp,
            abort_signal=self._abort_signal,
        )

        try:
            namespace = build_sandbox_globals(
                ctx,
                run_args,
                extras=pattern_sandbox_extras(),
            )
            exec(compile(tree, "<workflow>", "exec"), namespace)
            run_fn = namespace.get("run")
            if run_fn is None or not asyncio.iscoroutinefunction(run_fn):
                raise SandboxError("Workflow must define async def run(ctx)")

            result = await run_fn(ctx)

            if self._abort_signal.is_set():
                cp = await _save_checkpoint("aborted", error_message="Workflow aborted")
                return WorkflowRunResult(
                    run_id=run_id,
                    name=meta.name,
                    status="aborted",
                    error_message="Workflow aborted",
                    checkpoint=cp,
                )

            cp = await _save_checkpoint("completed", result=result)
            return WorkflowRunResult(
                run_id=run_id,
                name=meta.name,
                status="completed",
                result=result,
                checkpoint=cp,
            )

        except QuotaExceeded as exc:
            cp = await _save_checkpoint("failed", error_message=str(exc))
            return WorkflowRunResult(
                run_id=run_id,
                name=meta.name,
                status="failed",
                error_message=str(exc),
                checkpoint=cp,
            )

        except asyncio.CancelledError:
            cp = await _save_checkpoint("aborted", error_message="Workflow cancelled")
            raise

        except Exception as exc:
            cp = await _save_checkpoint("failed", error_message=str(exc))
            return WorkflowRunResult(
                run_id=run_id,
                name=meta.name,
                status="failed",
                error_message=str(exc),
                checkpoint=cp,
            )

        finally:
            self._current_run_id = None

    async def abort(self, run_id: str | None = None) -> None:
        if run_id is not None and self._current_run_id != run_id:
            return
        self._abort_signal.set()
        await self._runner.abort_all()

    def _resolve_source(
        self,
        *,
        name: str | None,
        inline_source: str | None,
        resume_cp: WorkflowCheckpoint | None,
    ) -> tuple[str, WorkflowMeta]:
        if inline_source is not None:
            if not self._options.enable_dynamic_exec:
                raise SandboxError("inline_source requires enable_dynamic_exec=True")
            tree = validate_workflow_source(inline_source)
            fallback = name or (
                resume_cp.workflow_name if resume_cp is not None else "inline"
            )
            meta = _extract_meta(tree, fallback)
            return inline_source, meta

        workflow_name = name or (resume_cp.workflow_name if resume_cp else None)
        if workflow_name is None:
            raise ValueError("name is required when not using inline_source")

        spec = self._loader.get(workflow_name)
        return spec.source, spec.meta
