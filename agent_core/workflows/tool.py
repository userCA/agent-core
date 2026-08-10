"""run_workflow tool — execute dynamic workflow scripts via WorkflowRunner."""

from __future__ import annotations

import json
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import ToolContext, ToolDefinition, ToolResult
from agent_core.workflows.runner import WorkflowRunner
from agent_core.workflows.types import WorkflowProgress, WorkflowRunResult

_SUMMARY_MAX_CHARS = 2000


def _short_result(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(value)
    return text


def _format_summary(result: WorkflowRunResult, progress: WorkflowProgress) -> str:
    phase = progress.phase or ""
    short = _short_result(result.result if result.status == "completed" else result.error_message)
    header = f"[workflow:{result.name}] status={result.status} phase={phase}"
    if short:
        text = f"{header}\n{short}"
    else:
        text = header
    if len(text) > _SUMMARY_MAX_CHARS:
        text = text[: _SUMMARY_MAX_CHARS - 3] + "..."
    return text


def _progress_from_result(result: WorkflowRunResult) -> WorkflowProgress:
    cp = result.checkpoint
    phases: list[str] = []
    phase: str | None = None
    log: list[str] = []
    progress: dict[str, int] = {}
    if cp is not None:
        phase = cp.current_phase
        log = list(cp.log)
        progress = {
            "completed_phases": len(cp.completed_phases),
        }
    return WorkflowProgress(
        run_id=result.run_id,
        name=result.name,
        status=result.status,
        phase=phase,
        phases=phases,
        log=log,
        progress=progress,
        error_message=result.error_message,
        result=result.result,
    )


class RunWorkflowTool:
    def __init__(
        self,
        *,
        runner: WorkflowRunner,
        name: str = "run_workflow",
        enable_dynamic_exec: bool = False,
    ) -> None:
        self._runner = runner
        self._enable_dynamic_exec = enable_dynamic_exec
        self.definition = ToolDefinition(
            name=name,
            description=(
                "Run a workflow script: static assets from .pi/workflows/ or "
                "inline_source when dynamic execution is enabled. "
                "Use resume_run_id to continue from a checkpoint."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Workflow asset name (required unless inline_source)",
                    },
                    "args": {
                        "type": "object",
                        "description": "Arguments passed to the workflow script",
                    },
                    "resume_run_id": {
                        "type": "string",
                        "description": "Resume from a saved checkpoint run id",
                    },
                    "inline_source": {
                        "type": "string",
                        "description": "Inline workflow source (requires enable_dynamic_exec)",
                    },
                },
            },
        )

    async def execute(
        self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext
    ) -> ToolResult:
        inline_source = params.get("inline_source")
        if inline_source is not None and not self._enable_dynamic_exec:
            progress = WorkflowProgress(
                run_id="",
                name=params.get("name") or "inline",
                status="failed",
                error_message="inline_source requires enable_dynamic_exec=True",
            )
            msg = progress.error_message or "Workflow failed"
            return ToolResult(
                content=[TextContent(text=msg)],
                details={"workflow": progress.model_dump()},
            )

        name = params.get("name")
        args = params.get("args")
        resume_run_id = params.get("resume_run_id")

        async def on_progress(progress_dict: dict[str, Any]) -> None:
            if ctx.on_update is not None:
                ctx.on_update(
                    ToolResult(
                        content=[TextContent(text="")],
                        details={"workflow": progress_dict},
                    )
                )

        try:
            result = await self._runner.run(
                name=str(name) if name is not None else None,
                args=args if isinstance(args, dict) else None,
                resume_run_id=str(resume_run_id) if resume_run_id else None,
                inline_source=str(inline_source) if inline_source is not None else None,
                on_progress=on_progress,
            )
        except Exception as exc:
            progress = WorkflowProgress(
                run_id=str(resume_run_id or ""),
                name=str(name or "unknown"),
                status="failed",
                error_message=str(exc),
            )
            return ToolResult(
                content=[TextContent(text=f"Workflow failed: {exc}")],
                details={"workflow": progress.model_dump()},
            )

        final_progress = _progress_from_result(result)
        if result.checkpoint is not None and result.checkpoint.completed_phases:
            final_progress.progress["completed_phases"] = len(
                result.checkpoint.completed_phases
            )

        summary = _format_summary(result, final_progress)
        return ToolResult(
            content=[TextContent(text=summary)],
            details={"workflow": final_progress.model_dump()},
        )
