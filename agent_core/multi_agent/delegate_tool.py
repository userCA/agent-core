"""delegate_task tool — routes work to expert sub-agents."""

from __future__ import annotations

import uuid
from typing import Any

from agent_core.core.content import TextContent
from agent_core.multi_agent.profile_registry import AgentProfileRegistry
from agent_core.multi_agent.sub_agent_runner import SubAgentRunner
from agent_core.multi_agent.types import AgentProfile, SubAgentResult
from agent_core.tools.base import ToolContext, ToolDefinition, ToolResult

DEFAULT_ROUTING_HINT = (
    "Use delegate_task to assign work to specialized agents listed in "
    "<available_agents>. Prefer single for one expert; parallel for independent "
    "lookups; chain when later steps need earlier results ({previous})."
)


def _format_results(results: list[SubAgentResult]) -> str:
    chunks: list[str] = []
    for r in results:
        chunks.append(
            f"[{r.agent_name}] status={r.status}\n{r.response_text or r.error_message or ''}"
        )
    return "\n\n---\n\n".join(chunks)


class DelegateTaskTool:
    def __init__(
        self,
        *,
        registry: AgentProfileRegistry,
        runner: SubAgentRunner,
        name: str = "delegate_task",
    ) -> None:
        self._registry = registry
        self._runner = runner
        agents_xml = registry.format_for_system_prompt()
        self.definition = ToolDefinition(
            name=name,
            description=(
                "Delegate tasks to specialized sub-agents.\n"
                f"{agents_xml}\n"
                "mode=single: provide agent + task. "
                "mode=parallel|chain: provide tasks=[{agent,task},...]. "
                "In chain mode, use {previous} in later tasks."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["single", "parallel", "chain"],
                        "description": "Delegation mode (default single)",
                    },
                    "agent": {"type": "string", "description": "Profile name for single mode"},
                    "task": {"type": "string", "description": "Task text for single mode"},
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "agent": {"type": "string"},
                                "task": {"type": "string"},
                            },
                            "required": ["agent", "task"],
                        },
                        "description": "Task list for parallel/chain",
                    },
                },
            },
        )

    def _resolve_profile(self, name: str) -> AgentProfile | None:
        return self._registry.resolve(name)

    async def execute(
        self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext
    ) -> ToolResult:
        mode = (params.get("mode") or "single").strip().lower()
        if mode not in ("single", "parallel", "chain"):
            return ToolResult(
                content=[TextContent(text=f"Invalid mode: {mode}")],
                details={"delegation": {"type": "delegation", "status": "failed", "error_message": "invalid mode"}},
            )

        delegation_id = str(uuid.uuid4())

        async def on_progress(payload: dict[str, Any]) -> None:
            if ctx.on_update is not None:
                ctx.on_update(
                    ToolResult(
                        content=[TextContent(text="")],
                        details={"delegation": payload},
                    )
                )

        start_payload = {
            "type": "delegation",
            "phase": "start",
            "mode": mode,
            "delegation_id": delegation_id,
            "status": "running",
        }
        await on_progress(start_payload)

        try:
            if mode == "single":
                agent_name = params.get("agent")
                task = params.get("task")
                if not agent_name or not task:
                    raise ValueError("single mode requires agent and task")
                profile = self._resolve_profile(str(agent_name))
                if profile is None:
                    raise ValueError(f"Unknown agent: {agent_name}")
                results = [
                    await self._runner.run_single(
                        profile,
                        str(task),
                        delegation_id=delegation_id,
                        mode="single",
                        signal=ctx.signal,
                        on_progress=on_progress,
                    )
                ]
            else:
                raw_tasks = params.get("tasks")
                if not isinstance(raw_tasks, list) or not raw_tasks:
                    raise ValueError(f"{mode} mode requires non-empty tasks")
                resolved: list[tuple[AgentProfile, str]] = []
                for item in raw_tasks:
                    if not isinstance(item, dict):
                        raise ValueError("each task must be an object")
                    an = item.get("agent")
                    tk = item.get("task")
                    if not an or not tk:
                        raise ValueError("each task requires agent and task")
                    profile = self._resolve_profile(str(an))
                    if profile is None:
                        raise ValueError(f"Unknown agent: {an}")
                    resolved.append((profile, str(tk)))
                if mode == "parallel":
                    results = await self._runner.run_parallel(
                        resolved,
                        delegation_id=delegation_id,
                        signal=ctx.signal,
                        on_progress=on_progress,
                    )
                else:
                    results = await self._runner.run_chain(
                        resolved,
                        delegation_id=delegation_id,
                        signal=ctx.signal,
                        on_progress=on_progress,
                    )
        except Exception as exc:
            end = {
                "type": "delegation",
                "phase": "end",
                "mode": mode,
                "delegation_id": delegation_id,
                "status": "failed",
                "error_message": str(exc),
            }
            await on_progress(end)
            return ToolResult(
                content=[TextContent(text=f"Delegation failed: {exc}")],
                details={"delegation": end},
                display={"type": "delegation_error", "error": str(exc)},
            )

        overall = "completed"
        if any(r.status == "aborted" for r in results):
            overall = "aborted"
        elif any(r.status == "failed" for r in results):
            overall = "failed"

        end_payload = {
            "type": "delegation",
            "phase": "end",
            "mode": mode,
            "delegation_id": delegation_id,
            "status": overall,
            "total": len(results),
        }
        await on_progress(end_payload)

        text = _format_results(results)
        return ToolResult(
            content=[TextContent(text=text)],
            details={
                "delegation": end_payload,
                "results": [
                    {
                        "agent_name": r.agent_name,
                        "status": r.status,
                        "response_text": r.response_text,
                        "error_message": r.error_message,
                        "session_id": r.session_id,
                        "duration_ms": r.duration_ms,
                    }
                    for r in results
                ],
            },
            display={"type": "delegation", "mode": mode, "status": overall},
        )
