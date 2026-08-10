"""System prompt snippets for workflow orchestration."""

from __future__ import annotations

from agent_core.workflows.types import WorkflowMeta


def workflow_prompt_snippet(*, workflows: list[WorkflowMeta] | None = None) -> str:
    lines = [
        "Use `run_workflow` for multi-step or parallel tasks defined as workflow scripts.",
        "Pass `name` (workflow asset id) and optional `args` (object).",
        "Use `resume_run_id` to continue a paused/failed run from the last phase checkpoint.",
        "Workflow intermediate state stays out of this conversation; only the final summary returns.",
    ]
    if workflows:
        names = ", ".join(w.name for w in workflows[:12])
        if names:
            lines.append(f"Available workflows: {names}.")
    return "\n".join(lines)
